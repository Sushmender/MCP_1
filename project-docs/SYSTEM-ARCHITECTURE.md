# System Architecture

> **Service Name:** MCP Research Backend  
> **Framework:** FastAPI (Python 3.11+)  
> **Protocol Layer:** Model Context Protocol (MCP)  
> **Version:** 1.0.0

---

## Table of Contents

1. [Overall System Architecture](#1-overall-system-architecture)
2. [Backend Components](#2-backend-components)
3. [Data Flow](#3-data-flow)
4. [External Dependencies](#4-external-dependencies)
5. [Service Communication](#5-service-communication)
6. [Deployment Architecture](#6-deployment-architecture)

---

## 1. Overall System Architecture

The system is a **single-process FastAPI backend** that orchestrates AI-powered academic research by connecting to three MCP (Model Context Protocol) sub-servers. There is no database — all persistent state is stored as JSON files on the local filesystem.

```
┌──────────────────────────────────────────────────────────────────┐
│                      CLIENT (Browser / React Frontend)           │
│                   POST /api/chat   GET /api/tools                │
│                   POST /api/prompts/execute   GET /api/resources │
└─────────────────────────────┬────────────────────────────────────┘
                              │ HTTP (REST / JSON)
                              │ CORS: open (*)
┌─────────────────────────────▼────────────────────────────────────┐
│                         FastAPI App (ASGI)                       │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │                  API Router (/api/*)                     │    │
│  │  endpoints.py — chat / tools / prompts / resources       │    │
│  └───────────────────────┬──────────────────────────────────┘    │
│                          │                                        │
│  ┌───────────────────────▼──────────────────────────────────┐    │
│  │                  MCPClientManager                        │    │
│  │  • Manages AsyncExitStack of subprocess sessions         │    │
│  │  • Runs LLM ↔ Tool orchestration loop                    │    │
│  │  • Dispatches tool calls to correct MCP session          │    │
│  └─────┬──────────────────────────┬───────────────────┬─────┘    │
│        │                          │                   │           │
│  ┌─────▼──────┐  ┌────────────────▼────────┐  ┌──────▼──────┐   │
│  │  LLM Layer │  │  research MCP Server    │  │  filesystem │   │
│  │  (Provider │  │  python research_server │  │  MCP Server │   │
│  │  Abstraction│  │  .py  — subprocess     │  │  npx @mcp/  │   │
│  │  )         │  │  tools: search_papers   │  │  server-fs  │   │
│  │            │  │          extract_info   │  │  ./papers   │   │
│  │  Groq /    │  │  resources: papers://   │  └──────┬──────┘   │
│  │  Cerebras/ │  │  prompts: summarize/    │         │           │
│  │  Anthropic │  │           compare/      │   ./papers dir     │
│  └─────┬──────┘  │           find_and_... │         │           │
│        │         └────────────────┬────────┘  ┌──────▼──────┐   │
│        │                         │            │  fetch MCP  │   │
│        │                    arXiv API         │  Server     │   │
│        │                                      │  uvx mcp-   │   │
│  External LLM API                             │  server-    │   │
│  (HTTPS)                                      │  fetch      │   │
│                                               └──────┬──────┘   │
│                                                      │           │
│                                               Live Web (HTTP)   │
└──────────────────────────────────────────────────────────────────┘
```

**Key architectural characteristics:**

- **No database** — paper metadata is stored as JSON files in `papers/<topic>/papers_info.json`
- **Stateful singleton** — `MCPClientManager` is created once at startup and stored in `app.state.mcp_client`
- **Async-first** — all I/O (LLM calls, MCP sessions, tool execution) is fully async
- **Provider-agnostic LLM layer** — switching LLM providers requires only a `.env` change

---

## 2. Backend Components

### 2.1 `app/main.py` — FastAPI Application Entry Point

| Responsibility | Detail |
|----------------|--------|
| FastAPI app instance creation | Title: `MCP Production Backend`, version `1.0.0` |
| Lifespan management | Startup: initializes `MCPClientManager`; Shutdown: calls `cleanup()` |
| CORS middleware | Open (`*`) for all origins, methods, headers |
| Router mounting | Mounts `api_router` at prefix `/api` |
| Health endpoint | `GET /` returns `{"status": "healthy", ...}` |

### 2.2 `app/config.py` — Settings

Reads all configuration from environment variables (via `python-dotenv`). Exposes a singleton `settings` object used throughout the app.

| Setting | Purpose |
|---------|---------|
| `LLM_PROVIDER` | Selects which LLM provider to instantiate (`cerebras` / `groq` / `anthropic`) |
| `*_API_KEY` / `*_MODEL` | Per-provider credentials and model selection |
| `HOST`, `PORT` | Uvicorn bind address |
| `SERVER_CONFIG_PATH` | Path to `server_config.json` |
| `LOG_LEVEL` | Uvicorn log verbosity |
| `PROMPT_TIMEOUT_SECS` | Global request timeout (default: 300s) |

### 2.3 `app/api/endpoints.py` — REST Endpoints

Thin controller layer. Each endpoint:
1. Retrieves `mcp_client` from `request.app.state`
2. Delegates to `MCPClientManager` methods
3. Wraps exceptions in `HTTPException`
4. Enforces the `PROMPT_TIMEOUT_SECS` via `asyncio.wait_for()`

### 2.4 `app/mcp_client.py` — MCPClientManager

The core orchestration engine. Responsibilities:

| Method | Purpose |
|--------|---------|
| `initialize()` | Creates LLM provider; ensures `papers/` dir exists; connects to all MCP servers |
| `connect_to_servers()` | Loads `server_config.json`; iterates server definitions |
| `connect_to_server()` | Launches a subprocess MCP server via `stdio_client`; discovers and registers its tools, prompts, resources, and resource templates |
| `process_query()` | Runs the LLM ↔ MCP tool-call loop until `stop_reason == "end_turn"` |
| `get_resource()` | Reads a specific resource URI from the correct MCP session |
| `execute_prompt()` | Fetches a rendered prompt from MCP, then pipes it through `process_query()` |
| `cleanup()` | Closes all `AsyncExitStack` contexts (stops all subprocess MCP servers) |

**Session Registry (`self.sessions`):** A flat dictionary mapping tool names, prompt names, and resource URIs → the MCP session that owns them. This enables O(1) dispatch of tool calls to the correct subprocess.

### 2.5 `app/llm/` — LLM Provider Layer

**Abstract base:** `BaseLLMProvider` (ABC) defines the `chat()` interface. Returns a normalized dict:

```python
{
    "text": str,         # assistant text
    "tool_calls": list,  # [{id, name, input}]
    "stop_reason": str   # "tool_use" | "end_turn"
}
```

**Concrete providers:**

| File | Provider | SDK | Default Model | Max Tokens |
|------|----------|-----|---------------|------------|
| `groq_provider.py` | Groq | `AsyncGroq` | `llama-3.3-70b-versatile` | 2048 |
| `cerebras_provider.py` | Cerebras | `AsyncCerebras` | `gpt-oss-120b` | 4096 |
| `anthropic_provider.py` | Anthropic | `AsyncAnthropic` | `claude-3-7-sonnet-20250219` | 2048 |

Both Groq and Cerebras use **OpenAI-compatible** function-calling format. Anthropic uses its native tool-use format (which matches our internal format directly, so no conversion is needed).

**Schema sanitizer:** `_sanitize_schema()` strips unsupported JSON Schema keywords (`default`, `examples`, `$schema`, `$id`, `allOf`, etc.) before sending tools to Groq/Cerebras, preventing HTTP 400 errors.

**Malformed tool-call recovery:** Both Groq and Cerebras providers handle edge cases where models return:
- Embedded JSON in the function name (e.g. `list_directory{"path": "papers"}`)
- XML-style function calls in response text (e.g. `<function=search_papers{...}</function>`)

**Factory:** `app/llm/factory.py` — `get_llm_provider()` reads `settings.LLM_PROVIDER` and returns the appropriate provider instance, raising `ValueError` if the API key is missing.

### 2.6 `app/schemas/chat.py` — Pydantic Models

All request/response bodies are validated by Pydantic v2:

| Model | Used By |
|-------|---------|
| `ChatRequest` | `POST /api/chat` request body |
| `ChatResponse` | `POST /api/chat` response |
| `ExecutePromptRequest` | `POST /api/prompts/execute` request body |
| `ExecutePromptResponse` | `POST /api/prompts/execute` response |
| `ReadResourceResponse` | `GET /api/resources/read` response |
| `PromptInfo`, `PromptArgument`, `ResourceInfo` | Internal data models |

### 2.7 `research_server.py` — Custom MCP Research Server

A standalone MCP server built with `FastMCP`. Runs as a subprocess launched by `MCPClientManager`. Exposes:

**Tools:**
- `search_papers(topic, max_results=5)` — queries arXiv, persists JSON metadata
- `extract_info(paper_id)` — looks up stored paper by arXiv ID

**Resources:**
- `papers://list` — JSON map of all topics → paper IDs
- `papers://{topic}/info` — full metadata JSON for a topic

**Prompts:**
- `summarize_paper(paper_id)` — renders a "summarize this paper" instruction
- `compare_papers(paper_id_1, paper_id_2)` — renders a comparison instruction
- `find_and_summarize(topic, max_results=3)` — renders a search-and-summarize instruction

---

## 3. Data Flow

### 3.1 Chat Query Flow (`POST /api/chat`)

```
Client
  │
  ▼ POST /api/chat { "message": "..." }
FastAPI endpoint
  │
  ▼ asyncio.wait_for(..., timeout=300s)
MCPClientManager.process_query(message)
  │
  ▼ Build initial messages: [{"role": "user", "content": message}]
  │
  ┌─────────────── LLM Loop ───────────────────┐
  │                                            │
  ▼ LLMProvider.chat(messages, tools)          │
  │                                            │
  ├─ stop_reason == "end_turn" ──────────────► Break loop
  │                                            │
  ├─ stop_reason == "tool_use"                 │
  │   │                                        │
  │   ▼ For each tool call:                    │
  │   Look up session by tool name             │
  │   session.call_tool(name, args)            │
  │   (calls subprocess MCP server)            │
  │   Collect tool result                      │
  │   Append to messages                       │
  │   └────────────────────────────────────────┘
  │
  ▼ Return { response, tool_calls }
FastAPI endpoint
  │
  ▼ HTTP 200 { "response": "...", "tool_calls": [...] }
Client
```

### 3.2 Prompt Execution Flow (`POST /api/prompts/execute`)

```
Client
  │
  ▼ POST /api/prompts/execute { "prompt_name": "...", "arguments": {...} }
FastAPI endpoint
  │
  ▼ Validate prompt_name exists in available_prompts
MCPClientManager.execute_prompt(name, args)
  │
  ▼ session.get_prompt(name, arguments=args)  ← calls research MCP server subprocess
  │
  ▼ Extract rendered instruction text from prompt.messages[0].content
  │
  ▼ MCPClientManager.process_query(rendered_text)
  │   (enters full LLM ↔ Tool loop, same as chat)
  │
  ▼ Return { prompt_name, response, tool_calls }
Client
```

### 3.3 Paper Metadata Storage

```
LLM calls search_papers("attention mechanisms", max_results=5)
  │
  ▼ research MCP server subprocess
  │
  ▼ arxiv.Client().results(Search(query=topic, max_results=5, sort_by=Relevance))
  │
  ▼ Create dir: papers/attention_mechanisms/
  │
  ▼ Merge into papers/attention_mechanisms/papers_info.json:
    {
      "<paper_id>": {
        "title": "...",
        "authors": [...],
        "summary": "...",
        "pdf_url": "...",
        "published": "YYYY-MM-DD"
      }
    }
  │
  ▼ Return [list of paper IDs] to LLM
```

---

## 4. External Dependencies

### 4.1 Third-Party LLM APIs

| Provider | API Base URL | Auth | SDK |
|----------|-------------|------|-----|
| Groq | `https://api.groq.com` | `GROQ_API_KEY` (Bearer) | `groq` Python SDK |
| Cerebras | `https://api.cerebras.ai` | `CEREBRAS_API_KEY` (Bearer) | `cerebras-cloud-sdk` |
| Anthropic | `https://api.anthropic.com` | `ANTHROPIC_API_KEY` | `anthropic` Python SDK |

Only **one provider** is active at runtime (determined by `LLM_PROVIDER` env var).

### 4.2 arXiv API

- **Used by:** `research_server.py` via `arxiv` Python client
- **Endpoint:** `https://export.arxiv.org/api/query` (called by the `arxiv` library)
- **Auth:** None required (public API)
- **Rate limiting:** The `arxiv` library applies built-in delays
- **Data returned:** Paper title, authors, abstract/summary, PDF URL, publish date

### 4.3 Filesystem MCP Server

- **Package:** `@modelcontextprotocol/server-filesystem` (npm)
- **Launch:** `npx -y @modelcontextprotocol/server-filesystem ./papers`
- **Scope:** Read/write access restricted to the `./papers` directory
- **Runtime requirement:** Node.js must be installed

### 4.4 Fetch MCP Server

- **Package:** `mcp-server-fetch` (PyPI)
- **Launch:** `uvx mcp-server-fetch`
- **Purpose:** Fetches live web pages via HTTP and returns their text content
- **Runtime requirement:** `uvx` (uv package runner) must be installed

---

## 5. Service Communication

### 5.1 Client ↔ FastAPI

- **Protocol:** HTTP/1.1 (REST)
- **Format:** JSON
- **CORS:** Fully open (`*`)
- **Transport:** TCP (default port 8000)

### 5.2 FastAPI ↔ MCP Servers

- **Protocol:** MCP over **stdio** (standard input/output)
- **Transport:** Each MCP server is a **child subprocess** launched by the FastAPI process
- **Session management:** `mcp.ClientSession` with `AsyncExitStack` for lifecycle management
- **Communication:** JSON-RPC messages over stdin/stdout pipes between FastAPI and each subprocess

### 5.3 LLM Loop Message Format (Internal)

Messages use an **Anthropic-style** internal format:
- User messages: `{"role": "user", "content": "string or list of blocks"}`
- Assistant messages: `{"role": "assistant", "content": [{"type": "text", "text": "..."}, {"type": "tool_use", "id": "...", "name": "...", "input": {...}}]}`
- Tool results: `{"role": "user", "content": [{"type": "tool_result", "tool_use_id": "...", "content": [...]}]}`

Groq and Cerebras providers **translate** this to OpenAI format on the way in and normalize the response on the way out.

---

## 6. Deployment Architecture

### 6.1 Current (Development)

```
Single machine
├── Python process: uvicorn app.main:app --reload
│   ├── FastAPI ASGI app
│   └── MCPClientManager (singleton)
│       ├── Subprocess: python research_server.py  (research MCP)
│       ├── Subprocess: npx @modelcontextprotocol/server-filesystem ./papers  (filesystem MCP)
│       └── Subprocess: uvx mcp-server-fetch  (fetch MCP)
└── ./papers/           ← file-based data store
    └── <topic>/
        └── papers_info.json
```

**Start command:**
```bash
uvicorn app.main:app --reload
```

**Default URL:** `http://127.0.0.1:8000`

### 6.2 Runtime Requirements

| Requirement | Purpose |
|-------------|---------|
| Python 3.11+ | FastAPI, research_server.py |
| `.venv` Python (virtual env) | Used to launch `research_server.py` subprocess |
| Node.js + npx | Required to run the filesystem MCP server |
| `uvx` (uv tool runner) | Required to run the fetch MCP server |
| Valid LLM API key | At least one of Groq / Cerebras / Anthropic |

### 6.3 Environment Variables Required for Startup

```
LLM_PROVIDER=groq            # or cerebras or anthropic
GROQ_API_KEY=sk-...          # if LLM_PROVIDER=groq
CEREBRAS_API_KEY=...         # if LLM_PROVIDER=cerebras
ANTHROPIC_API_KEY=sk-ant-... # if LLM_PROVIDER=anthropic
```

### 6.4 Production Considerations (Not Implemented, Reference Only)

> The following are **not implemented** in the current codebase. They are recommendations for a production deployment.

- **Process manager:** Use `gunicorn` with `uvicorn` workers, or a systemd service
- **Reverse proxy:** Nginx or Caddy in front of uvicorn
- **CORS hardening:** Replace `allow_origins=["*"]` with specific frontend origin(s)
- **Authentication:** Add JWT middleware (see AUTHENTICATION.md)
- **File storage:** Replace local `papers/` with object storage (S3, GCS) for multi-instance deployments
- **Secrets management:** Use environment-level secrets (Docker secrets, AWS Secrets Manager) instead of `.env` files
- **Containerization:** Dockerfile would need to install Python, Node.js, and `uvx`
- **Health checks:** The `GET /` endpoint can be used as an HTTP health probe
