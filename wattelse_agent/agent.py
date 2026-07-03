"""
Builds an OpenAI Agents SDK `Agent` whose tools come entirely from the `wattelse_mcp` FastMCP
server, launched as a stdio subprocess via `MCPServerStdio`. The agent process never talks to
WattElse directly -- it only ever calls MCP tools, which is what keeps the WattElse-specific
HTTP/auth logic isolated in `wattelse_mcp` and reusable by any other MCP host (Claude Desktop,
Claude Code, etc.), not just this agent.
"""

from __future__ import annotations

import sys

from agents import Agent
from agents.mcp import MCPServerStdio

INSTRUCTIONS = """\
You are a RAG assistant backed by WattElse, RTE's internal document Q&A platform.

- For a simple, one-off question against the default document collection, call the `ask` tool.
- For multi-collection workflows, first call `create_rag_session` for the relevant `group_id`,
  optionally `upload_documents`, then use `query_rag` for that `group_id`.
- Use `list_documents` / `list_rag_sessions` to check state before assuming a collection exists.
- When you answer using `relevant_extracts` from a query result, ground your answer in them and
  mention which document(s) the information came from.
- If the retrieved extracts don't support an answer, say so plainly instead of guessing.
- Never call `clear_collection` or `remove_documents` unless the user explicitly asks to delete
  content -- these are destructive and irreversible.
"""


def build_mcp_server() -> MCPServerStdio:
    """Launch `wattelse_mcp.server` as a stdio MCP server subprocess."""
    return MCPServerStdio(
        name="wattelse",
        params={"command": sys.executable, "args": ["-m", "wattelse_mcp.server"]},
        client_session_timeout_seconds=60,
    )


def build_agent(mcp_server: MCPServerStdio) -> Agent:
    return Agent(
        name="WattElse RAG Assistant",
        instructions=INSTRUCTIONS,
        mcp_servers=[mcp_server],
    )
