from abc import ABC, abstractmethod
from typing import Any


class BaseLLMProvider(ABC):
    """
    Abstract base class for all LLM providers.

    Each provider must implement `chat()` and return a normalized response
    dict so that MCPClientManager never needs to know which LLM is in use.

    Normalized response format returned by `chat()`:
    {
        "text":        str,           # assistant text (may be "" during tool use)
        "tool_calls":  list[dict],    # [{"id": str, "name": str, "input": dict}]
        "stop_reason": str,           # "tool_use" | "end_turn"
    }
    """

    @abstractmethod
    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
    ) -> dict[str, Any]:
        """
        Send a conversation turn to the LLM.

        Args:
            messages: Conversation history in the provider-agnostic internal format.
            tools:    List of available MCP tools in internal format:
                      [{"name": str, "description": str, "input_schema": dict}]

        Returns:
            Normalized response dict (see class docstring).
        """
        ...
