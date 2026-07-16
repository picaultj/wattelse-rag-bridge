# wattelse-rag-bridge

Bridges [WattElse](https://github.com/rte-france/wattelse) (RTE's RAG platform) to LLM agents,
via the [Model Context Protocol](https://modelcontextprotocol.io).

Two pieces:

- **`wattelse_mcp/`** — an MCP server, built with the official `mcp` Python SDK's `FastMCP`
  (`mcp.server.fastmcp.FastMCP`), that wraps WattElse's `RAGOrchestrator` HTTP API as MCP tools.
- **`wattelse_agent/`** — an [OpenAI Agents SDK](https://github.com/openai/openai-agents-python)
  agent that talks to that MCP server over stdio and answers questions using it.

All WattElse-specific logic (auth, sessions, document management, querying) lives in `wattelse_mcp`
and nowhere else, so it can be reused by any MCP host, not just `wattelse_agent`. See
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the full design, component breakdown, and
sequence diagrams.

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
The port can be configured via `WATTELSE_MCP_PORT` (defaults to 8000).

```bash
# default (streamable-http)
python -m wattelse_mcp.server

# stdio transport
python -m wattelse_mcp.server stdio

# SSE transport
python -m wattelse_mcp.server sse
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

## CI

Two workflows under `.github/workflows/`:

- **`lint.yml`** — runs `ruff check` and `ruff format --check` on every push and pull request.
- **`release.yml`** — on merge of a pull request into `main`, bumps `version` in `pyproject.toml`
  (patch by default; add a `bump:minor` or `bump:major` label to the PR to change that), commits
  the bump, tags it `vX.Y.Z`, and publishes a GitHub release with auto-generated notes.
