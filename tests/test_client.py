import json
from pathlib import Path

import httpx
import pytest
import respx

from wattelse_mcp.client import WattElseAPIError, WattElseClient

BASE_URL = "https://wattelse.test"


def make_client(**kwargs) -> WattElseClient:
    return WattElseClient(
        base_url=BASE_URL,
        client_id="wattelse",
        client_secret="test-secret",
        verify_ssl=False,
        **kwargs,
    )


@respx.mock
async def test_health_does_not_authenticate():
    token_route = respx.post(f"{BASE_URL}/token")
    respx.get(f"{BASE_URL}/health").mock(
        return_value=httpx.Response(200, json={"status": "ok"})
    )

    client = make_client()
    assert await client.health() is True
    assert token_route.call_count == 0
    await client.aclose()


@respx.mock
async def test_authenticated_request_fetches_and_reuses_token():
    token_route = respx.post(f"{BASE_URL}/token").mock(
        return_value=httpx.Response(200, json={"access_token": "tok-123", "expires_in": 3600})
    )
    sessions_route = respx.post(f"{BASE_URL}/create-session/groupA").mock(
        return_value=httpx.Response(200, json={"message": "Session for group 'groupA' created"})
    )

    client = make_client()
    message = await client.create_session("groupA", "default_config")
    await client.create_session("groupA", "default_config")

    assert message == "Session for group 'groupA' created"
    assert token_route.call_count == 1  # token is cached across calls
    assert sessions_route.call_count == 2

    sent_headers = sessions_route.calls[0].request.headers
    assert sent_headers["Authorization"] == "Bearer tok-123"
    await client.aclose()


@respx.mock
async def test_query_rag_decodes_double_encoded_json():
    respx.post(f"{BASE_URL}/token").mock(
        return_value=httpx.Response(200, json={"access_token": "tok-123", "expires_in": 3600})
    )
    inner_payload = {
        "answer": "The answer is 42.",
        "relevant_extracts": [{"content": "extract text", "metadata": {"source": "doc.pdf"}}],
    }
    respx.post(f"{BASE_URL}/query-rag/groupA").mock(
        return_value=httpx.Response(200, json=json.dumps(inner_payload))
    )

    client = make_client()
    result = await client.query("groupA", "What is the answer?")
    assert result == inner_payload
    await client.aclose()


@respx.mock
async def test_list_documents_decodes_double_encoded_json():
    respx.post(f"{BASE_URL}/token").mock(
        return_value=httpx.Response(200, json={"access_token": "tok-123", "expires_in": 3600})
    )
    respx.get(f"{BASE_URL}/list-available-docs/groupA").mock(
        return_value=httpx.Response(200, json=json.dumps(["a.pdf", "b.pdf"]))
    )

    client = make_client()
    docs = await client.list_documents("groupA")
    assert docs == ["a.pdf", "b.pdf"]
    await client.aclose()


@respx.mock
async def test_error_response_raises_api_error():
    respx.post(f"{BASE_URL}/token").mock(
        return_value=httpx.Response(200, json={"access_token": "tok-123", "expires_in": 3600})
    )
    respx.get(f"{BASE_URL}/list-available-docs/groupA").mock(
        return_value=httpx.Response(404, text="Group id not found")
    )

    client = make_client()
    with pytest.raises(WattElseAPIError) as exc_info:
        await client.list_documents("groupA")
    assert exc_info.value.status_code == 404
    await client.aclose()


@respx.mock
async def test_upload_documents_sends_files(tmp_path: Path):
    respx.post(f"{BASE_URL}/token").mock(
        return_value=httpx.Response(200, json={"access_token": "tok-123", "expires_in": 3600})
    )
    upload_route = respx.post(f"{BASE_URL}/upload-docs/groupA").mock(
        return_value=httpx.Response(200, json={"message": "uploaded"})
    )

    file_path = tmp_path / "note.txt"
    file_path.write_text("hello world")

    client = make_client()
    result = await client.upload_documents("groupA", [file_path])

    assert result == {"message": "uploaded"}
    request = upload_route.calls[0].request
    assert b"note.txt" in request.content
    await client.aclose()


def test_client_requires_secret():
    with pytest.raises(ValueError):
        WattElseClient(base_url=BASE_URL, client_id="wattelse", client_secret="")
