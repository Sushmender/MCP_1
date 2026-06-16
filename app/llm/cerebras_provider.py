import json
import re
import uuid
from typing import Any

from cerebras.cloud.sdk import AsyncCerebras
from app.llm.base import BaseLLMProvider


class CerebrasProvider(BaseLLMProvider):
    """
    LLM provider backed by the official Cerebras Cloud SDK.

    Uses AsyncCerebras which is OpenAI-compatible under the hood.
    Converts our internal tool format to OpenAI function-calling format
    on the way in, and normalizes tool_calls back to our internal format
    on the way out.
    """

    def __init__(self, api_key: str, model: str):
        # Set a generous HTTP timeout: paper searches involve multiple LLM
        # round-trips + ArXiv API calls, which can take well over 60 seconds.
        self.client = AsyncCerebras(api_key=api_key, timeout=300.0)
        self.model = model

    # ------------------------------------------------------------------ #
    # Format conversion helpers                                            #
    # ------------------------------------------------------------------ #

    def _convert_tools(self, tools: list[dict]) -> list[dict]:
        """
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
        Convert internal message list to OpenAI-compatible format.

        Handles Anthropic-style 'tool_result' content blocks, translating
        them to OpenAI's 'tool' role messages.
        """
        converted: list[dict] = []
        for msg in messages:
            role = msg["role"]
            content = msg["content"]

            # Plain string — pass through unchanged
            if isinstance(content, str):
                converted.append({"role": role, "content": content})
                continue

            # List of content blocks (Anthropic-style)
            if isinstance(content, list):
                # user role with tool_result blocks → OpenAI "tool" role messages
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

                # Assistant message that may contain tool_use blocks
                if role == "assistant":
                    text_parts = []
                    oai_tool_calls = []
                    for block in content:
                        if hasattr(block, "type"):
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

                # Fallback: join any text blocks into a single string
                text = " ".join(
                    b.get("text", str(b)) if isinstance(b, dict) else str(b)
                    for b in content
                )
                converted.append({"role": role, "content": text})

        return converted

    @staticmethod
    def _parse_tool_call(raw_name: str, raw_arguments: str | None) -> tuple[str, dict]:
        """
        Handle the occasional malformed tool call where the function name
        contains embedded JSON, e.g. 'list_directory{"path": "papers"}'.
        """
        name = raw_name.strip()
        embedded: dict = {}

        brace_pos = name.find("{")
        if brace_pos != -1:
            try:
                embedded = json.loads(name[brace_pos:])
            except (json.JSONDecodeError, TypeError):
                pass
            name = name[:brace_pos]

        explicit: dict = {}
        if raw_arguments:
            try:
                explicit = json.loads(raw_arguments)
            except (json.JSONDecodeError, TypeError):
                pass

        return name, {**embedded, **explicit}

    @staticmethod
    def _parse_xml_function_calls(text: str) -> list[dict]:
        """Parse XML-style function calls some models emit instead of proper tool_calls."""
        calls = []
        pattern = re.compile(
            r"<function=([^<\s\[{=]+)\s*=?\s*([{\[][^<]*?)\s*</function>",
            re.DOTALL,
        )
        for m in pattern.finditer(text):
            raw_name = m.group(1).strip()
            raw_args = m.group(2).strip()
            args: dict = {}
            for candidate in [raw_args, raw_args + "}", raw_args + "}]"]:
                try:
                    parsed = json.loads(candidate)
                    if isinstance(parsed, list):
                        parsed = parsed[0] if parsed else {}
                    if isinstance(parsed, dict):
                        args = parsed
                        break
                except (json.JSONDecodeError, TypeError, IndexError):
                    continue
            calls.append({"id": f"call_{uuid.uuid4().hex[:8]}", "name": raw_name, "input": args})
        return calls

    # ------------------------------------------------------------------ #
    # Main entry point                                                     #
    # ------------------------------------------------------------------ #

    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
    ) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": 4096,
            "messages": self._convert_messages(messages),
        }
        if tools:
            kwargs["tools"] = self._convert_tools(tools)
            kwargs["tool_choice"] = "auto"

        print(f"[CerebrasProvider] model={self.model}")

        response = await self.client.chat.completions.create(**kwargs)
        message = response.choices[0].message

        text = message.content or ""
        tool_calls: list[dict] = []

        if message.tool_calls:
            for tc in message.tool_calls:
                name, args = self._parse_tool_call(tc.function.name, tc.function.arguments)
                tool_calls.append({"id": tc.id, "name": name, "input": args})

        # Also scan text content for stray XML-style function calls
        if text:
            xml_calls = self._parse_xml_function_calls(text)
            if xml_calls:
                tool_calls.extend(xml_calls)
                text = re.sub(r"<function=.*?</function>", "", text, flags=re.DOTALL).strip()

        stop_reason = "tool_use" if tool_calls else "end_turn"
        return {"text": text, "tool_calls": tool_calls, "stop_reason": stop_reason}
