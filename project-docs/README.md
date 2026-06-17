# 🔬 MCP Research Backend

A production-ready **FastAPI** backend that connects to multiple **Model Context Protocol (MCP)** servers and exposes a unified REST API for AI-powered academic research. The system lets an LLM autonomously search arXiv, manage local paper archives, fetch web content, and read/write files — all orchestrated through the MCP tool-calling loop.

---

## ✨ Features

- **Multi-LLM Support** — Plug-and-play provider switching between **Groq**, **Cerebras**, and **Anthropic**
- **MCP Tool Orchestration** — LLM autonomously calls tools across multiple MCP servers until it produces a final answer
- **arXiv Research Tools** — Search papers, extract metadata, and persist results locally
- **Filesystem Access** — Read/write files in the `papers/` directory via the official MCP filesystem server
- **Web Fetching** — Fetch and read live web pages via the MCP fetch server
- **Reusable Prompts** — Pre-built research prompt templates (summarize, compare, find & summarize)
- **Resource Endpoints** — Browse locally cached papers by topic without calling any tool
- **Interactive API Docs** — Swagger UI available out of the box at `/docs`

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────┐
│                   FastAPI Backend                   │
│  POST /api/chat   GET /api/tools   /api/prompts     │
│  POST /api/prompts/execute   GET /api/resources     │
└───────────────────┬─────────────────────────────────┘
                    │ MCPClientManager
          ┌─────────┼─────────────────┐
          │         │                 │
   ┌──────▼──┐ ┌────▼──────┐ ┌───────▼──┐
   │research │ │filesystem │ │  fetch   │
   │  MCP    │ │  MCP      │ │  MCP     │
   │ server  │ │  server   │ │  server  │
   └──────┬──┘ └────┬──────┘ └───────┬──┘
          │         │                 │
     arXiv API  ./papers dir    HTTP web
```

### Directory Structure

```
MCP_1/
├── app/
│   ├── main.py              # FastAPI app + lifespan (startup/shutdown)
│   ├── config.py            # Settings loaded from .env
│   ├── mcp_client.py        # MCPClientManager — connects to servers, runs LLM loop
│   ├── api/
│   │   └── endpoints.py     # REST endpoints: /chat, /tools, /prompts, /resources
│   ├── llm/
│   │   ├── base.py          # Abstract BaseLLMProvider
│   │   ├── factory.py       # get_llm_provider() factory
│   │   ├── groq_provider.py     # Groq (llama-3.3-70b-versatile, etc.)
│   │   ├── cerebras_provider.py # Cerebras (gpt-oss-120b, etc.)
│   │   └── anthropic_provider.py# Anthropic (claude-3-7-sonnet, etc.)
│   └── schemas/
│       └── chat.py          # Pydantic request/response models
├── research_server.py       # Custom MCP server (tools, resources, prompts)
├── server_config.json       # MCP server process definitions
├── project-docs/            # Frontend integration documentation
│   ├── API-CONTRACT.md      # All endpoints documented in full
│   ├── SYSTEM-ARCHITECTURE.md # High-level design document
│   ├── AUTHENTICATION.md    # Auth status and recommendations
│   ├── BUSINESS-FLOWS.md    # User workflow documentation
│   ├── ERROR-HANDLING.md    # Error reference for frontend
│   ├── FRONTEND-HANDOFF.md  # React developer guide
│   └── README.md            # This file (copy of root README)
├── papers/                  # Auto-created; stores downloaded paper metadata
│   └── <topic>/
│       └── papers_info.json
├── docs/                    # Learning notebooks & walkthroughs
├── requirements.txt
├── .env.example             # Copy to .env and fill in your keys
└── .gitignore
```

---

## 🚀 Quick Start

### 1. Clone & enter the project

```bash
git clone <your-repo-url>
cd MCP_1
```

### 2. Create and activate a virtual environment

```bash
# Windows
python -m venv .venv
.venv\Scripts\activate

# macOS / Linux
python -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

```bash
# Copy the example file
copy .env.example .env    # Windows
cp .env.example .env      # macOS / Linux
```

Open `.env` and fill in **at minimum** the LLM provider and API key you want to use:

```env
# Choose one: cerebras | groq | anthropic
LLM_PROVIDER=groq

# Groq
GROQ_API_KEY=your_groq_api_key_here
GROQ_MODEL=llama-3.3-70b-versatile

# Cerebras (optional)
CEREBRAS_API_KEY=your_cerebras_api_key_here
CEREBRAS_MODEL=gpt-oss-120b

# Anthropic (optional)
ANTHROPIC_API_KEY=your_anthropic_api_key_here
ANTHROPIC_MODEL=claude-3-7-sonnet-20250219
```

> **Get free API keys:**
> - [Groq](https://console.groq.com/) — fast, generous free tier
> - [Cerebras](https://cloud.cerebras.ai/) — ultra-fast inference
> - [Anthropic](https://console.anthropic.com/) — Claude models

### 5. Start the server

```bash
uvicorn app.main:app --reload
```

The server starts at **http://127.0.0.1:8000**.

On startup you will see the MCP servers connecting and registering their tools:

```
Initializing MCP Client Manager and connecting to servers...
[LLM] Provider: GROQ  |  Model: llama-3.3-70b-versatile
[LLM] Provider initialized successfully.
Connecting to MCP Server 'research'...
Connected to 'research' successfully. Registered tools: ['search_papers', 'extract_info']
Connecting to MCP Server 'filesystem'...
Connected to 'filesystem' successfully. Registered tools: [...]
Connecting to MCP Server 'fetch'...
Connected to 'fetch' successfully. Registered tools: ['fetch']
INFO:     Application startup complete.
```

---

## 📡 API Reference

Interactive Swagger UI: **http://127.0.0.1:8000/docs**

### `POST /api/chat`
Send any free-form query. The LLM decides which tools to call.

```json
// Request
{ "message": "Find me the top 3 papers on transformer attention mechanisms and summarize them." }

// Response
{
  "response": "Here are the top 3 papers on transformer attention mechanisms...",
  "tool_calls": [
    { "id": "call_abc", "name": "search_papers", "input": { "topic": "transformer attention mechanisms", "max_results": 3 } },
    { "id": "call_def", "name": "extract_info",  "input": { "paper_id": "2301.01234" } }
  ]
}
```

### `GET /api/tools`
List all tools registered across every connected MCP server.

### `GET /api/prompts`
List all named prompts available (e.g. `summarize_paper`, `compare_papers`, `find_and_summarize`).

### `POST /api/prompts/execute`
Execute a named MCP prompt template and pipe its output through the LLM.

```json
// Summarize a single paper
{ "prompt_name": "summarize_paper", "arguments": { "paper_id": "2301.01234" } }

// Compare two papers
{ "prompt_name": "compare_papers", "arguments": { "paper_id_1": "2301.01234", "paper_id_2": "2302.05678" } }

// Search and summarize a topic
{ "prompt_name": "find_and_summarize", "arguments": { "topic": "RAG", "max_results": 3 } }
```

### `GET /api/resources`
List all static resources and URI templates registered by MCP servers.

### `GET /api/resources/read?uri=<uri>`
Read a specific resource by its URI.

```
GET /api/resources/read?uri=papers://list
GET /api/resources/read?uri=papers://transformer_attention_mechanisms/info
```

---

## 🔧 MCP Servers

The backend connects to three MCP servers defined in [`server_config.json`](server_config.json):

| Server | Command | Provides |
|--------|---------|----------|
| **research** | `python research_server.py` | `search_papers`, `extract_info` tools; `papers://list` resource; 3 prompts |
| **filesystem** | `npx @modelcontextprotocol/server-filesystem ./papers` | Full file read/write access to the `papers/` directory |
| **fetch** | `uvx mcp-server-fetch` | `fetch` tool — retrieves live web pages |

### Research Server Tools

| Tool | Description |
|------|-------------|
| `search_papers(topic, max_results=5)` | Searches arXiv, stores metadata in `papers/<topic>/papers_info.json`, returns list of paper IDs |
| `extract_info(paper_id)` | Looks up stored metadata for a given arXiv paper ID |

### Research Server Resources

| URI | Description |
|-----|-------------|
| `papers://list` | JSON map of all stored topics → paper IDs |
| `papers://{topic}/info` | Full metadata for all papers under a given topic |

### Research Server Prompts

| Prompt | Args | Description |
|--------|------|-------------|
| `summarize_paper` | `paper_id` | Generates instructions to summarize a paper |
| `compare_papers` | `paper_id_1`, `paper_id_2` | Generates instructions to compare two papers |
| `find_and_summarize` | `topic`, `max_results=3` | Generates instructions to search and summarize |

---

## 🤖 LLM Providers

Switch providers at any time by changing `LLM_PROVIDER` in your `.env` file and restarting.

| Provider | `LLM_PROVIDER` value | Default Model | Notes |
|----------|---------------------|---------------|-------|
| **Groq** | `groq` | `llama-3.3-70b-versatile` | Fast inference, good tool-calling |
| **Cerebras** | `cerebras` | `gpt-oss-120b` | Ultra-fast, best for long contexts |
| **Anthropic** | `anthropic` | `claude-3-7-sonnet-20250219` | Best reasoning, native tool-calling |

All providers implement [`BaseLLMProvider`](app/llm/base.py) and return the same normalized response format, so the rest of the system is completely provider-agnostic.

---

## ⚙️ Configuration Reference

All settings live in `.env` (copy from `.env.example`):

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_PROVIDER` | `cerebras` | Active provider: `cerebras`, `groq`, or `anthropic` |
| `GROQ_API_KEY` | — | Your Groq API key |
| `GROQ_MODEL` | `llama-3.3-70b-versatile` | Groq model name |
| `CEREBRAS_API_KEY` | — | Your Cerebras API key |
| `CEREBRAS_MODEL` | `gpt-oss-120b` | Cerebras model name |
| `ANTHROPIC_API_KEY` | — | Your Anthropic API key |
| `ANTHROPIC_MODEL` | `claude-3-7-sonnet-20250219` | Anthropic model name |
| `HOST` | `127.0.0.1` | Uvicorn bind address |
| `PORT` | `8000` | Uvicorn port |
| `LOG_LEVEL` | `info` | Uvicorn log level |
| `PROMPT_TIMEOUT_SECS` | `300` | Max seconds for a prompt/chat request |
| `SERVER_CONFIG_PATH` | `server_config.json` | Path to MCP server definitions |

---

## 📦 Dependencies

| Package | Purpose |
|---------|---------|
| `fastapi` | Web framework |
| `uvicorn` | ASGI server |
| `mcp` | Model Context Protocol SDK (client + server) |
| `arxiv` | arXiv API client |
| `groq` | Groq Python SDK |
| `cerebras-cloud-sdk` | Cerebras Python SDK |
| `anthropic` | Anthropic Python SDK |
| `python-dotenv` | `.env` file loading |
| `pydantic` | Request/response validation |
| `nest-asyncio` | Async loop compatibility |

---

## 🛠️ Development Tips

**Hot reload** is enabled by default with `--reload`. Any changes to Python files will automatically restart the server.

**View all available tools at runtime:**
```bash
curl http://127.0.0.1:8000/api/tools
```

**Increase timeout for complex queries** (e.g., comparing papers that haven't been cached yet):
```env
PROMPT_TIMEOUT_SECS=600
```

**Papers are cached locally** in `papers/<topic>/papers_info.json`. Subsequent queries for the same topic are faster since metadata is already on disk.

---

## 📚 Frontend Integration Documentation

The `project-docs/` folder contains comprehensive documentation for frontend developers:

| Document | Description |
|----------|-------------|
| [API-CONTRACT.md](./API-CONTRACT.md) | Every endpoint with full request/response schemas and examples |
| [SYSTEM-ARCHITECTURE.md](./SYSTEM-ARCHITECTURE.md) | High-level system design and component breakdown |
| [AUTHENTICATION.md](./AUTHENTICATION.md) | Auth status (no auth required) and recommendations |
| [BUSINESS-FLOWS.md](./BUSINESS-FLOWS.md) | User workflows with API calls and backend processing |
| [ERROR-HANDLING.md](./ERROR-HANDLING.md) | All error codes, formats, and frontend handling strategies |
| [FRONTEND-HANDOFF.md](./FRONTEND-HANDOFF.md) | React developer guide: pages, state, API client setup |
