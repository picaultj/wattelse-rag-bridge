# Architecture

## Overview

This repository has two layers, kept deliberately separate:

- **`wattelse_mcp`** — an MCP server that owns all WattElse-specific integration logic (OAuth2
  client-credentials auth, session/document/query endpoints, response parsing). It exposes that
  logic as MCP tools over stdio, using the official `mcp` package's `FastMCP`.
- **`wattelse_agent`** — an [OpenAI Agents SDK](https://github.com/openai/openai-agents-python)
  agent that mounts `wattelse_mcp` as its only tool source, via `MCPServerStdio`. It never talks to
  WattElse's HTTP API directly.

Because the WattElse integration lives entirely behind the MCP boundary, `wattelse_mcp` can be
mounted by any other MCP host (Claude Desktop, Claude Code, a different agent framework) with zero
code changes — `wattelse_agent` is just one consumer among many.

## Components

```mermaid
flowchart LR
    subgraph hosts["MCP hosts"]
        agent["wattelse_agent\n(openai-agents Agent)"]
        other["Other MCP hosts\n(Claude Desktop, Claude Code, ...)"]
    end

    subgraph bridge["wattelse_mcp"]
        server["server.py\nFastMCP tools"]
        client["client.py\nWattElseClient (httpx)"]
        config["config.py\nSettings (env / .env)"]
    end

    subgraph wattelse["WattElse deployment"]
        orchestrator["RAGOrchestrator API\n/token, /query-rag, ..."]
        backend["RAGBackend\n(one per group_id)"]
        vdb[("Vector DB")]
        llm["LLM / Embedding services"]
    end

    agent -- "MCP over stdio" --> server
    other -- "MCP over stdio" --> server
    server --> client
    client -- "HTTPS + Bearer token" --> orchestrator
    orchestrator --> backend
    backend --> vdb
    backend --> llm
    config -.config.-> client
    config -.config.-> server
```

| File | Responsibility |
|---|---|
| `wattelse_mcp/config.py` | `pydantic-settings` `Settings`, read from `WATTELSE_*` env vars / `.env` |
| `wattelse_mcp/client.py` | `WattElseClient`: async `httpx` wrapper around the WattElse `RAGOrchestrator` API — token caching, one method per endpoint, response (de)serialization |
| `wattelse_mcp/server.py` | `FastMCP` instance; one `@mcp.tool()` per `WattElseClient` method, plus the `ask` convenience tool |
| `wattelse_agent/agent.py` | Builds an `Agent` + `MCPServerStdio` pointing at `python -m wattelse_mcp.server` |
| `wattelse_agent/cli.py` | Interactive REPL driving that agent with `Runner` |

## Request flow: answering a question

`ask` is the convenience tool most callers use — it hides session bookkeeping behind a single call.
`query_rag` follows the same path minus the session lookup/creation step.

```mermaid
sequenceDiagram
    participant U as User
    participant A as wattelse_agent (Agent)
    participant M as wattelse_mcp.server (FastMCP)
    participant C as WattElseClient
    participant W as WattElse RAGOrchestrator API

    U->>A: question
    A->>M: call tool "ask" (MCP over stdio)
    M->>C: list_sessions()
    C->>W: GET /current-sessions
    alt default group has no session yet
        M->>C: create_session(group_id, config)
        C->>W: POST /create-session/{group_id}
    end
    M->>C: query(group_id, question)
    C->>W: POST /token (only if no cached/expired token)
    W-->>C: access_token, expires_in
    C->>W: POST /query-rag/{group_id} (Authorization: Bearer ...)
    W-->>C: JSON-encoded {"answer", "relevant_extracts"}
    C-->>M: decoded {"answer": str, "relevant_extracts": [...]}
    M-->>A: tool result
    A-->>U: final answer, grounded in relevant_extracts
```

## Auth

`WattElseClient` mirrors WattElse's own client-credentials flow: `client_id`/`client_secret` are
sent as `username`/`password` to `POST /token`, the returned bearer token is cached in memory and
transparently refreshed shortly before `expires_in` elapses. `/health` and `/current-sessions` are
called without a token, matching how the upstream API leaves them unauthenticated.

## Deployment notes

- `wattelse_mcp.server` is a plain stdio MCP server (`python -m wattelse_mcp.server`) — it can be
  registered in any MCP host's config (e.g. Claude Desktop's `claude_desktop_config.json`) the same
  way `wattelse_agent` launches it.
- `upload_documents` takes filesystem paths that must be readable by whichever process is running
  `wattelse_mcp.server` — for a remote agent host, that means files need to be staged on that host
  first, not on the machine driving the conversation.
- All group/session state lives server-side in WattElse; `wattelse_mcp` is stateless and can be
  restarted freely.
