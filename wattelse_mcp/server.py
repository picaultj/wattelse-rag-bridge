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

from mcp.server.fastmcp import FastMCP

from wattelse_mcp.client import WattElseClient
from wattelse_mcp.config import get_settings

mcp = FastMCP(
    "wattelse-rag",
    instructions=(
        "Tools to manage and query WattElse (RTE's RAG platform) document collections. "
        "Each collection is scoped by a `group_id`. Call `create_rag_session` once per group_id "
        "before uploading documents or querying it. For a quick single-collection setup, prefer "
        "the `ask` tool, which uses a pre-configured default group_id and auto-creates its session."
    ),
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


@mcp.tool()
async def wattelse_health() -> dict:
    """Check whether the WattElse RAGOrchestrator API is reachable."""
    ok = await _get_client().health()
    return {"status": "ok" if ok else "unreachable"}


@mcp.tool()
async def create_rag_session(group_id: str, config_name: str | None = None) -> str:
    """
    Create (or reuse, if it already exists) a WattElse RAG session/collection for `group_id`.
    Must be called once per group before `upload_documents` or `query_rag` can be used for it.
    `config_name` selects a server-side registered RAG config; defaults to WATTELSE_DEFAULT_CONFIG.
    """
    settings = get_settings()
    return await _get_client().create_session(group_id, config_name or settings.default_config)


@mcp.tool()
async def list_rag_sessions() -> list[str]:
    """List the group_ids that currently have an active WattElse RAG session."""
    return await _get_client().list_sessions()


@mcp.tool()
async def upload_documents(group_id: str, file_paths: list[str]) -> dict:
    """
    Upload one or more documents into the WattElse collection for `group_id`.
    `file_paths` must be local filesystem paths readable by this MCP server process.
    A session for `group_id` must already exist (see `create_rag_session`).
    """
    paths = [Path(p) for p in file_paths]
    missing = [str(p) for p in paths if not p.is_file()]
    if missing:
        raise ValueError(f"File(s) not found on the MCP server's filesystem: {missing}")
    return await _get_client().upload_documents(group_id, paths)


@mcp.tool()
async def list_documents(group_id: str) -> list[str]:
    """List the documents currently indexed in the WattElse collection for `group_id`."""
    return await _get_client().list_documents(group_id)


@mcp.tool()
async def remove_documents(group_id: str, filenames: list[str]) -> dict:
    """Remove the given documents (and their embeddings) from the `group_id` collection."""
    return await _get_client().remove_documents(group_id, filenames)


@mcp.tool()
async def clear_collection(group_id: str) -> dict:
    """
    Permanently delete ALL documents and embeddings for `group_id`, and close its session.
    Destructive and irreversible: only call this when the user explicitly asks to wipe a collection.
    """
    return await _get_client().clear_collection(group_id)


@mcp.tool()
async def get_llm_model_name(group_id: str) -> str:
    """Return the name of the LLM WattElse uses to generate answers for `group_id`."""
    return await _get_client().get_llm_model_name(group_id)


@mcp.tool()
async def query_rag(
    group_id: str,
    question: str,
    history: list[dict[str, str]] | None = None,
    selected_files: list[str] | None = None,
    group_system_prompt: str | None = None,
) -> dict:
    """
    Ask a question against the WattElse document collection for `group_id`.
    Returns {"answer": str, "relevant_extracts": [{"content": str, "metadata": dict}, ...]}.
    A session for `group_id` must already exist (see `create_rag_session`).
    `history` is a list of {"role": "user"|"assistant", "content": str} turns, oldest first.
    `selected_files` restricts retrieval to a subset of the collection's documents.
    """
    return await _get_client().query(
        group_id,
        question,
        history=history,
        group_system_prompt=group_system_prompt,
        selected_files=selected_files,
    )


@mcp.tool()
async def ask(question: str, group_system_prompt: str | None = None) -> dict:
    """
    Convenience tool for the common single-collection case: ask a question using the default
    WattElse group (WATTELSE_DEFAULT_GROUP_ID), auto-creating its session on first use.
    Returns the same shape as `query_rag`.
    """
    settings = get_settings()
    client = _get_client()
    sessions = await client.list_sessions()
    if settings.default_group_id not in sessions:
        await client.create_session(settings.default_group_id, settings.default_config)
    return await client.query(settings.default_group_id, question, group_system_prompt=group_system_prompt)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
