import asyncio
from fastapi import APIRouter, Request, HTTPException
from app.schemas.chat import (
    ChatRequest,
    ChatResponse,
    ExecutePromptRequest,
    ExecutePromptResponse,
    ReadResourceResponse,
)
from app.config import settings
from typing import Any

router = APIRouter()


# ── Chat ──────────────────────────────────────────────────────────────────────

@router.post("/chat", response_model=ChatResponse)
async def chat(request: Request, payload: ChatRequest):
    """
    Send a free-form query through the LLM + MCP tool-call loop.
    The model will automatically call MCP tools as needed and return
    a final text response.
    """
    mcp_client = request.app.state.mcp_client
    if not mcp_client:
        raise HTTPException(status_code=503, detail="MCP Client is not initialized.")

    try:
        result = await asyncio.wait_for(
            mcp_client.process_query(payload.message),
            timeout=settings.PROMPT_TIMEOUT_SECS,
        )
        return ChatResponse(
            response=result["response"],
            tool_calls=result["tool_calls"],
        )
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=408,
            detail=(
                f"Request timed out after {settings.PROMPT_TIMEOUT_SECS}s. "
                "Paper searches involve multiple LLM + ArXiv calls — try a simpler query "
                "or increase PROMPT_TIMEOUT_SECS in your .env file."
            ),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing chat query: {str(e)}")


# ── Tools ─────────────────────────────────────────────────────────────────────

@router.get("/tools")
async def list_tools(request: Request):
    """
    List all tools registered across every connected MCP server.

    Returns name, description, and input_schema for each tool so callers
    know exactly what arguments each tool expects.
    """
    mcp_client = request.app.state.mcp_client
    if not mcp_client:
        raise HTTPException(status_code=503, detail="MCP Client is not initialized.")
    return {"tools": mcp_client.available_tools}


# ── Prompts ───────────────────────────────────────────────────────────────────

@router.get("/prompts")
async def list_prompts(request: Request):
    """
    List all prompts registered across every connected MCP server.

    Each entry includes the prompt name, description, and the arguments it
    accepts (name, description, required flag).  Use POST /api/prompts/execute
    to actually run one.
    """
    mcp_client = request.app.state.mcp_client
    if not mcp_client:
        raise HTTPException(status_code=503, detail="MCP Client is not initialized.")
    return {"prompts": mcp_client.available_prompts}


@router.post("/prompts/execute", response_model=ExecutePromptResponse)
async def execute_prompt(request: Request, payload: ExecutePromptRequest):
    """
    Execute a named MCP prompt and pipe the resulting message through the LLM.

    How it works:
      1. The MCP server renders the prompt template with your arguments into a
         ready-made instruction string.
      2. That string is sent to the LLM as a user message (via process_query),
         so the model can call any tools it needs and return a final answer.

    Example request body:
    ```json
    {
      "prompt_name": "summarize_paper",
      "arguments": { "paper_id": "2301.01234" }
    }
    ```
    """
    mcp_client = request.app.state.mcp_client
    if not mcp_client:
        raise HTTPException(status_code=503, detail="MCP Client is not initialized.")

    # Validate the prompt exists
    known = {p["name"] for p in mcp_client.available_prompts}
    if payload.prompt_name not in known:
        raise HTTPException(
            status_code=404,
            detail=f"Prompt '{payload.prompt_name}' not found. Available: {sorted(known)}",
        )

    try:
        result = await asyncio.wait_for(
            mcp_client.execute_prompt(payload.prompt_name, payload.arguments),
            timeout=getattr(settings, "PROMPT_TIMEOUT_SECS", 120),
        )
        return ExecutePromptResponse(
            prompt_name=payload.prompt_name,
            response=result["response"],
            tool_calls=result["tool_calls"],
        )
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=408,
            detail=(
                f"Prompt '{payload.prompt_name}' timed out after "
                f"{getattr(settings, 'PROMPT_TIMEOUT_SECS', 120)}s. "
                "Tip: for 'compare_papers', make sure both paper IDs are already "
                "stored locally (run a /chat search first), or pass IDs that exist "
                "in papers/ on disk."
            ),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error executing prompt: {str(e)}")


# ── Resources ─────────────────────────────────────────────────────────────────

@router.get("/resources")
async def list_resources(request: Request):
    """
    List all resources and resource templates registered across MCP servers.

    Static resources have a fixed URI (e.g. papers://list).
    Resource templates have a URI pattern with path parameters
    (e.g. papers://{topic}/info) — fill in the parameter to read them.
    """
    mcp_client = request.app.state.mcp_client
    if not mcp_client:
        raise HTTPException(status_code=503, detail="MCP Client is not initialized.")
    return {
        "resources": mcp_client.available_resources,
        "resource_templates": mcp_client.available_resource_templates,
    }


@router.get("/resources/read", response_model=ReadResourceResponse)
async def read_resource(request: Request, uri: str):
    """
    Read the content of a specific resource by its URI.

    Pass the fully-resolved URI as a query parameter, e.g.:
      GET /api/resources/read?uri=papers://list
      GET /api/resources/read?uri=papers://attention_mechanisms/info

    For template resources, substitute the path parameter yourself before
    calling this endpoint.
    """
    mcp_client = request.app.state.mcp_client
    if not mcp_client:
        raise HTTPException(status_code=503, detail="MCP Client is not initialized.")

    try:
        content = await mcp_client.get_resource(uri)
        return ReadResourceResponse(uri=uri, content=content)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading resource: {str(e)}")
