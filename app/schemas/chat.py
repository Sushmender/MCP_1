from pydantic import BaseModel
from typing import List, Dict, Any, Optional


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    response: str
    tool_calls: List[Dict[str, Any]] = []


# ── Prompts ──────────────────────────────────────────────────────────────────

class PromptArgument(BaseModel):
    name: str
    description: str = ""
    required: bool = False


class PromptInfo(BaseModel):
    name: str
    description: str = ""
    arguments: List[PromptArgument] = []


class ExecutePromptRequest(BaseModel):
    """Body for POST /api/prompts/execute"""
    prompt_name: str
    arguments: Dict[str, Any] = {}


class ExecutePromptResponse(BaseModel):
    prompt_name: str
    response: str
    tool_calls: List[Dict[str, Any]] = []


# ── Resources ─────────────────────────────────────────────────────────────────

class ResourceInfo(BaseModel):
    uri: str
    name: str = ""
    description: str = ""
    mime_type: str = ""


class ReadResourceResponse(BaseModel):
    uri: str
    content: str
