# Frontend Handoff Guide

> **For:** React Frontend Developer  
> **Backend:** MCP Research Backend (FastAPI)  
> **Base URL:** `http://127.0.0.1:8000`  
> **Auth:** None required  
> **CORS:** Fully open — direct browser fetch works without proxy

---

## Table of Contents

1. [Quick Start](#1-quick-start)
2. [Required Pages / Screens](#2-required-pages--screens)
3. [Required API Integrations](#3-required-api-integrations)
4. [UI Expectations](#4-ui-expectations)
5. [Authentication Flow](#5-authentication-flow)
6. [State Management Requirements](#6-state-management-requirements)
7. [Important Frontend Considerations](#7-important-frontend-considerations)
8. [Recommended Tech Stack](#8-recommended-tech-stack)
9. [API Client Setup (Axios Example)](#9-api-client-setup-axios-example)
10. [Smart Query Box — Prefix Routing](#10-smart-query-box--prefix-routing)

---

## 1. Quick Start

### Confirm Backend is Running
```bash
curl http://127.0.0.1:8000/
# Expected: {"status":"healthy","service":"MCP Backend Server","documentation":"/docs"}
```

### No Environment Variables Needed on Frontend
The frontend does not need any LLM API keys. All keys are backend-only. The only frontend configuration needed:

```env
# .env (React / Vite)
VITE_API_BASE_URL=http://127.0.0.1:8000
```

---

## 2. Required Pages / Screens

### Page 1: Chat Interface (`/` or `/chat`)

**Purpose:** Primary interface for free-form AI-powered research queries.

**Required Elements:**
- Chat message thread (scrollable, user messages on right, AI responses on left)
- Text input area (multi-line, supports Enter to submit)
- Send button with loading state
- Tool calls log — collapsible section below each AI response showing which MCP tools were used
- Empty state: *"Ask me anything about academic research. I can search arXiv, summarize papers, compare studies, and browse the web."*

**UX Requirements:**
- Disable input while loading (queries can take 10–120+ seconds)
- Show a spinner + message: *"Searching and analyzing papers…"*
- Render AI response as Markdown (use `react-markdown` or similar)
- Auto-scroll to the bottom on new message

---

### Page 2: Research Workflows (`/workflows`)

**Purpose:** Guided forms for the three named research workflows.

**Sections:**

**A. Summarize Paper**
- Input: "arXiv Paper ID" (text field, required)
- Submit button: "Summarize"
- Result: Markdown-rendered LLM response

**B. Compare Two Papers**
- Input 1: "Paper ID 1" (text field, required)
- Input 2: "Paper ID 2" (text field, required)
- Submit button: "Compare"
- Helper text: *"Note: Both papers must be searchable. This may take several minutes."*
- Result: Markdown-rendered LLM response

**C. Find & Summarize by Topic**
- Input: "Research Topic" (text field, required, e.g., "diffusion models")
- Input: "Number of Papers" (number field, optional, default: 3, range: 1–10)
- Submit button: "Search & Summarize"
- Result: Markdown-rendered LLM response

---

### Page 3: Paper Library (`/library`)

**Purpose:** Browse locally cached papers without making LLM calls.

**Required Elements:**
- Topic cards grid — each topic shown as a card with topic name + paper count
- On click: expand to show paper list
- Each paper entry: title, authors, published date, abstract (truncated), "View PDF" link
- Empty state: *"No papers cached yet. Use the chat to search for papers first."*

**Data Source:**
1. `GET /api/resources/read?uri=papers://list` → topic map
2. For each topic: `GET /api/resources/read?uri=papers://<topic>/info` → paper metadata

---

### Page 4: System Capabilities (`/capabilities`)

**Purpose:** Documentation page showing what the AI can do.

**Required Elements:**
- Tools list — fetched from `GET /api/tools`, displayed as cards (tool name + description + parameters)
- Prompts list — fetched from `GET /api/prompts`, with argument descriptions
- Resources section — fetched from `GET /api/resources`, showing available data URIs

---

### Page 5: Error / Status Page

**Purpose:** Full-page fallback for critical backend failures.

**Triggers:** HTTP 503 from any endpoint.

**Content:**
- Title: "Service Unavailable"
- Message: *"The research backend is currently offline. Please try again later."*
- Retry button that re-checks `GET /`

---

## 3. Required API Integrations

### Summary Table

| Page | Endpoint | Method | Trigger |
|------|----------|--------|---------|
| Chat | `/api/chat` | `POST` | User sends message |
| Workflows / Summarize | `/api/prompts/execute` | `POST` | Form submit |
| Workflows / Compare | `/api/prompts/execute` | `POST` | Form submit |
| Workflows / Find & Summarize | `/api/prompts/execute` | `POST` | Form submit |
| Library — topics | `/api/resources/read?uri=papers://list` | `GET` | Page load |
| Library — papers | `/api/resources/read?uri=papers://{topic}/info` | `GET` | Topic click |
| Capabilities — tools | `/api/tools` | `GET` | Page load |
| Capabilities — prompts | `/api/prompts` | `GET` | Page load |
| Capabilities — resources | `/api/resources` | `GET` | Page load |
| Status check | `/` | `GET` | App startup / error page |

### Critical: Parse `content` as JSON String

The `GET /api/resources/read` response returns `content` as a **JSON-encoded string**, not an object:

```json
{
  "uri": "papers://list",
  "content": "{\"attention_mechanisms\": [\"1706.03762\"]}"
}
```

You must `JSON.parse(response.content)` to get the actual data:

```typescript
const raw = await api.get(`/api/resources/read?uri=papers://list`);
const topics = JSON.parse(raw.data.content); // { "attention_mechanisms": ["1706.03762"] }
```

---

## 4. UI Expectations

### Loading States
Every async operation needs a loading indicator. Suggested messages:

| Operation | Loading Message |
|-----------|----------------|
| `POST /api/chat` | "Thinking… the AI is searching and analyzing papers" |
| `POST /api/prompts/execute` (summarize) | "Summarizing paper…" |
| `POST /api/prompts/execute` (compare) | "Comparing papers… this may take a few minutes" |
| `POST /api/prompts/execute` (find_and_summarize) | "Searching arXiv and summarizing…" |
| `GET /api/resources/read` | "Loading papers…" |

### Markdown Rendering
All `response` fields from chat and prompt-execute endpoints contain **Markdown** formatted text. Use `react-markdown` with `remark-gfm` for GitHub-flavored Markdown:

```tsx
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

<ReactMarkdown remarkPlugins={[remarkGfm]}>
  {response}
</ReactMarkdown>
```

### Tool Calls Display
The `tool_calls` array shows the AI's reasoning process. Display it as an expandable "Reasoning" section:

```
▼ AI used 3 tools
  🔧 search_papers({ topic: "RAG", max_results: 3 })
  🔧 extract_info({ paper_id: "2005.11401" })
  🔧 extract_info({ paper_id: "2012.04584" })
```

### Timeout Indication
For long-running operations, show an elapsed timer: *"Elapsed: 45s (may take up to 5 minutes for complex comparisons)"*

### PDF Links
Paper metadata includes `pdf_url` (e.g., `https://arxiv.org/pdf/1706.03762v5`). Open in a new tab:

```tsx
<a href={paper.pdf_url} target="_blank" rel="noopener noreferrer">View PDF</a>
```

---

## 5. Authentication Flow

**There is no authentication required.** See [AUTHENTICATION.md](./AUTHENTICATION.md) for full details.

**Frontend impact:**
- No login page needed
- No token storage needed
- No auth headers needed on any request
- All routes are publicly accessible

---

## 6. State Management Requirements

### Recommended State Shape (Zustand / Redux / Context)

```typescript
interface AppState {
  // Chat
  chatHistory: ChatMessage[];
  isChatLoading: boolean;
  chatError: string | null;
  
  // Current workflow
  workflowResult: WorkflowResult | null;
  isWorkflowLoading: boolean;
  workflowError: string | null;
  
  // Library (cached papers)
  topicMap: Record<string, string[]> | null;  // topic → paper IDs
  papersByTopic: Record<string, PaperMap>;    // topic → paper metadata
  
  // Capabilities
  tools: Tool[] | null;
  prompts: Prompt[] | null;
  resources: ResourceInfo[] | null;
  
  // System
  backendOnline: boolean;
}

interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;          // For assistant: markdown response text
  toolCalls?: ToolCall[];   // Only on assistant messages
  timestamp: number;
  isLoading?: boolean;      // Optimistic loading placeholder
}

interface ToolCall {
  id: string;
  name: string;
  input: Record<string, unknown>;
}

interface WorkflowResult {
  promptName: string;
  response: string;
  toolCalls: ToolCall[];
}

interface Paper {
  title: string;
  authors: string[];
  summary: string;
  pdf_url: string;
  published: string;
}

type PaperMap = Record<string, Paper>;  // paper_id → Paper
```

### Data Fetching Strategy

| Data | When to Fetch | Cache Strategy |
|------|--------------|----------------|
| Tools, Prompts, Resources | On page load (lazy, per-page) | Cache in state, refresh on page revisit |
| Topics list (`papers://list`) | On Library page mount | Cache, invalidate only on user action |
| Papers per topic | On topic click | Cache in state by topic name |
| Chat responses | On user submit | Append to history, never refetch |
| Workflow results | On form submit | Replace previous result |

---

## 7. Important Frontend Considerations

### 7.1 Long Response Times
This is the most important UX consideration. **Chat and prompt-execute calls can take 30–300 seconds.** The frontend must:
- Never hide the loading state prematurely
- Use a generous client-side timeout (>300 seconds, or no timeout — let the backend 408 handle it)
- Show elapsed time for transparency

### 7.2 Do NOT set a short client timeout
```typescript
// ❌ WRONG — will cut off legitimate long-running requests
const response = await fetch(url, { signal: AbortSignal.timeout(10_000) });

// ✅ CORRECT — let the backend's 300s timeout govern; or set to 310s+ to catch 408s
const controller = new AbortController();
const timeoutId = setTimeout(() => controller.abort(), 310_000);
const response = await fetch(url, { signal: controller.signal });
clearTimeout(timeoutId);
```

### 7.3 Parse Resource Content as JSON
Always `JSON.parse()` the `content` field from `GET /api/resources/read`. It is a JSON string, not a nested object. Failure to do this is a very common mistake:

```typescript
// ❌ WRONG
const topics = response.data.content.attention_mechanisms; // undefined!

// ✅ CORRECT
const topics = JSON.parse(response.data.content); // object
const attentionPapers = topics.attention_mechanisms; // ["1706.03762"]
```

### 7.4 Topic Names Use Underscores
Topics in `papers://list` use underscore-separated names (e.g., `"transformer_attention_mechanisms"`). When displaying to users, replace underscores with spaces and capitalize:

```typescript
const displayName = (topic: string) =>
  topic.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
// "transformer_attention_mechanisms" → "Transformer Attention Mechanisms"
```

### 7.5 Tool Calls Can Be Empty
For simple queries the LLM may answer from general knowledge without calling any tools. `tool_calls` will be `[]`. Handle this gracefully — don't show an empty "Tools Used" section.

### 7.6 Backend Health Check on App Startup
Check `GET /` on app startup and set `backendOnline` state. Show a banner if the backend is unreachable:

```typescript
useEffect(() => {
  fetch(`${API_BASE}/`)
    .then(r => r.ok ? setBackendOnline(true) : setBackendOnline(false))
    .catch(() => setBackendOnline(false));
}, []);
```

### 7.7 `compare_papers` Tip
For the "Compare Papers" workflow, show a pre-emptive warning:
> *"Tip: For best results, search for each paper via the chat first. Comparing uncached papers can take up to 5 minutes."*

### 7.8 Error Detail Messages are User-Friendly
The backend's `detail` field in errors is already written to be human-readable and often contains actionable tips. It is safe to display these to users (but avoid showing raw 500 exception messages which may contain stack traces).

### 7.9 No Pagination
All list endpoints (`GET /api/tools`, `GET /api/prompts`, `GET /api/resources`) return **all items in a single response**. No pagination is implemented. The lists are small (typically 5–15 items).

### 7.10 Swagger UI is Available
During development, point developers to `http://127.0.0.1:8000/docs` for live API exploration.

### 7.11 Smart Query Box — Prefix Routing

> **This is a required UX behaviour for the Chat page.**

The chat input box must act as a **unified command interface**. Before sending any input to the backend, inspect the raw string and route it to the correct endpoint based on its prefix:

| User types | Prefix check | Action | API call |
|---|---|---|---|
| `@folders` | `=== '@folders'` | List all resource folders | `GET /api/resources` |
| `@<topic>` | starts with `@` | Read papers for that topic | `GET /api/resources/read?uri=papers://<topic>` |
| `/prompts` | `=== '/prompts'` | List all available prompts | `GET /api/prompts` |
| `/<prompt_name> [key=val …]` | starts with `/` | Execute a named prompt | `POST /api/prompts/execute` |
| anything else | — | Normal AI chat query | `POST /api/chat` |

**Order of checks matters** — check `/prompts` and `@folders` before the generic `@` / `/` fallthrough.

#### Reference implementation (TypeScript)

```typescript
// src/utils/queryRouter.ts
import { chatApi, promptsApi, resourcesApi } from '../api/client';

export async function handleQueryInput(raw: string) {
  const query = raw.trim();

  // ── @folders  → list all resource folders ──────────────────────────
  if (query === '@folders') {
    const res = await resourcesApi.list();
    return { type: 'resources_list', data: res.data };
  }

  // ── @<topic>  → read papers for that topic ─────────────────────────
  if (query.startsWith('@')) {
    const topic = query.slice(1);                        // strip '@'
    const uri   = `papers://${topic}`;
    const res   = await resourcesApi.read(uri);
    const data  = JSON.parse(res.data.content);          // always parse!
    return { type: 'resource', uri, data };
  }

  // ── /prompts  → list available prompts ─────────────────────────────
  if (query === '/prompts') {
    const res = await promptsApi.list();
    return { type: 'prompts_list', data: res.data };
  }

  // ── /<name> [key=val …]  → execute a named prompt ──────────────────
  if (query.startsWith('/')) {
    const parts      = query.split(/\s+/);               // split on whitespace
    const promptName = parts[0].slice(1);                // strip '/'
    const args: Record<string, string> = {};
    for (const part of parts.slice(1)) {
      const [key, ...rest] = part.split('=');
      if (key && rest.length) args[key] = rest.join('=');
    }
    const res = await promptsApi.execute(promptName, args);
    return { type: 'prompt_result', data: res.data };
  }

  // ── default  → normal AI chat ───────────────────────────────────────
  const res = await chatApi.sendMessage(query);
  return { type: 'chat', data: res.data };
}
```

#### How to wire it into the Chat component

```typescript
const handleSend = async () => {
  const input = queryInput.trim();
  if (!input) return;

  setLoading(true);
  try {
    const result = await handleQueryInput(input);
    // Render result.data depending on result.type
    appendToChat(input, result);
  } catch (err) {
    showError(err);
  } finally {
    setLoading(false);
  }
};
```

#### Input placeholder hint
Update the text input placeholder so users discover the syntax:
```
Ask anything, or use @folders · @<topic> · /prompts · /<prompt>
```

---

## 8. Recommended Tech Stack

| Concern | Recommendation |
|---------|---------------|
| Framework | React 18+ with TypeScript |
| Build tool | Vite |
| Styling | Tailwind CSS or CSS Modules |
| HTTP client | Axios or native `fetch` |
| State management | Zustand (lightweight) or React Query (for caching) |
| Markdown rendering | `react-markdown` + `remark-gfm` |
| Routing | React Router v6 |
| Code highlighting | `react-syntax-highlighter` (for paper abstracts with code) |
| Icons | Lucide React or Heroicons |
| Loading indicators | `react-spinners` or custom CSS animations |

---

## 9. API Client Setup (Axios Example)

```typescript
// src/api/client.ts
import axios from 'axios';

const BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000';

export const apiClient = axios.create({
  baseURL: BASE_URL,
  headers: { 'Content-Type': 'application/json' },
  timeout: 320_000,  // 320 seconds — slightly above backend's 300s default
});

// Response interceptor for error normalization
apiClient.interceptors.response.use(
  response => response,
  error => {
    if (error.response) {
      const status = error.response.status;
      const detail = error.response.data?.detail;
      
      // Enrich the error with normalized fields
      error.statusCode = status;
      error.userMessage = typeof detail === 'string'
        ? detail
        : 'An unexpected error occurred. Please try again.';
    } else if (error.request) {
      error.userMessage = 'Cannot connect to the backend server. Is it running?';
    }
    return Promise.reject(error);
  }
);

// ─── API Functions ────────────────────────────────────────────────

export const chatApi = {
  sendMessage: (message: string) =>
    apiClient.post<ChatResponse>('/api/chat', { message }),
};

export const toolsApi = {
  list: () => apiClient.get<{ tools: Tool[] }>('/api/tools'),
};

export const promptsApi = {
  list: () => apiClient.get<{ prompts: Prompt[] }>('/api/prompts'),
  execute: (promptName: string, args: Record<string, unknown>) =>
    apiClient.post<ExecutePromptResponse>('/api/prompts/execute', {
      prompt_name: promptName,
      arguments: args,
    }),
};

export const resourcesApi = {
  list: () => apiClient.get<ResourcesResponse>('/api/resources'),
  read: (uri: string) =>
    apiClient.get<ReadResourceResponse>('/api/resources/read', {
      params: { uri },
    }),
  readTopicList: async (): Promise<Record<string, string[]>> => {
    const res = await apiClient.get<ReadResourceResponse>('/api/resources/read', {
      params: { uri: 'papers://list' },
    });
    return JSON.parse(res.data.content);
  },
  readTopicPapers: async (topic: string): Promise<PaperMap> => {
    const res = await apiClient.get<ReadResourceResponse>('/api/resources/read', {
      params: { uri: `papers://${topic}/info` },
    });
    return JSON.parse(res.data.content);
  },
};

// ─── TypeScript Types ─────────────────────────────────────────────

export interface ChatResponse {
  response: string;
  tool_calls: ToolCall[];
}

export interface ToolCall {
  id: string;
  name: string;
  input: Record<string, unknown>;
}

export interface Tool {
  name: string;
  description: string;
  input_schema: {
    type: string;
    properties: Record<string, { type: string; description?: string }>;
    required?: string[];
  };
}

export interface Prompt {
  name: string;
  description: string;
  arguments: PromptArgument[];
}

export interface PromptArgument {
  name: string;
  description: string;
  required: boolean;
}

export interface ExecutePromptResponse {
  prompt_name: string;
  response: string;
  tool_calls: ToolCall[];
}

export interface ResourcesResponse {
  resources: ResourceInfo[];
  resource_templates: ResourceTemplate[];
}

export interface ResourceInfo {
  uri: string;
  name: string;
  description: string;
  mime_type: string;
}

export interface ResourceTemplate {
  uri_template: string;
  name: string;
  description: string;
  mime_type: string;
}

export interface ReadResourceResponse {
  uri: string;
  content: string; // JSON-encoded string — always JSON.parse() this!
}

export interface Paper {
  title: string;
  authors: string[];
  summary: string;
  pdf_url: string;
  published: string;
}

export type PaperMap = Record<string, Paper>;
```
