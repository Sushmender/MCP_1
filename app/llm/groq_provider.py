import json
import re
import uuid
from typing import Any
from groq import AsyncGroq, BadRequestError
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

    @staticmethod
    def _parse_tool_call(raw_name: str, raw_arguments: str | None) -> tuple[str, dict]:
        """
        Groq (and some other OpenAI-compatible models) occasionally return a
        malformed tool call where the function *name* contains embedded JSON
        arguments, e.g.:

            name      = 'list_directory{"path": "papers"}'
            arguments = ''   # or None

        This helper detects that pattern by looking for the first '{' in the
        name, splits the clean name from the embedded JSON, and merges the
        result with whatever was already in `raw_arguments`.

        Returns:
            (clean_name, merged_args_dict)
        """
        name = raw_name.strip()
        embedded: dict = {}

        # Detect embedded JSON in the name (e.g. 'tool_name{"key": "val"}')
        brace_pos = name.find("{")
        if brace_pos != -1:
            json_fragment = name[brace_pos:]
            name = name[:brace_pos]
            try:
                embedded = json.loads(json_fragment)
            except (json.JSONDecodeError, TypeError):
                # Best-effort: ignore malformed embedded fragment
                pass

        # Parse the normal arguments field
        explicit: dict = {}
        if raw_arguments:
            try:
                explicit = json.loads(raw_arguments)
            except (json.JSONDecodeError, TypeError):
                pass

        # Merge: explicit arguments field takes precedence over embedded ones
        merged = {**embedded, **explicit}
        return name, merged

    @staticmethod
    def _parse_xml_function_calls(text: str) -> list[dict]:
        """
        Parse Groq's llama-style XML function-call format.

        Observed variants (all are real Groq failures):
            <function=list_directory{"path": "papers"}</function>
            <function=list_directory [{"path": "papers"}] </function>
            <function=list_directory{"path": "papers/"}</function>   ← missing }

        Captures tool name + everything from the first `{` or `[` up to
        </function>, then tries multiple JSON repair strategies.
        """
        calls = []
        pattern = re.compile(
            r"<function=([^<\s\[{=]+)\s*=?\s*([{\[][^<]*?)\s*</function>",
            re.DOTALL,
        )
        for m in pattern.finditer(text):
            raw_name = m.group(1).strip()
            raw_args = m.group(2).strip()

            args: dict = {}
            # Candidates to try in order: as-is, auto-close object, auto-close array+obj
            candidates = [raw_args, raw_args + "}", raw_args + "}]"]
            for candidate in candidates:
                try:
                    parsed = json.loads(candidate)
                    # Unwrap array wrapper: [{"key": "val"}] → {"key": "val"}
                    if isinstance(parsed, list):
                        parsed = parsed[0] if parsed else {}
                    if isinstance(parsed, dict):
                        args = parsed
                        break
                except (json.JSONDecodeError, TypeError, IndexError):
                    continue

            calls.append({
                "id": f"call_{uuid.uuid4().hex[:8]}",
                "name": raw_name,
                "input": args,
            })
        return calls


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

        try:
            response = await self.client.chat.completions.create(**kwargs)
        except BadRequestError as exc:
            # Groq returns HTTP 400 with a `failed_generation` field when the
            # model emits XML-style function calls instead of proper tool_calls.
            # Example: <function=list_directory{"path": "papers/"}</function>
            # We salvage those calls so the agentic loop can still execute them.
            body: dict = exc.body if isinstance(exc.body, dict) else {}
            failed_gen: str = body.get("error", {}).get("failed_generation", "")
            if failed_gen:
                tool_calls = self._parse_xml_function_calls(failed_gen)
                if tool_calls:
                    print(
                        f"[GroqProvider] Salvaged {len(tool_calls)} tool call(s) "
                        f"from failed_generation: {[tc['name'] for tc in tool_calls]}"
                    )
                    return {"text": "", "tool_calls": tool_calls, "stop_reason": "tool_use"}
            # Nothing salvageable — re-raise
            raise

        message = response.choices[0].message

        text = message.content or ""
        tool_calls: list[dict] = []

        if message.tool_calls:
            for tc in message.tool_calls:
                name, args = self._parse_tool_call(tc.function.name, tc.function.arguments)
                tool_calls.append({
                    "id": tc.id,
                    "name": name,
                    "input": args,
                })

        # Also scan message content for any stray XML-style function calls
        # (some models emit both a tool_call *and* text with embedded calls)
        if text:
            xml_calls = self._parse_xml_function_calls(text)
            if xml_calls:
                tool_calls.extend(xml_calls)
                # Strip the raw XML from the displayed text
                text = re.sub(r"<function=.*?</function>", "", text, flags=re.DOTALL).strip()

        stop_reason = "tool_use" if tool_calls else "end_turn"
        return {"text": text, "tool_calls": tool_calls, "stop_reason": stop_reason}
