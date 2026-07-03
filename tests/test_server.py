from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from wattelse_mcp import server


class FakeClient:
    def __init__(self):
        self.health = AsyncMock(return_value=True)
        self.create_session = AsyncMock(return_value="Session for group 'default' created")
        self.list_sessions = AsyncMock(return_value=["default"])
        self.upload_documents = AsyncMock(return_value={"message": "uploaded"})
        self.list_documents = AsyncMock(return_value=["a.pdf"])
        self.remove_documents = AsyncMock(return_value={"message": "removed"})
        self.clear_collection = AsyncMock(return_value={"message": "cleared"})
        self.get_llm_model_name = AsyncMock(return_value="gpt-4o-mini")
        self.query = AsyncMock(return_value={"answer": "42", "relevant_extracts": []})


@pytest.fixture
def fake_client(monkeypatch):
    client = FakeClient()
    monkeypatch.setattr(server, "_client", client)
    return client


async def test_wattelse_health(fake_client):
    result = await server.wattelse_health()
    assert result == {"status": "ok"}
    fake_client.health.assert_awaited_once()


async def test_query_rag_forwards_arguments(fake_client):
    result = await server.query_rag(
        group_id="default",
        question="What is the answer?",
        history=[{"role": "user", "content": "hi"}],
        selected_files=["a.pdf"],
        group_system_prompt="Be terse.",
    )
    assert result == {"answer": "42", "relevant_extracts": []}
    fake_client.query.assert_awaited_once_with(
        "default",
        "What is the answer?",
        history=[{"role": "user", "content": "hi"}],
        group_system_prompt="Be terse.",
        selected_files=["a.pdf"],
    )


async def test_ask_creates_session_when_missing(fake_client):
    fake_client.list_sessions.return_value = []

    result = await server.ask(question="What is the answer?")

    fake_client.create_session.assert_awaited_once()
    fake_client.query.assert_awaited_once()
    assert result == {"answer": "42", "relevant_extracts": []}


async def test_ask_reuses_existing_session(fake_client):
    fake_client.list_sessions.return_value = ["default"]

    await server.ask(question="What is the answer?")

    fake_client.create_session.assert_not_awaited()
    fake_client.query.assert_awaited_once()


async def test_upload_documents_rejects_missing_files(fake_client, tmp_path: Path):
    missing = tmp_path / "missing.pdf"
    with pytest.raises(ValueError):
        await server.upload_documents(group_id="default", file_paths=[str(missing)])
    fake_client.upload_documents.assert_not_awaited()


async def test_upload_documents_forwards_existing_files(fake_client, tmp_path: Path):
    present = tmp_path / "present.pdf"
    present.write_text("content")

    result = await server.upload_documents(group_id="default", file_paths=[str(present)])

    assert result == {"message": "uploaded"}
    fake_client.upload_documents.assert_awaited_once_with("default", [present])
