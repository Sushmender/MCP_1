# API Contract

> **Base URL:** `http://127.0.0.1:8000`  
> **Interactive Docs:** `http://127.0.0.1:8000/docs` (Swagger UI)  
> **Version:** 1.0.0  
> **Authentication:** None required — this backend has no authentication layer. All endpoints are publicly accessible.

---

## Table of Contents

1. [Health Check — `GET /`](#1-health-check)
2. [Chat — `POST /api/chat`](#2-chat)
3. [List Tools — `GET /api/tools`](#3-list-tools)
4. [List Prompts — `GET /api/prompts`](#4-list-prompts)
5. [Execute Prompt — `POST /api/prompts/execute`](#5-execute-prompt)
6. [List Resources — `GET /api/resources`](#6-list-resources)
7. [Read Resource — `GET /api/resources/read`](#7-read-resource)

---

## 1. Health Check

### `GET /`

**Purpose:** Returns a simple health-check payload confirming the service is running.

**Authentication Required:** No

**Headers:**

| Header | Value | Required |
|--------|-------|----------|
| `Accept` | `application/json` | No |

**Request Parameters:** None

**Request Body:** None

**Response Schema:**

```json
{
  "status": "string",
  "service": "string",
  "documentation": "string"
}
```

**Example Request:**

```http
GET / HTTP/1.1
Host: 127.0.0.1:8000
```

**Example Response:**

```json
{
  "status": "healthy",
  "service": "MCP Backend Server",
  "documentation": "/docs"
}
```

**Possible Error Responses:** None — this endpoint never fails under normal conditions.

---

## 2. Chat

### `POST /api/chat`

**Purpose:** Send a free-form natural-language query to the LLM. The model will autonomously decide which MCP tools to call (arXiv search, file system, web fetch, etc.), execute them in a loop, and return a final text response along with a log of every tool call made.

**Authentication Required:** No

**Headers:**

| Header | Value | Required |
|--------|-------|----------|
| `Content-Type` | `application/json` | Yes |
| `Accept` | `application/json` | No |

**Request Parameters:** None (no query params)

**Request Body Schema:**

```json
{
  "message": "string"   // required — the user query
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `message` | `string` | ✅ Yes | Free-form text query sent to the LLM |

**Response Schema:**

```json
{
  "response": "string",
  "tool_calls": [
    {
      "id": "string",
      "name": "string",
      "input": {}
    }
  ]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `response` | `string` | Final plain-text answer from the LLM |
| `tool_calls` | `array` | Ordered list of every tool call the LLM executed during this request |
| `tool_calls[].id` | `string` | Unique ID of the tool call (e.g. `"call_abc123"`) |
| `tool_calls[].name` | `string` | Name of the tool called (e.g. `"search_papers"`, `"fetch"`) |
| `tool_calls[].input` | `object` | Arguments passed to the tool |

**Example Request:**

```http
POST /api/chat HTTP/1.1
Host: 127.0.0.1:8000
Content-Type: application/json

{
  "message": "Find me the top 3 papers on transformer attention mechanisms and summarize them."
}
```

**Example Response:**

```json
{
  "response": "Here are the top 3 papers on transformer attention mechanisms:\n\n1. **Attention Is All You Need** (Vaswani et al., 2017) ...",
  "tool_calls": [
    {
      "id": "call_abc123",
      "name": "search_papers",
      "input": {
        "topic": "transformer attention mechanisms",
        "max_results": 3
      }
    },
    {
      "id": "call_def456",
      "name": "extract_info",
      "input": {
        "paper_id": "1706.03762"
      }
    }
  ]
}
```

**Possible Error Responses:**

| HTTP Status | Condition | Example Body |
|-------------|-----------|--------------|
| `408 Request Timeout` | Request exceeded `PROMPT_TIMEOUT_SECS` (default 300s) | `{"detail": "Request timed out after 300s. Paper searches involve multiple LLM + ArXiv calls — try a simpler query or increase PROMPT_TIMEOUT_SECS in your .env file."}` |
| `500 Internal Server Error` | Unexpected exception in LLM or tool execution | `{"detail": "Error processing chat query: <exception message>"}` |
| `503 Service Unavailable` | MCP Client Manager not initialized (startup failure) | `{"detail": "MCP Client is not initialized."}` |

---

## 3. List Tools

### `GET /api/tools`

**Purpose:** Returns a list of all tools registered across every connected MCP server. Includes name, description, and the full JSON Schema for each tool's input. Useful for the frontend to dynamically render tool documentation or a "capabilities" page.

**Authentication Required:** No

**Headers:**

| Header | Value | Required |
|--------|-------|----------|
| `Accept` | `application/json` | No |

**Request Parameters:** None

**Request Body:** None

**Response Schema:**

```json
{
  "tools": [
    {
      "name": "string",
      "description": "string",
      "input_schema": {
        "type": "object",
        "properties": {},
        "required": []
      }
    }
  ]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `tools` | `array` | All registered tools from all MCP servers |
| `tools[].name` | `string` | Tool identifier used in tool_calls (e.g. `"search_papers"`) |
| `tools[].description` | `string` | Human-readable description of what the tool does |
| `tools[].input_schema` | `object` | JSON Schema (subset: `type`, `description`, `properties`, `required`, `items`, `enum`) |

**Example Request:**

```http
GET /api/tools HTTP/1.1
Host: 127.0.0.1:8000
```

**Example Response:**

```json
{
  "tools": [
    {
      "name": "search_papers",
      "description": "Search for papers on arXiv based on a topic and store their information.",
      "input_schema": {
        "type": "object",
        "properties": {
          "topic": {
            "type": "string",
            "description": "The topic to search for (e.g. 'attention mechanisms')."
          },
          "max_results": {
            "type": "integer",
            "description": "Maximum number of results to retrieve (default: 5)."
          }
        },
        "required": ["topic"]
      }
    },
    {
      "name": "extract_info",
      "description": "Retrieve stored metadata for a specific paper by its arXiv ID.",
      "input_schema": {
        "type": "object",
        "properties": {
          "paper_id": {
            "type": "string",
            "description": "The short arXiv ID of the paper (e.g. '2301.01234')."
          }
        },
        "required": ["paper_id"]
      }
    },
    {
      "name": "fetch",
      "description": "Fetch content from a web URL.",
      "input_schema": {
        "type": "object",
        "properties": {
          "url": {
            "type": "string",
            "description": "The URL to fetch."
          }
        },
        "required": ["url"]
      }
    }
  ]
}
```

> **Note:** The filesystem MCP server (`@modelcontextprotocol/server-filesystem`) also registers tools such as `read_file`, `write_file`, `list_directory`, `create_directory`, `move_file`, `search_files`, `get_file_info`, and `list_allowed_directories`. The exact set depends on the SDK version at runtime.

**Possible Error Responses:**

| HTTP Status | Condition | Example Body |
|-------------|-----------|--------------|
| `503 Service Unavailable` | MCP Client Manager not initialized | `{"detail": "MCP Client is not initialized."}` |

---

## 4. List Prompts

### `GET /api/prompts`

**Purpose:** Returns all named prompt templates registered by MCP servers. Each prompt has a name, description, and the arguments it accepts. Use these to drive the `POST /api/prompts/execute` endpoint.

**Authentication Required:** No

**Headers:**

| Header | Value | Required |
|--------|-------|----------|
| `Accept` | `application/json` | No |

**Request Parameters:** None

**Request Body:** None

**Response Schema:**

```json
{
  "prompts": [
    {
      "name": "string",
      "description": "string",
      "arguments": [
        {
          "name": "string",
          "description": "string",
          "required": true
        }
      ]
    }
  ]
}
```

**Example Request:**

```http
GET /api/prompts HTTP/1.1
Host: 127.0.0.1:8000
```

**Example Response:**

```json
{
  "prompts": [
    {
      "name": "summarize_paper",
      "description": "Generate a prompt that instructs the LLM to summarize a stored paper.",
      "arguments": [
        {
          "name": "paper_id",
          "description": "The short arXiv ID of the paper to summarize.",
          "required": true
        }
      ]
    },
    {
      "name": "compare_papers",
      "description": "Generate a prompt that instructs the LLM to compare two stored papers.",
      "arguments": [
        {
          "name": "paper_id_1",
          "description": "arXiv ID of the first paper.",
          "required": true
        },
        {
          "name": "paper_id_2",
          "description": "arXiv ID of the second paper.",
          "required": true
        }
      ]
    },
    {
      "name": "find_and_summarize",
      "description": "Generate a prompt that instructs the LLM to search for papers on a topic and then summarize the top results.",
      "arguments": [
        {
          "name": "topic",
          "description": "The research topic to search for.",
          "required": true
        },
        {
          "name": "max_results",
          "description": "How many papers to fetch and summarize (default: 3).",
          "required": false
        }
      ]
    }
  ]
}
```

**Possible Error Responses:**

| HTTP Status | Condition | Example Body |
|-------------|-----------|--------------|
| `503 Service Unavailable` | MCP Client Manager not initialized | `{"detail": "MCP Client is not initialized."}` |

---

## 5. Execute Prompt

### `POST /api/prompts/execute`

**Purpose:** Execute a named MCP prompt template. The server renders the prompt with your arguments, then pipes the resulting instruction string through the LLM (which may call tools), and returns the final response. This is the high-level research workflow endpoint.

**Authentication Required:** No

**Headers:**

| Header | Value | Required |
|--------|-------|----------|
| `Content-Type` | `application/json` | Yes |
| `Accept` | `application/json` | No |

**Request Parameters:** None

**Request Body Schema:**

```json
{
  "prompt_name": "string",
  "arguments": {}
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `prompt_name` | `string` | ✅ Yes | Name of the prompt to execute (must match a value from `GET /api/prompts`) |
| `arguments` | `object` | No | Key-value pairs matching the prompt's declared arguments |

**Available Prompts and Their Arguments:**

| `prompt_name` | Required Arguments | Optional Arguments |
|---------------|-------------------|--------------------|
| `summarize_paper` | `paper_id` (string) | — |
| `compare_papers` | `paper_id_1` (string), `paper_id_2` (string) | — |
| `find_and_summarize` | `topic` (string) | `max_results` (integer, default: 3) |

**Response Schema:**

```json
{
  "prompt_name": "string",
  "response": "string",
  "tool_calls": [
    {
      "id": "string",
      "name": "string",
      "input": {}
    }
  ]
}
```

**Example Requests:**

*Summarize a single paper:*
```http
POST /api/prompts/execute HTTP/1.1
Host: 127.0.0.1:8000
Content-Type: application/json

{
  "prompt_name": "summarize_paper",
  "arguments": { "paper_id": "1706.03762" }
}
```

*Compare two papers:*
```http
POST /api/prompts/execute HTTP/1.1
Host: 127.0.0.1:8000
Content-Type: application/json

{
  "prompt_name": "compare_papers",
  "arguments": {
    "paper_id_1": "1706.03762",
    "paper_id_2": "2005.14165"
  }
}
```

*Search and summarize by topic:*
```http
POST /api/prompts/execute HTTP/1.1
Host: 127.0.0.1:8000
Content-Type: application/json

{
  "prompt_name": "find_and_summarize",
  "arguments": { "topic": "RAG", "max_results": 3 }
}
```

**Example Response:**

```json
{
  "prompt_name": "summarize_paper",
  "response": "**Summary of '1706.03762' — Attention Is All You Need**\n\nThis paper introduces the Transformer architecture...",
  "tool_calls": [
    {
      "id": "call_xyz789",
      "name": "extract_info",
      "input": { "paper_id": "1706.03762" }
    }
  ]
}
```

**Possible Error Responses:**

| HTTP Status | Condition | Example Body |
|-------------|-----------|--------------|
| `404 Not Found` | `prompt_name` does not exist | `{"detail": "Prompt 'unknown_prompt' not found. Available: ['compare_papers', 'find_and_summarize', 'summarize_paper']"}` |
| `408 Request Timeout` | Prompt execution exceeded timeout | `{"detail": "Prompt 'compare_papers' timed out after 300s. Tip: for 'compare_papers', make sure both paper IDs are already stored locally..."}` |
| `500 Internal Server Error` | Unexpected error during execution | `{"detail": "Error executing prompt: <exception message>"}` |
| `503 Service Unavailable` | MCP Client not initialized | `{"detail": "MCP Client is not initialized."}` |

---

## 6. List Resources

### `GET /api/resources`

**Purpose:** Returns all static resources and URI template resources registered by MCP servers. Static resources have a fixed URI; template resources have URI patterns with variable placeholders. Read a specific resource with `GET /api/resources/read`.

**Authentication Required:** No

**Headers:**

| Header | Value | Required |
|--------|-------|----------|
| `Accept` | `application/json` | No |

**Request Parameters:** None

**Request Body:** None

**Response Schema:**

```json
{
  "resources": [
    {
      "uri": "string",
      "name": "string",
      "description": "string",
      "mime_type": "string"
    }
  ],
  "resource_templates": [
    {
      "uri_template": "string",
      "name": "string",
      "description": "string",
      "mime_type": "string"
    }
  ]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `resources` | `array` | Static resources with fixed URIs |
| `resources[].uri` | `string` | Exact URI to use when calling `GET /api/resources/read` |
| `resource_templates` | `array` | Parameterized resources; substitute path variables before reading |
| `resource_templates[].uri_template` | `string` | URI pattern with `{param}` placeholders |

**Example Request:**

```http
GET /api/resources HTTP/1.1
Host: 127.0.0.1:8000
```

**Example Response:**

```json
{
  "resources": [
    {
      "uri": "papers://list",
      "name": "list_stored_papers",
      "description": "List all paper IDs stored locally, grouped by topic.",
      "mime_type": "application/json"
    }
  ],
  "resource_templates": [
    {
      "uri_template": "papers://{topic}/info",
      "name": "get_topic_papers",
      "description": "Return all stored paper metadata for a given topic.",
      "mime_type": "application/json"
    }
  ]
}
```

**Possible Error Responses:**

| HTTP Status | Condition | Example Body |
|-------------|-----------|--------------|
| `503 Service Unavailable` | MCP Client not initialized | `{"detail": "MCP Client is not initialized."}` |

---

## 7. Read Resource

### `GET /api/resources/read`

**Purpose:** Read the raw content of a specific resource by its fully resolved URI. For template resources, substitute path variables before calling this endpoint (e.g. replace `{topic}` with the actual topic name).

**Authentication Required:** No

**Headers:**

| Header | Value | Required |
|--------|-------|----------|
| `Accept` | `application/json` | No |

**Request Parameters (Query String):**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `uri` | `string` | ✅ Yes | Fully resolved resource URI (e.g. `papers://list`, `papers://attention_mechanisms/info`) |

**Request Body:** None

**Response Schema:**

```json
{
  "uri": "string",
  "content": "string"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `uri` | `string` | Echo of the requested URI |
| `content` | `string` | Raw resource content (typically JSON-encoded string) |

**Example Requests:**

*List all stored topics and paper IDs:*
```http
GET /api/resources/read?uri=papers://list HTTP/1.1
Host: 127.0.0.1:8000
```

*Get all papers for a specific topic:*
```http
GET /api/resources/read?uri=papers://transformer_attention_mechanisms/info HTTP/1.1
Host: 127.0.0.1:8000
```

**Example Response (for `papers://list`):**

```json
{
  "uri": "papers://list",
  "content": "{\n  \"transformer_attention_mechanisms\": [\n    \"1706.03762\",\n    \"2005.14165\"\n  ],\n  \"rag\": [\n    \"2005.11401\"\n  ]\n}"
}
```

**Example Response (for `papers://transformer_attention_mechanisms/info`):**

```json
{
  "uri": "papers://transformer_attention_mechanisms/info",
  "content": "{\n  \"1706.03762\": {\n    \"title\": \"Attention Is All You Need\",\n    \"authors\": [\"Ashish Vaswani\", \"Noam Shazeer\"],\n    \"summary\": \"The dominant sequence transduction models...\",\n    \"pdf_url\": \"https://arxiv.org/pdf/1706.03762v5\",\n    \"published\": \"2017-06-12\"\n  }\n}"
}
```

**Possible Error Responses:**

| HTTP Status | Condition | Example Body |
|-------------|-----------|--------------|
| `404 Not Found` | Resource URI does not exist or is unknown | `{"detail": "Resource 'papers://unknown_topic/info' not found."}` |
| `500 Internal Server Error` | Error reading resource content | `{"detail": "Error reading resource: <exception message>"}` |
| `503 Service Unavailable` | MCP Client not initialized | `{"detail": "MCP Client is not initialized."}` |

---

## CORS Policy

The backend is configured with **open CORS** — all origins, methods, and headers are allowed:

```
Access-Control-Allow-Origin: *
Access-Control-Allow-Credentials: true
Access-Control-Allow-Methods: *
Access-Control-Allow-Headers: *
```

This means any frontend (React, Vue, plain HTML) running on any port can call these endpoints directly from the browser without proxy configuration.

---

## Global Error Format

All FastAPI HTTP errors follow this structure:

```json
{
  "detail": "Human-readable error message"
}
```

Validation errors (malformed request body) follow FastAPI's default 422 format:

```json
{
  "detail": [
    {
      "loc": ["body", "field_name"],
      "msg": "field required",
      "type": "value_error.missing"
    }
  ]
}
```
