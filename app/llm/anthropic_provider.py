from typing import Any
from anthropic import AsyncAnthropic
from app.llm.base import BaseLLMProvider


class AnthropicProvider(BaseLLMProvider):
    """
    LLM provider backed by Anthropic's Claude models.

    Uses the Anthropic Python SDK. Tool-use blocks in the response are
    converted into the normalized internal format before returning.
    """

    def __init__(self, api_key: str, model: str):
        self.client = AsyncAnthropic(api_key=api_key)
        self.model = model

    def _convert_tools(self, tools: list[dict]) -> list[dict]:
        """
        Anthropic tool format (same as our internal format):
        {"name": str, "description": str, "input_schema": dict}
        No conversion needed.
        """
        return tools

    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
    ) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": 2048,
            "messages": messages,
        }
        if tools:
            kwargs["tools"] = self._convert_tools(tools)

        response = await self.client.messages.create(**kwargs)

        text = ""
        tool_calls: list[dict] = []

        for block in response.content:
            if block.type == "text":
                text += block.text
            elif block.type == "tool_use":
                tool_calls.append({
                    "id": block.id,
                    "name": block.name,
                    "input": block.input,
                })

        stop_reason = "tool_use" if tool_calls else "end_turn"
        return {"text": text, "tool_calls": tool_calls, "stop_reason": stop_reason}
