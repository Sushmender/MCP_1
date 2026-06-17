# Business Flows

> This document describes the primary user workflows supported by the MCP Research Backend, including what the user does, how the frontend should behave, which API calls are made, what the backend processes, and what response to expect.

---

## Table of Contents

1. [Free-Form Research Chat Query](#1-free-form-research-chat-query)
2. [Summarize a Specific Paper](#2-summarize-a-specific-paper)
3. [Compare Two Papers](#3-compare-two-papers)
4. [Search and Summarize by Topic](#4-search-and-summarize-by-topic)
5. [Browse Available Research Tools](#5-browse-available-research-tools)
6. [Browse Cached Papers by Topic](#6-browse-cached-papers-by-topic)
7. [Browse All Available Prompt Templates](#7-browse-all-available-prompt-templates)

---

## 1. Free-Form Research Chat Query

### Overview
The most flexible workflow. The user types any natural-language research question and the LLM autonomously decides which tools to use.

### User Action
The user types a question such as:
- *"Find me the top 5 papers on diffusion models and give me a brief summary of each."*
- *"What does the paper 2301.01234 say about its methodology?"*
- *"Fetch this URL and tell me what it says: https://arxiv.org/abs/1706.03762"*

### Frontend Behavior
1. Render a chat input textarea
2. On submit, disable the input and show a loading spinner (queries can take 10–120 seconds)
3. POST to the backend
4. On success, render the `response` as markdown text in the chat thread
5. Optionally display the `tool_calls` array as a collapsible "Tools Used" section
6. Re-enable the input

### API Calls

```
POST /api/chat
Body: { "message": "<user query>" }
```

### Backend Processing
1. FastAPI receives the request and passes it to `MCPClientManager.process_query()`
2. LLM receives the message + full list of available tools
3. LLM decides to call `search_papers("diffusion models", max_results=5)`
4. Backend dispatches the tool call to the `research` MCP subprocess
5. The MCP server fetches results from arXiv and saves JSON to disk
6. Tool result (list of paper IDs) is appended to the LLM conversation history
7. LLM calls `extract_info(paper_id)` for each paper ID
8. LLM composes its final text answer
9. Backend returns `response` + `tool_calls` log

### Expected Response
```json
{
  "response": "Here are the top 5 papers on diffusion models:\n\n1. **Denoising Diffusion Probabilistic Models** ...\n2. **Score-Based Generative Modeling** ...",
  "tool_calls": [
    { "id": "call_a1b2", "name": "search_papers", "input": { "topic": "diffusion models", "max_results": 5 } },
    { "id": "call_c3d4", "name": "extract_info", "input": { "paper_id": "2006.11239" } },
    { "id": "call_e5f6", "name": "extract_info", "input": { "paper_id": "2011.13456" } }
  ]
}
```

### Edge Cases
| Situation | Backend Behavior | Frontend Should Handle |
|-----------|-----------------|----------------------|
| Query times out (>300s) | HTTP 408 | Show timeout error with suggestion to retry a simpler query |
| LLM not configured | Returns `response` with config error text, HTTP 200 | Show the response text as-is (it will be an error description) |
| arXiv not reachable | Tool call fails; LLM may report the error in its text | Show the response text |

---

## 2. Summarize a Specific Paper

### Overview
The user provides an arXiv paper ID and receives a structured 3–4 paragraph summary.

### User Action
The user enters a known arXiv paper ID (e.g., `1706.03762`) and clicks "Summarize".

### Frontend Behavior
1. Show a form with a single text field labeled "arXiv Paper ID"
2. Validate the field is non-empty before submitting
3. On submit, show a loading state
4. On success, render the `response` field as formatted markdown

### API Calls

```
POST /api/prompts/execute
Body: {
  "prompt_name": "summarize_paper",
  "arguments": { "paper_id": "1706.03762" }
}
```

### Backend Processing
1. Validates that `"summarize_paper"` is in `available_prompts`
2. Calls `session.get_prompt("summarize_paper", {"paper_id": "1706.03762"})` on the research MCP server
3. The server renders the prompt template with the paper ID
4. Rendered text is passed to `process_query()`, which:
   - Instructs LLM to call `extract_info("1706.03762")`
   - LLM checks if the paper is stored locally
   - If found: uses stored metadata to write summary
   - If not found: LLM reports the paper is not cached yet (user must run a search first)
5. Returns structured summary

### Expected Response
```json
{
  "prompt_name": "summarize_paper",
  "response": "**Summary of '1706.03762' — Attention Is All You Need**\n\n**Problem:** Prior sequence models relied heavily on recurrent architectures...\n\n**Approach:** The Transformer uses self-attention exclusively...\n\n**Key Results:** Achieved state-of-the-art BLEU scores...\n\n**Takeaway:** The Transformer architecture revolutionized NLP by eliminating recurrence.",
  "tool_calls": [
    { "id": "call_xy1", "name": "extract_info", "input": { "paper_id": "1706.03762" } }
  ]
}
```

### Important Note for Frontend
> If the paper has never been searched for, the `extract_info` tool will return `"No stored information found for paper ID '...'."` and the LLM will report it cannot summarize. The frontend should suggest the user first search for the paper using the chat interface.

---

## 3. Compare Two Papers

### Overview
The user provides two arXiv paper IDs and receives a structured side-by-side comparison with a reading recommendation.

### User Action
The user enters two arXiv paper IDs (e.g., `1706.03762` and `2005.14165`) and clicks "Compare".

### Frontend Behavior
1. Show a form with two text fields: "Paper ID 1" and "Paper ID 2"
2. Validate both fields are non-empty
3. On submit, show a loading state — this can take **up to 5 minutes** if papers need to be fetched from arXiv
4. Display a progress indicator or informational message: *"This may take a while if papers haven't been searched before…"*
5. Render the comparison as formatted markdown

### API Calls

```
POST /api/prompts/execute
Body: {
  "prompt_name": "compare_papers",
  "arguments": {
    "paper_id_1": "1706.03762",
    "paper_id_2": "2005.14165"
  }
}
```

### Backend Processing
1. Validates `"compare_papers"` prompt exists
2. Renders prompt template with both paper IDs
3. LLM attempts `extract_info()` for both papers
4. If either paper is not found locally, the LLM is instructed to call `search_papers(topic=<paper_id>, max_results=1)` first, then retry `extract_info()`
5. After retrieving both papers' metadata, LLM produces a structured comparison:
   - Research problem & motivation
   - Methodology / approach
   - Key results & contributions
   - Strengths and weaknesses
   - Reading recommendation

### Expected Response
```json
{
  "prompt_name": "compare_papers",
  "response": "## Comparison: '1706.03762' vs '2005.14165'\n\n**Research Problem:**\n- Paper A addresses sequence transduction without recurrence...\n- Paper B addresses few-shot learning in large language models...\n\n**Methodology:**\n...\n\n**Recommendation:** Read Paper A first as a foundational architecture paper.",
  "tool_calls": [
    { "id": "call_1", "name": "extract_info", "input": { "paper_id": "1706.03762" } },
    { "id": "call_2", "name": "extract_info", "input": { "paper_id": "2005.14165" } }
  ]
}
```

### Timeout Handling
This flow is the most time-consuming. If both papers need to be fetched from arXiv, it can exceed the default 300-second timeout. The error message from the backend includes a helpful tip:

```json
{
  "detail": "Prompt 'compare_papers' timed out after 300s. Tip: for 'compare_papers', make sure both paper IDs are already stored locally (run a /chat search first), or pass IDs that exist in papers/ on disk."
}
```

Frontend should display this tip to the user.

---

## 4. Search and Summarize by Topic

### Overview
The user enters a research topic and receives an overview of the top N papers with a synthesis paragraph.

### User Action
The user types a topic (e.g., `"RAG"` or `"graph neural networks"`) and optionally specifies a number of papers (default: 3).

### Frontend Behavior
1. Show a form with a "Topic" text field and an optional "Number of papers" number input (1–10)
2. On submit, show a loading state with a message like *"Searching arXiv and summarizing papers…"*
3. Render the response as formatted markdown, including individual paper summaries and a synthesis paragraph

### API Calls

```
POST /api/prompts/execute
Body: {
  "prompt_name": "find_and_summarize",
  "arguments": {
    "topic": "RAG",
    "max_results": 3
  }
}
```

### Backend Processing
1. Validates `"find_and_summarize"` prompt exists
2. Renders prompt instructing the LLM to:
   - Call `search_papers(topic="RAG", max_results=3)`
   - Call `extract_info(paper_id)` for each returned paper ID
   - Write a 1–2 paragraph summary for each paper
   - Write a synthesis paragraph with common themes and open questions
3. Returns the complete analysis

### Expected Response
```json
{
  "prompt_name": "find_and_summarize",
  "response": "## Top 3 Papers on RAG (Retrieval-Augmented Generation)\n\n### 1. Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks\n...\n\n### 2. ...\n\n---\n\n**Synthesis:** These papers collectively demonstrate that RAG...",
  "tool_calls": [
    { "id": "call_s1", "name": "search_papers", "input": { "topic": "RAG", "max_results": 3 } },
    { "id": "call_e1", "name": "extract_info", "input": { "paper_id": "2005.11401" } },
    { "id": "call_e2", "name": "extract_info", "input": { "paper_id": "..." } },
    { "id": "call_e3", "name": "extract_info", "input": { "paper_id": "..." } }
  ]
}
```

---

## 5. Browse Available Research Tools

### Overview
Read-only view of all capabilities the backend exposes. Useful for a "capabilities" or "about" page.

### User Action
User navigates to a "Tools" or "Capabilities" page.

### Frontend Behavior
1. On page load, call `GET /api/tools`
2. Render a card or table for each tool showing: name, description, and input parameters
3. No user interaction needed — this is a read-only display

### API Calls

```
GET /api/tools
```

### Backend Processing
Returns the in-memory `available_tools` list collected from all MCP servers at startup.

### Expected Response
```json
{
  "tools": [
    {
      "name": "search_papers",
      "description": "Search for papers on arXiv...",
      "input_schema": { "type": "object", "properties": { "topic": {...}, "max_results": {...} }, "required": ["topic"] }
    },
    { "name": "extract_info", ... },
    { "name": "fetch", ... },
    { "name": "read_file", ... },
    { "name": "write_file", ... }
  ]
}
```

---

## 6. Browse Cached Papers by Topic

### Overview
View all papers that have already been searched and cached locally, without making any LLM or arXiv calls.

### User Action
User navigates to a "Library" or "Cached Papers" page.

### Frontend Behavior — Step 1: Get Topic List

**API Call:**
```
GET /api/resources/read?uri=papers://list
```

**Parse the `content` field** (it is a JSON string, not an object — `JSON.parse(response.content)`) to get a map of `{ topic: [paper_id, ...] }`.

Display each topic as a clickable card or accordion.

### Frontend Behavior — Step 2: Get Papers for a Topic

When user clicks a topic (e.g., `"transformer_attention_mechanisms"`):

**API Call:**
```
GET /api/resources/read?uri=papers://transformer_attention_mechanisms/info
```

**Parse the `content` field** to get:
```json
{
  "1706.03762": {
    "title": "Attention Is All You Need",
    "authors": ["Ashish Vaswani", ...],
    "summary": "...",
    "pdf_url": "https://arxiv.org/pdf/1706.03762v5",
    "published": "2017-06-12"
  }
}
```

Display each paper with title, authors, published date, a truncated summary, and a "View PDF" link.

### Backend Processing
Resources are served directly from the `papers/` filesystem by the research MCP server subprocess. No LLM call is made — this is a fast, direct file read.

### Important Note
> **Topic names use underscores**, not spaces. The topic `"transformer attention mechanisms"` is stored as `"transformer_attention_mechanisms"`. The `papers://list` response returns the folder names as-is (with underscores).

---

## 7. Browse All Available Prompt Templates

### Overview
Display the available research workflows (summarize, compare, find & summarize) so the user can choose which to use.

### User Action
User navigates to a "Research Workflows" or "Templates" page.

### Frontend Behavior
1. Call `GET /api/prompts` on page load
2. Render each prompt as a card:
   - Title: prompt `name` (prettified)
   - Description: prompt `description`
   - Input fields: one input for each argument (mark required ones with `*`)
   - Submit button → routes to the appropriate "Execute Prompt" form

### API Calls
```
GET /api/prompts
```

### Expected Response
```json
{
  "prompts": [
    {
      "name": "summarize_paper",
      "description": "...",
      "arguments": [
        { "name": "paper_id", "description": "...", "required": true }
      ]
    },
    {
      "name": "compare_papers",
      "description": "...",
      "arguments": [
        { "name": "paper_id_1", "required": true },
        { "name": "paper_id_2", "required": true }
      ]
    },
    {
      "name": "find_and_summarize",
      "description": "...",
      "arguments": [
        { "name": "topic", "required": true },
        { "name": "max_results", "required": false }
      ]
    }
  ]
}
```
