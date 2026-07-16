import pytest
import respx
import httpx
import asyncio
from wattelse_mcp.client import WattElseClient

@pytest.mark.asyncio
async def test_request_retry_on_remote_protocol_error():
    # Mocking the client
    client = WattElseClient(
        base_url="http://testserver",
        client_id="test",
        client_secret="test",
    )
    
    # Pre-set a valid token so we don't trigger authentication retry here
    client._token = "valid_token"
    client._token_expiry = 9999999999.0

    async with respx.mock(base_url="http://testserver") as respx_mock:
        # First call fails with RemoteProtocolError, second succeeds
        route = respx_mock.get("/current-sessions")
        route.side_effect = [
            httpx.RemoteProtocolError("Server disconnected without sending a response"),
            httpx.Response(200, json=["session1"])
        ]
        
        # We need to monkeypatch asyncio.sleep to avoid waiting during tests
        original_sleep = asyncio.sleep
        async def mock_sleep(delay):
            pass
        asyncio.sleep = mock_sleep
        
        try:
            sessions = await client.list_sessions()
            assert sessions == ["session1"]
            assert route.call_count == 2
        finally:
            asyncio.sleep = original_sleep

@pytest.mark.asyncio
async def test_request_max_retries_exceeded():
    client = WattElseClient(
        base_url="http://testserver",
        client_id="test",
        client_secret="test",
    )
    client._token = "valid_token"
    client._token_expiry = 9999999999.0

    async with respx.mock(base_url="http://testserver") as respx_mock:
        # All calls fail
        route = respx_mock.get("/current-sessions")
        route.side_effect = httpx.RemoteProtocolError("Persistent error")
        
        original_sleep = asyncio.sleep
        async def mock_sleep(delay):
            pass
        asyncio.sleep = mock_sleep
        
        try:
            with pytest.raises(httpx.RemoteProtocolError):
                await client.list_sessions()
            assert route.call_count == 3  # max_retries
        finally:
            asyncio.sleep = original_sleep
