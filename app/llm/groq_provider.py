import json
from typing import Any
from groq import AsyncGroq
from app.llm.base import BaseLLMProvider


class GroqProvider(BaseLLMProvider):
    """
    LLM provider backed by Groq's OpenAI-compatible API.

    Converts our internal tool format to OpenAI function-calling format on
    the way in, and normalizes OpenAI-style tool_calls back to our internal
    format on the way out.

    Messages with tool results are sent in OpenAI's 'tool' role format.
    """

    def __init__(self, api_key: str, model: str):
        self.client = AsyncGroq(api_key=api_key)
        self.model = model

    def _convert_tools(self, tools: list[dict]) -> list[dict]:
        """
        Convert internal tool format → OpenAI function-calling format.

        Internal:  {"name": str, "description": str, "input_schema": dict}
        OpenAI:    {"type": "function", "function": {"name", "description", "parameters"}}
        """
        return [
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "parameters": t.get("input_schema", {"type": "object", "properties": {}}),
                },
            }
            for t in tools
        ]

    def _convert_messages(self, messages: list[dict]) -> list[dict]:
        """
        Convert our internal message list to OpenAI-compatible format.

        Handles the special 'tool_result' content type that Anthropic uses,
        translating it to OpenAI's 'tool' role messages.
        """
        converted: list[dict] = []
        for msg in messages:
            role = msg["role"]
            content = msg["content"]

            # Content is a plain string — pass through
            if isinstance(content, str):
                converted.append({"role": role, "content": content})
                continue

            # Content is a list of blocks (Anthropic-style)
            if isinstance(content, list):
                # Check if this is a tool_result message (user role with tool results)
                if role == "user" and all(
                    isinstance(b, dict) and b.get("type") == "tool_result"
                    for b in content
                ):
                    for block in content:
                        tool_content = block.get("content", "")
                        if isinstance(tool_content, list):
                            tool_content = " ".join(
                                c.get("text", str(c)) if isinstance(c, dict) else str(c)
                                for c in tool_content
                            )
                        converted.append({
                            "role": "tool",
                            "tool_call_id": block["tool_use_id"],
                            "content": tool_content,
                        })
                    continue

                # Assistant message with tool_use blocks
                if role == "assistant":
                    text_parts = []
                    oai_tool_calls = []
                    for block in content:
                        if hasattr(block, "type"):
                            # SDK objects
                            if block.type == "text":
                                text_parts.append(block.text)
                            elif block.type == "tool_use":
                                oai_tool_calls.append({
                                    "id": block.id,
                                    "type": "function",
                                    "function": {
                                        "name": block.name,
                                        "arguments": json.dumps(block.input),
                                    },
                                })
                        elif isinstance(block, dict):
                            if block.get("type") == "text":
                                text_parts.append(block.get("text", ""))
                            elif block.get("type") == "tool_use":
                                oai_tool_calls.append({
                                    "id": block["id"],
                                    "type": "function",
                                    "function": {
                                        "name": block["name"],
                                        "arguments": json.dumps(block.get("input", {})),
                                    },
                                })
                    asst_msg: dict[str, Any] = {
                        "role": "assistant",
                        "content": " ".join(text_parts) or None,
                    }
                    if oai_tool_calls:
                        asst_msg["tool_calls"] = oai_tool_calls
                    converted.append(asst_msg)
                    continue

                # Fallback: join text blocks
                text = " ".join(
                    b.get("text", str(b)) if isinstance(b, dict) else str(b)
                    for b in content
                )
                converted.append({"role": role, "content": text})

        return converted

    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
    ) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": 2048,
            "messages": self._convert_messages(messages),
        }
        if tools:
            kwargs["tools"] = self._convert_tools(tools)
            kwargs["tool_choice"] = "auto"

        response = await self.client.chat.completions.create(**kwargs)
        message = response.choices[0].message

        text = message.content or ""
        tool_calls: list[dict] = []

        if message.tool_calls:
            for tc in message.tool_calls:
                try:
                    args = json.loads(tc.function.arguments)
                except (json.JSONDecodeError, TypeError):
                    args = {}
                tool_calls.append({
                    "id": tc.id,
                    "name": tc.function.name,
                    "input": args,
                })

        stop_reason = "tool_use" if tool_calls else "end_turn"
        return {"text": text, "tool_calls": tool_calls, "stop_reason": stop_reason}
