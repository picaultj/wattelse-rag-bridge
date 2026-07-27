"""
MCP server exposing the WattElse RAGOrchestrator API as tools, built with the official
`mcp` Python SDK's FastMCP (`mcp.server.fastmcp.FastMCP`).

Run standalone (stdio transport, the default MCP transport for local/desktop clients):

    python -m wattelse_mcp.server

Or inspect it interactively:

    uv run mcp dev wattelse_mcp/server.py
"""

from __future__ import annotations

from pathlib import Path

import sys
from loguru import logger

from mcp.server.fastmcp import FastMCP
import mcp.types as types

from wattelse_mcp.client import WattElseClient
from wattelse_mcp.config import get_settings

settings = get_settings()

mcp = FastMCP(
    "wattelse-rag",
    instructions=(
        "Tools to manage and query WattElse (RTE's RAG platform) document collections. "
        "Each collection is scoped by a `group_id`. `group_id` is optional on every tool: leave "
        "it out to use the single default collection (this is the common case). Every tool "
        "auto-creates a session (with the default config) for its `group_id` on first use, so "
        "calling `create_rag_session` explicitly is only needed to pick a non-default "
        "`config_name` or to work with a specific, named `group_id`. Never invent or guess a "
        "`group_id` value (e.g. from an env var name) -- call `list_rag_sessions` to see the "
        "real, currently active group_ids, or simply omit `group_id` for the default collection."
    ),
    port=settings.mcp_port,
)

_client: WattElseClient | None = None


def _get_client() -> WattElseClient:
    global _client
    if _client is None:
        settings = get_settings()
        _client = WattElseClient(
            base_url=settings.base_url,
            client_id=settings.client_id,
            client_secret=settings.client_secret,
            verify_ssl=settings.verify_ssl,
            timeout=settings.request_timeout,
        )
    return _client


def _resolve_group_id(group_id: str | None) -> str:
    """Resolve an optional `group_id` tool argument to a concrete id, falling back to the
    server-side configured default (WATTELSE_DEFAULT_GROUP_ID) when the caller omits it."""
    return group_id or get_settings().default_group_id


async def _ensure_session(group_id: str) -> None:
    """Auto-create a WattElse RAG session for `group_id` (using the default config) if one
    doesn't already exist, so tools don't require `create_rag_session` to be called first."""
    settings = get_settings()
    client = _get_client()
    sessions = await client.list_sessions()
    if group_id not in sessions:
        await client.create_session(group_id, settings.default_config)


@mcp.tool()
async def wattelse_health() -> dict:
    """Check whether the WattElse RAGOrchestrator API is reachable."""
    logger.info("Tool call: wattelse_health()")
    ok = await _get_client().health()
    return {"status": "ok" if ok else "unreachable"}


@mcp.tool()
async def create_rag_session(group_id: str | None = None, config_name: str | None = None) -> str:
    """
    Create (or reuse, if it already exists) a WattElse RAG session/collection for `group_id`.
    `group_id` is optional; omit it to target the single default collection. Other tools
    auto-create a session with the default config on first use, so this only needs to be called
    explicitly when you want a non-default `config_name`, or a specific, named `group_id`.
    `config_name` selects a server-side registered RAG config; omit it to use the server default.
    """
    resolved_group_id = _resolve_group_id(group_id)
    logger.info(f"Tool call: create_rag_session(group_id={resolved_group_id!r}, config_name={config_name!r})")
    settings = get_settings()
    return await _get_client().create_session(resolved_group_id, config_name or settings.default_config)


@mcp.tool()
async def list_rag_sessions() -> list[str]:
    """List the group_ids that currently have an active WattElse RAG session."""
    logger.info("Tool call: list_rag_sessions()")
    return await _get_client().list_sessions()


@mcp.tool()
async def upload_documents(file_paths: list[str], group_id: str | None = None) -> dict:
    """
    Upload one or more documents into a WattElse collection.
    `file_paths` must be local filesystem paths readable by this MCP server process.
    `group_id` is optional; omit it to target the single default collection.
    Auto-creates a session for `group_id` (with the default config) if one doesn't exist yet.
    """
    resolved_group_id = _resolve_group_id(group_id)
    logger.info(f"Tool call: upload_documents(group_id={resolved_group_id!r}, file_paths={file_paths!r})")
    paths = [Path(p) for p in file_paths]
    missing = [str(p) for p in paths if not p.is_file()]
    if missing:
        raise ValueError(f"File(s) not found on the MCP server's filesystem: {missing}")
    await _ensure_session(resolved_group_id)
    return await _get_client().upload_documents(resolved_group_id, paths)


@mcp.tool()
async def list_documents(group_id: str | None = None) -> list[str]:
    """List the documents currently indexed in a WattElse collection.
    `group_id` is optional; omit it to target the single default collection.
    Auto-creates a session for `group_id` (with the default config) if one doesn't exist yet."""
    resolved_group_id = _resolve_group_id(group_id)
    logger.info(f"Tool call: list_documents(group_id={resolved_group_id!r})")
    await _ensure_session(resolved_group_id)
    return await _get_client().list_documents(resolved_group_id)


@mcp.tool()
async def remove_documents(filenames: list[str], group_id: str | None = None) -> dict:
    """Remove the given documents (and their embeddings) from a WattElse collection.
    `group_id` is optional; omit it to target the single default collection.
    Auto-creates a session for `group_id` (with the default config) if one doesn't exist yet."""
    resolved_group_id = _resolve_group_id(group_id)
    logger.info(f"Tool call: remove_documents(group_id={resolved_group_id!r}, filenames={filenames!r})")
    await _ensure_session(resolved_group_id)
    return await _get_client().remove_documents(resolved_group_id, filenames)


@mcp.tool()
async def clear_collection(group_id: str | None = None) -> dict:
    """
    Permanently delete ALL documents and embeddings for a WattElse collection, and close its
    session. `group_id` is optional; omit it to target the single default collection.
    Destructive and irreversible: only call this when the user explicitly asks to wipe a collection.
    Auto-creates a session for `group_id` (with the default config) if one doesn't exist yet.
    """
    resolved_group_id = _resolve_group_id(group_id)
    logger.info(f"Tool call: clear_collection(group_id={resolved_group_id!r})")
    await _ensure_session(resolved_group_id)
    return await _get_client().clear_collection(resolved_group_id)


@mcp.tool()
async def get_llm_model_name(group_id: str | None = None) -> str:
    """Return the name of the LLM WattElse uses to generate answers.
    `group_id` is optional; omit it to target the single default collection.
    Auto-creates a session for `group_id` (with the default config) if one doesn't exist yet."""
    resolved_group_id = _resolve_group_id(group_id)
    logger.info(f"Tool call: get_llm_model_name(group_id={resolved_group_id!r})")
    await _ensure_session(resolved_group_id)
    return await _get_client().get_llm_model_name(resolved_group_id)


@mcp.tool()
async def query_rag(
    question: str,
    group_id: str | None = None,
    history: list[dict[str, str]] | None = None,
    selected_files: list[str] | None = None,
    group_system_prompt: str | None = None,
) -> dict:
    """
    Ask a question against a WattElse document collection.
    `group_id` is optional; omit it to target the single default collection (for that common
    case, `ask` is a simpler shortcut).
    Returns {"answer": str, "relevant_extracts": [{"content": str, "metadata": dict}, ...]}.
    Auto-creates a session for `group_id` (with the default config) if one doesn't exist yet.
    `history` is a list of {"role": "user"|"assistant", "content": str} turns, oldest first.
    `selected_files` restricts retrieval to a subset of the collection's documents.
    """
    resolved_group_id = _resolve_group_id(group_id)
    logger.info(f"Tool call: query_rag(group_id={resolved_group_id!r}, question={question!r})")
    await _ensure_session(resolved_group_id)
    return await _get_client().query(
        resolved_group_id,
        question,
        history=history,
        group_system_prompt=group_system_prompt,
        selected_files=selected_files,
    )


@mcp.tool()
async def ask(question: str, group_system_prompt: str | None = None) -> dict:
    """
    Convenience tool for the common single-collection case: ask a question against the single
    default WattElse collection, auto-creating its session on first use.
    Returns the same shape as `query_rag`.
    """
    settings = get_settings()
    logger.info(f"Tool call: ask(group_id={settings.default_group_id!r}, question={question!r})")
    await _ensure_session(settings.default_group_id)
    return await _get_client().query(
        settings.default_group_id, question, group_system_prompt=group_system_prompt
    )


def main() -> None:
    # Configure loguru to write to stderr
    logger.remove()
    logger.add(sys.stderr, level="INFO")

    # Patch JSONRPCMessage.model_validate_json to handle empty lines gracefully.
    # The MCP SDK's stdio transport reads line by line and passes them to this method.
    # Empty lines (e.g. \n) trigger a Pydantic validation error if not handled.
    original_validate = types.JSONRPCMessage.model_validate_json

    def patched_validate(cls, json_data, *args, **kwargs):
        if isinstance(json_data, (str, bytes)) and not json_data.strip():
            # Return a dummy notification that will be ignored by the server.
            # 'notifications/initialized' is a valid method that's safe to send twice
            # (though here it's being "received" by the server from the client).
            return types.JSONRPCMessage(
                root=types.JSONRPCNotification(
                    jsonrpc="2.0",
                    method="notifications/initialized",
                )
            )
        return original_validate(json_data, *args, **kwargs)

    types.JSONRPCMessage.model_validate_json = classmethod(patched_validate)

    # When running as SSE or streamable-http, display the full URL.
    # We detect transport if it's the first argument or if MCP_TRANSPORT env var is set (FastMCP convention).
    transport = "streamable-http"
    if len(sys.argv) > 1 and sys.argv[1] in ["stdio", "sse", "streamable-http"]:
        transport = sys.argv[1]

    if transport in ["sse", "streamable-http"]:
        host = mcp.settings.host
        port = mcp.settings.port
        if transport == "sse":
            path = mcp.settings.sse_path
        else:
            path = mcp.settings.streamable_http_path
        
        # Default mount path is /
        logger.info(f"URL: http://{host}:{port}{path}")

    logger.info(f"Starting WattElse MCP server on {transport}...")
    try:
        mcp.run(transport=transport)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
