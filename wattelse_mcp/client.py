"""
Async client for the WattElse RAGOrchestrator API.

Reimplements the same HTTP contract as `wattelse.api.rag_orchestrator.client.RAGOrchestratorClient`
(see https://github.com/rte-france/wattelse/blob/main/wattelse/api/rag_orchestrator/client.py)
without depending on the (heavyweight, ML-dependency-laden) `wattelse` package itself:

- OAuth2-style client-credentials login against `POST /token` (client_id/client_secret sent as
  username/password), Bearer token cached until it expires.
- One coroutine per RAGOrchestrator endpoint (session management, document management, querying).

Endpoints and response shapes below mirror wattelse/api/rag_orchestrator/{__init__,routers/*}.py.
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any

import httpx
from loguru import logger

ENDPOINT_TOKEN = "/token"
ENDPOINT_HEALTH = "/health"
ENDPOINT_CREATE_SESSION = "/create-session"
ENDPOINT_QUERY_RAG = "/query-rag"
ENDPOINT_UPLOAD_DOCS = "/upload-docs"
ENDPOINT_REMOVE_DOCS = "/remove-docs"
ENDPOINT_LIST_AVAILABLE_DOCS = "/list-available-docs"
ENDPOINT_CURRENT_SESSIONS = "/current-sessions"
ENDPOINT_CLEAN_SESSIONS = "/clean_sessions"
ENDPOINT_DOWNLOAD = "/download-doc"
ENDPOINT_CLEAR_COLLECTION = "/clear-collection"
ENDPOINT_GENERATION_MODEL_NAME = "/llm-model-name"

# Endpoints the upstream API leaves unauthenticated (no Security() dependency server-side).
_UNAUTHENTICATED_ENDPOINTS = {ENDPOINT_HEALTH, ENDPOINT_TOKEN, ENDPOINT_CURRENT_SESSIONS}

# Refresh the access token slightly before it actually expires.
_TOKEN_REFRESH_LEEWAY_SECONDS = 30


class WattElseAuthError(RuntimeError):
    """Raised when obtaining an access token from WattElse fails."""


class WattElseAPIError(RuntimeError):
    """Raised when the WattElse API returns a non-2xx response."""

    def __init__(self, status_code: int, detail: str):
        super().__init__(f"WattElse API error {status_code}: {detail}")
        self.status_code = status_code
        self.detail = detail


class WattElseClient:
    """Thin async wrapper around the WattElse RAGOrchestrator HTTP API."""

    def __init__(
        self,
        base_url: str,
        client_id: str,
        client_secret: str,
        verify_ssl: bool = True,
        timeout: float = 60.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not client_secret:
            raise ValueError("client_secret must be set")
        self._client_id = client_id
        self._client_secret = client_secret
        self._http = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            verify=verify_ssl,
            timeout=timeout,
            transport=transport,
        )
        self._token: str | None = None
        self._token_expiry: float = 0.0

    async def __aenter__(self) -> WattElseClient:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._http.aclose()

    # -- auth -----------------------------------------------------------------

    async def _authenticate(self) -> None:
        # Authentication should also be retried if it fails due to network issues
        max_retries = 3
        retry_delay = 1.0
        for attempt in range(max_retries):
            try:
                response = await self._http.post(
                    ENDPOINT_TOKEN,
                    data={"username": self._client_id, "password": self._client_secret},
                )
                if response.status_code != 200:
                    raise WattElseAuthError(
                        f"Failed to obtain access token: {response.status_code} {response.text}"
                    )
                payload = response.json()
                self._token = payload["access_token"]
                expires_in = payload.get("expires_in", 3600)
                self._token_expiry = time.monotonic() + expires_in - _TOKEN_REFRESH_LEEWAY_SECONDS
                return
            except (httpx.RemoteProtocolError, httpx.ConnectError, httpx.WriteError) as e:
                if "CERTIFICATE_VERIFY_FAILED" in str(e):
                    logger.error(
                        f"SSL certificate verification failed: {e}. "
                        "If you are using a self-signed certificate, set WATTELSE_VERIFY_SSL=false in your .env file."
                    )
                    raise
                if attempt == max_retries - 1:
                    logger.error(f"Authentication failed after {max_retries} attempts: {e}")
                    raise
                logger.warning(f"Authentication attempt {attempt + 1} failed, retrying in {retry_delay}s... ({e})")
                await asyncio.sleep(retry_delay)
                retry_delay *= 2

    async def _auth_header(self) -> dict[str, str]:
        if self._token is None or time.monotonic() >= self._token_expiry:
            await self._authenticate()
        return {"Authorization": f"Bearer {self._token}"}

    # -- low-level request helper ----------------------------------------------

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        logger.debug(f"Request: {method} {path}")
        headers = kwargs.pop("headers", None) or {}
        if path not in _UNAUTHENTICATED_ENDPOINTS:
            headers.update(await self._auth_header())

        # Retry logic for transient network issues (like "Server disconnected without sending a response")
        max_retries = 3
        retry_delay = 1.0
        for attempt in range(max_retries):
            try:
                response = await self._http.request(method, path, headers=headers, **kwargs)
                break
            except (httpx.RemoteProtocolError, httpx.ConnectError, httpx.WriteError) as e:
                if "CERTIFICATE_VERIFY_FAILED" in str(e):
                    logger.error(
                        f"SSL certificate verification failed: {e}. "
                        "If you are using a self-signed certificate, set WATTELSE_VERIFY_SSL=false in your .env file."
                    )
                    raise
                if attempt == max_retries - 1:
                    logger.error(f"Request failed after {max_retries} attempts: {method} {path} - {e}")
                    raise
                logger.warning(
                    f"Request attempt {attempt + 1} failed, retrying in {retry_delay}s... "
                    f"({method} {path} - {e})"
                )
                await asyncio.sleep(retry_delay)
                retry_delay *= 2  # Exponential backoff
            except Exception as e:
                logger.error(f"Request failed: {method} {path} - {e}")
                raise

        if response.status_code >= 400:
            logger.warning(f"API error: {method} {path} -> {response.status_code}")
            raise WattElseAPIError(response.status_code, response.text)
        return response

    # -- info / sessions --------------------------------------------------------

    async def health(self) -> bool:
        response = await self._request("GET", ENDPOINT_HEALTH)
        return response.json() == {"status": "ok"}

    async def get_llm_model_name(self, group_id: str) -> str:
        response = await self._request("GET", f"{ENDPOINT_GENERATION_MODEL_NAME}/{group_id}")
        return response.json()

    async def create_session(self, group_id: str, config: str | dict) -> str:
        response = await self._request(
            "POST",
            f"{ENDPOINT_CREATE_SESSION}/{group_id}",
            json={"config": config},
        )
        return response.json().get("message", f"Session for group '{group_id}' ready")

    async def list_sessions(self) -> list[str]:
        response = await self._request("GET", ENDPOINT_CURRENT_SESSIONS)
        return response.json()

    async def clean_sessions(self, group_id: str | None = None) -> None:
        suffix = f"/{group_id}" if group_id else ""
        await self._request("POST", f"{ENDPOINT_CLEAN_SESSIONS}{suffix}")

    # -- documents ----------------------------------------------------------------

    async def upload_documents(self, group_id: str, file_paths: list[Path]) -> dict:
        files = [("files", (p.name, p.read_bytes())) for p in file_paths]
        response = await self._request("POST", f"{ENDPOINT_UPLOAD_DOCS}/{group_id}", files=files)
        return response.json()

    async def remove_documents(self, group_id: str, filenames: list[str]) -> dict:
        response = await self._request("POST", f"{ENDPOINT_REMOVE_DOCS}/{group_id}", json=filenames)
        return response.json()

    async def list_documents(self, group_id: str) -> list[str]:
        response = await self._request("GET", f"{ENDPOINT_LIST_AVAILABLE_DOCS}/{group_id}")
        # The server returns `json.dumps(list)` as the body of a `str`-typed FastAPI response,
        # so the payload is JSON-encoded twice; decode once more to get the actual list.
        return json.loads(response.json())

    async def clear_collection(self, group_id: str) -> dict:
        response = await self._request("POST", f"{ENDPOINT_CLEAR_COLLECTION}/{group_id}")
        return response.json()

    async def download_document(self, group_id: str, filename: str, target_path: Path) -> Path:
        response = await self._request("GET", f"{ENDPOINT_DOWNLOAD}/{group_id}/{filename}")
        target_path.write_bytes(response.content)
        return target_path

    # -- querying -------------------------------------------------------------------

    async def query(
        self,
        group_id: str,
        message: str,
        history: list[dict[str, str]] | None = None,
        group_system_prompt: str | None = None,
        selected_files: list[str] | None = None,
    ) -> dict:
        response = await self._request(
            "POST",
            f"{ENDPOINT_QUERY_RAG}/{group_id}",
            json={
                "message": message,
                "history": history,
                "group_system_prompt": group_system_prompt,
                "selected_files": selected_files,
                "stream": False,
            },
        )
        # Same double-JSON-encoding quirk as list_documents
        # (see rag_query.py: `return json.dumps(response)`).
        return json.loads(response.json())
