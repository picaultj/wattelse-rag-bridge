# wattelse-rag-bridge

Bridges [WattElse](https://github.com/rte-france/wattelse) (RTE's RAG platform) to LLM agents,
via the [Model Context Protocol](https://modelcontextprotocol.io).

Two pieces:

- **`wattelse_mcp/`** — an MCP server, built with the official `mcp` Python SDK's `FastMCP`
  (`mcp.server.fastmcp.FastMCP`), that wraps WattElse's `RAGOrchestrator` HTTP API as MCP tools.
- **`wattelse_agent/`** — an [OpenAI Agents SDK](https://github.com/openai/openai-agents-python)
  agent that talks to that MCP server over stdio and answers questions using it.

## Assessment: RAG agent vs. MCP server

The task asked to build "a RAG agent *or* an MCP" for WattElse. These aren't actually competing
options — an MCP server is an *integration*, an agent is a *consumer* of tools. The real choice is
where to put the WattElse-specific logic (auth, endpoints, response parsing):

- **Baked into an agent** (e.g. as `@function_tool`s directly in an `openai-agents` `Agent`) is the
  fastest path to a working demo, but it locks the integration to one framework. Anthropic's
  Claude Code/Desktop, other agent frameworks, or a teammate's own script can't reuse it.
- **Exposed as an MCP server** decouples the integration from any single framework. Any MCP host —
  this repo's `openai-agents` agent, Claude Desktop, Claude Code, a future LangChain/LlamaIndex
  agent — can mount it and get the same tools for free, and WattElse's auth/session/error-handling
  logic lives in exactly one place.

So this repo does both, correctly layered: the WattElse-specific code lives entirely in the MCP
server (`wattelse_mcp`), and `wattelse_agent` is a thin `openai-agents` client that mounts that
server via `MCPServerStdio` and never talks to WattElse's HTTP API directly. This satisfies "for
agent use the openai-agents framework, for MCP use the official `mcp` package with FastMCP" as a
single coherent design rather than two disconnected deliverables.

```
┌───────────────────────┐        stdio (MCP)        ┌────────────────────┐       HTTPS        ┌───────────────────────┐
│ wattelse_agent (CLI)   │ ─────────────────────────▶│ wattelse_mcp.server │──────────────────▶│ WattElse RAGOrchestrator│
│ openai-agents Agent    │◀───────────────────────── │ FastMCP tools       │◀────────────────── │ API (/query-rag, ...)  │
└───────────────────────┘                            └────────────────────┘                    └───────────────────────┘
```

`wattelse_mcp/server.py` is a standalone MCP server: any other MCP host can run
`python -m wattelse_mcp.server` and get the same tools without `wattelse_agent` in the picture.

## WattElse API surface wrapped

Reverse-engineered from
[`wattelse/api/rag_orchestrator`](https://github.com/rte-france/wattelse/tree/main/wattelse/api/rag_orchestrator):
OAuth2 client-credentials login (`POST /token` with `client_id`/`client_secret` as
`username`/`password`, Bearer token cached until `expires_in`), then per-`group_id` session and
document-collection endpoints (`/create-session`, `/upload-docs`, `/query-rag`, ...).
`wattelse_mcp/client.py` reimplements this contract directly over `httpx` rather than depending on
the `wattelse` package (which pulls in the full ML/embedding stack) — see the docstrings in that
file for the endpoint-by-endpoint mapping.

| MCP tool             | WattElse endpoint                    | Notes |
|-----------------------|--------------------------------------|-------|
| `wattelse_health`      | `GET /health`                        | Unauthenticated |
| `create_rag_session`   | `POST /create-session/{group_id}`    | Idempotent; needed once per group |
| `list_rag_sessions`    | `GET /current-sessions`              | Unauthenticated |
| `upload_documents`     | `POST /upload-docs/{group_id}`       | Paths must be readable by the MCP server process |
| `list_documents`       | `GET /list-available-docs/{group_id}`| |
| `remove_documents`     | `POST /remove-docs/{group_id}`       | |
| `clear_collection`     | `POST /clear-collection/{group_id}`  | Destructive |
| `get_llm_model_name`   | `GET /llm-model-name/{group_id}`     | |
| `query_rag`            | `POST /query-rag/{group_id}`         | Non-streaming only |
| `ask`                  | `create-session` + `query-rag`       | Convenience: default `group_id`, auto-creates session |

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # fill in WATTELSE_CLIENT_SECRET, OPENAI_API_KEY, etc.
```

Required env vars (see `.env.example`): `WATTELSE_BASE_URL`, `WATTELSE_CLIENT_ID`,
`WATTELSE_CLIENT_SECRET` must match a running WattElse `RAGOrchestrator` deployment and its
`client_registry.json`. `OPENAI_API_KEY` is only needed to run `wattelse_agent`.

## Run

Standalone MCP server (e.g. to wire into Claude Desktop/Code, or `mcp dev` for the inspector):

```bash
python -m wattelse_mcp.server
```

Interactive agent (spawns the MCP server itself as a subprocess):

```bash
python -m wattelse_agent.cli
```

## Test

```bash
pytest
```

Tests mock the WattElse HTTP API with `respx` (`tests/test_client.py`) and mock the client inside
the MCP tools (`tests/test_server.py`) — no live WattElse deployment or OpenAI key is required.
