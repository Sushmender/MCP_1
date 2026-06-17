# Error Handling

> This document describes every category of error this backend can produce, including the HTTP status code, error format, trigger conditions, and JSON examples. Use this to build a robust frontend error handling layer.

---

## Table of Contents

1. [Global Error Format](#1-global-error-format)
2. [Validation Errors (422)](#2-validation-errors-422)
3. [Authentication & Configuration Errors](#3-authentication--configuration-errors)
4. [Service Unavailable Errors (503)](#4-service-unavailable-errors-503)
5. [Not Found Errors (404)](#5-not-found-errors-404)
6. [Timeout Errors (408)](#6-timeout-errors-408)
7. [Server Errors (500)](#7-server-errors-500)
8. [Silent Error — LLM Not Configured (200)](#8-silent-error--llm-not-configured-200)
9. [Frontend Error Handling Strategy](#9-frontend-error-handling-strategy)

---

## 1. Global Error Format

All HTTP errors from this FastAPI backend follow a consistent structure:

```json
{
  "detail": "Human-readable error message as a string"
}
```

> **Exception:** 422 Validation errors have an array format — see [Section 2](#2-validation-errors-422).

**HTTP Error Status Codes Used by This Backend:**

| Status Code | Name | When It Occurs |
|-------------|------|----------------|
| `408` | Request Timeout | Chat/prompt took longer than `PROMPT_TIMEOUT_SECS` |
| `404` | Not Found | Prompt name not found; Resource URI not found |
| `422` | Unprocessable Entity | Request body fails Pydantic schema validation |
| `500` | Internal Server Error | Unexpected Python exception |
| `503` | Service Unavailable | MCP Client not initialized (startup failure) |

---

## 2. Validation Errors (422)

**Trigger:** The request body does not match the expected Pydantic schema (e.g., missing required field, wrong type).

**Which Endpoints:** `POST /api/chat`, `POST /api/prompts/execute`

### Example: Missing `message` field in `/api/chat`

**Request:**
```http
POST /api/chat
Content-Type: application/json

{}
```

**Response:**
```json
HTTP 422 Unprocessable Entity

{
  "detail": [
    {
      "type": "missing",
      "loc": ["body", "message"],
      "msg": "Field required",
      "input": {},
      "url": "https://errors.pydantic.dev/2.6/v/missing"
    }
  ]
}
```

### Example: Missing `prompt_name` in `/api/prompts/execute`

**Request:**
```http
POST /api/prompts/execute
Content-Type: application/json

{ "arguments": { "topic": "RAG" } }
```

**Response:**
```json
HTTP 422 Unprocessable Entity

{
  "detail": [
    {
      "type": "missing",
      "loc": ["body", "prompt_name"],
      "msg": "Field required",
      "input": { "arguments": { "topic": "RAG" } },
      "url": "https://errors.pydantic.dev/2.6/v/missing"
    }
  ]
}
```

### Frontend Handling
- Parse `error.detail` as an array
- Map each item's `loc` (location path) and `msg` (message) to field-level error display
- Show inline error under the relevant form field

---

## 3. Authentication & Configuration Errors

> These are **not HTTP 401/403 errors** because the backend has no client authentication. These are **backend-side LLM misconfiguration** issues surfaced as either HTTP 200 (silent) or HTTP 500 (crash).

### 3.1 Missing or Placeholder LLM API Key

**When:** The server starts with an invalid or placeholder API key (e.g., `GROQ_API_KEY=your_groq_api_key_here`).

**Effect:** `get_llm_provider()` raises `ValueError`. The LLM is set to `None`. The app still starts.

**Surfaced as HTTP 200** (not an error response — see [Section 8](#8-silent-error--llm-not-configured-200)):

```json
{
  "response": "LLM provider is not configured. Check your .env settings.",
  "tool_calls": []
}
```

### 3.2 Unsupported LLM Provider

**When:** `LLM_PROVIDER` is set to an unknown value (e.g., `LLM_PROVIDER=openai`).

**Effect:** Same as above — `ValueError` during startup, LLM is `None`.

**Startup log message:**
```
[Warning] Unsupported LLM_PROVIDER='openai'. Supported values: 'cerebras', 'groq', 'anthropic'.
```

---

## 4. Service Unavailable Errors (503)

**Trigger:** `MCPClientManager` failed to initialize during application startup (e.g., `server_config.json` not found, subprocess failed to launch).

**Which Endpoints:** All `/api/*` endpoints

**Response:**
```json
HTTP 503 Service Unavailable

{
  "detail": "MCP Client is not initialized."
}
```

### Frontend Handling
- This indicates a **backend server startup failure** — the service is broken, not the request
- Show a full-page error state: *"The research service is temporarily unavailable. Please try again later or contact support."*
- Do not allow the user to retry individual requests — the entire backend needs attention
- Consider showing a maintenance banner

---

## 5. Not Found Errors (404)

### 5.1 Unknown Prompt Name

**Trigger:** `prompt_name` in `POST /api/prompts/execute` does not match any registered prompt.

**Response:**
```json
HTTP 404 Not Found

{
  "detail": "Prompt 'nonexistent_prompt' not found. Available: ['compare_papers', 'find_and_summarize', 'summarize_paper']"
}
```

**Frontend Handling:**
- The available prompt names are dynamic (fetched from `GET /api/prompts`)
- Validate `prompt_name` against the list from `GET /api/prompts` before calling execute
- If this 404 is somehow still returned, show: *"This research workflow is not available. Please refresh the page."*

### 5.2 Unknown Resource URI

**Trigger:** `uri` parameter in `GET /api/resources/read` does not match any registered resource.

**Response:**
```json
HTTP 404 Not Found

{
  "detail": "Resource 'papers://unknown_topic/info' not found."
}
```

**Frontend Handling:**
- Show: *"No papers found for this topic. Try searching for papers first using the chat."*
- For `papers://list`, this should never 404 — the resource always exists (returns `{}` if empty)

---

## 6. Timeout Errors (408)

**Trigger:** Chat or prompt execution exceeds `PROMPT_TIMEOUT_SECS` (default: 300 seconds).

**Which Endpoints:** `POST /api/chat`, `POST /api/prompts/execute`

### 6.1 Chat Timeout

```json
HTTP 408 Request Timeout

{
  "detail": "Request timed out after 300s. Paper searches involve multiple LLM + ArXiv calls — try a simpler query or increase PROMPT_TIMEOUT_SECS in your .env file."
}
```

### 6.2 Prompt Execution Timeout

```json
HTTP 408 Request Timeout

{
  "detail": "Prompt 'compare_papers' timed out after 300s. Tip: for 'compare_papers', make sure both paper IDs are already stored locally (run a /chat search first), or pass IDs that exist in papers/ on disk."
}
```

### Frontend Handling
- Show a friendly timeout message with the specific tip extracted from `error.detail`
- For the chat interface: *"This query took too long. Try asking about fewer papers, or search for a specific topic with fewer results."*
- For compare_papers specifically: *"Paper comparison timed out. Try searching for these papers individually via chat first, then retry the comparison."*
- Offer a "Try again" button
- Consider surfacing the tip text from `detail` directly to the user since it contains actionable advice

---

## 7. Server Errors (500)

**Trigger:** Unexpected exception — LLM API returns an unexpected error, tool execution fails, MCP subprocess crashes, network failure to LLM API, etc.

**Which Endpoints:** `POST /api/chat`, `POST /api/prompts/execute`, `GET /api/resources/read`

### 7.1 Chat Error

```json
HTTP 500 Internal Server Error

{
  "detail": "Error processing chat query: <exception message here>"
}
```

### 7.2 Prompt Execution Error

```json
HTTP 500 Internal Server Error

{
  "detail": "Error executing prompt: <exception message here>"
}
```

### 7.3 Resource Read Error

```json
HTTP 500 Internal Server Error

{
  "detail": "Error reading resource: <exception message here>"
}
```

### 7.4 Common Root Causes

| Root Cause | Example Exception Message | User-Facing Message |
|------------|--------------------------|---------------------|
| Groq API 400 (bad tool schema) | `BadRequestError: 400 ...` | Try a different query |
| LLM provider rate limit | `RateLimitError: 429 ...` | Too many requests, try again in a moment |
| Network failure to LLM API | `ConnectError: ...` | Check internet connection |
| MCP subprocess crashed | `BrokenPipeError: ...` | Service error, may require restart |
| arXiv API failure | `ConnectionError: ...` | arXiv unavailable, try later |

### Frontend Handling
- Show a generic error: *"Something went wrong. Please try again."*
- Log `error.detail` to the browser console for debugging
- Do NOT display raw exception messages to the user (they may contain internal details)
- Offer a "Try again" button

---

## 8. Silent Error — LLM Not Configured (200)

This is a special case: when the LLM is not properly configured, the backend returns **HTTP 200 OK** but with an error message in the `response` field.

**Trigger:** LLM provider API key is missing or invalid.

**Response from `POST /api/chat`:**
```json
HTTP 200 OK

{
  "response": "LLM provider is not configured. Check your .env settings.",
  "tool_calls": []
}
```

### Frontend Handling
- Do not assume HTTP 200 always means success
- Check if `response` contains known error sentinel strings:
  ```javascript
  if (data.response.includes("not configured") && data.tool_calls.length === 0) {
    // Show configuration error
  }
  ```
- Show: *"The AI service is not properly configured. Please contact the administrator."*

---

## 9. Frontend Error Handling Strategy

### Recommended Error Handler (JavaScript/TypeScript)

```typescript
interface ApiError {
  detail: string | ValidationErrorDetail[];
}

interface ValidationErrorDetail {
  type: string;
  loc: (string | number)[];
  msg: string;
}

async function callApi<T>(url: string, options?: RequestInit): Promise<T> {
  let response: Response;
  
  try {
    response = await fetch(url, options);
  } catch (networkError) {
    // Network-level failure (server unreachable)
    throw new Error('Cannot connect to the server. Please check if the backend is running.');
  }

  if (!response.ok) {
    const errorData: ApiError = await response.json().catch(() => ({ detail: 'Unknown error' }));
    
    switch (response.status) {
      case 408:
        throw new TimeoutError(typeof errorData.detail === 'string' ? errorData.detail : 'Request timed out');
      case 404:
        throw new NotFoundError(typeof errorData.detail === 'string' ? errorData.detail : 'Not found');
      case 422:
        throw new ValidationError(Array.isArray(errorData.detail) ? errorData.detail : []);
      case 503:
        throw new ServiceUnavailableError('The research service is temporarily unavailable.');
      case 500:
      default:
        throw new ServerError(typeof errorData.detail === 'string' ? errorData.detail : 'Internal server error');
    }
  }

  return response.json() as Promise<T>;
}
```

### Error Display Matrix

| Error Type | Toast? | Inline? | Full Page? | Retry Button? |
|------------|--------|---------|-----------|---------------|
| 422 Validation | No | Yes (field-level) | No | No |
| 404 Not Found | Yes | No | No | No |
| 408 Timeout | Yes | No | No | Yes |
| 500 Server Error | Yes | No | No | Yes |
| 503 Unavailable | No | No | Yes | No |
| Silent LLM config | No | Yes (in response area) | No | No |
