from fastapi import APIRouter, Request, HTTPException
from app.schemas.chat import ChatRequest, ChatResponse
from typing import List, Dict, Any

router = APIRouter()

@router.post("/chat", response_model=ChatResponse)
async def chat(request: Request, payload: ChatRequest):
    """
    Send a query to the Claude + MCP pipeline.
    """
    mcp_client = request.app.state.mcp_client
    if not mcp_client:
        raise HTTPException(status_code=503, detail="MCP Client is not initialized.")
    
    try:
        result = await mcp_client.process_query(payload.message)
        return ChatResponse(
            response=result["response"],
            tool_calls=result["tool_calls"]
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing chat query: {str(e)}")

@router.get("/tools")
async def list_tools(request: Request):
    """
    List all available tools across connected MCP servers.
    """
    mcp_client = request.app.state.mcp_client
    if not mcp_client:
        raise HTTPException(status_code=503, detail="MCP Client is not initialized.")
    return {"tools": mcp_client.available_tools}

@router.get("/prompts")
async def list_prompts(request: Request):
    """
    List all available prompts across connected MCP servers.
    """
    mcp_client = request.app.state.mcp_client
    if not mcp_client:
        raise HTTPException(status_code=503, detail="MCP Client is not initialized.")
    return {"prompts": mcp_client.available_prompts}

@router.get("/resources")
async def list_resources(request: Request):
    """
    List registered resource URIs.
    """
    mcp_client = request.app.state.mcp_client
    if not mcp_client:
        raise HTTPException(status_code=503, detail="MCP Client is not initialized.")
    
    # Extract registered resource URIs from sessions dictionary
    resource_uris = [uri for uri in mcp_client.sessions.keys() if "://" in uri]
    return {"resources": resource_uris}

@router.get("/resources/read")
async def read_resource(request: Request, uri: str):
    """
    Read content of a specific resource.
    """
    mcp_client = request.app.state.mcp_client
    if not mcp_client:
        raise HTTPException(status_code=503, detail="MCP Client is not initialized.")
    
    try:
        content = await mcp_client.get_resource(uri)
        return {"uri": uri, "content": content}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
