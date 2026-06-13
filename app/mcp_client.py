import json
from contextlib import AsyncExitStack
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from app.config import settings
from app.llm import get_llm_provider
from app.llm.base import BaseLLMProvider


class MCPClientManager:
    def __init__(self):
        self.exit_stack = AsyncExitStack()
        self.llm: BaseLLMProvider | None = None
        self.available_tools: list[dict] = []
        self.available_prompts: list[dict] = []
        self.sessions: dict = {}  # maps tool/prompt names and resource URIs to sessions

    async def initialize(self):
        """Initialize the chosen LLM provider and connect to all MCP servers."""
        print(f"[LLM] Provider: {settings.LLM_PROVIDER.upper()}")
        try:
            self.llm = get_llm_provider()
            print(f"[LLM] Provider initialized successfully.")
        except ValueError as e:
            print(f"[Warning] {e}")

        await self.connect_to_servers()

    # ------------------------------------------------------------------
    # MCP server connection helpers
    # ------------------------------------------------------------------

    async def connect_to_server(self, server_name: str, server_config: dict):
        try:
            print(f"Connecting to MCP Server '{server_name}'...")

            server_params = StdioServerParameters(
                command=server_config["command"],
                args=server_config.get("args", []),
                env=server_config.get("env"),
            )

            stdio_transport = await self.exit_stack.enter_async_context(
                stdio_client(server_params)
            )
            read, write = stdio_transport
            session = await self.exit_stack.enter_async_context(
                ClientSession(read, write)
            )
            await session.initialize()

            try:
                response = await session.list_tools()
                for tool in response.tools:
                    self.sessions[tool.name] = session
                    self.available_tools.append({
                        "name": tool.name,
                        "description": tool.description,
                        "input_schema": tool.inputSchema,
                    })
                print(
                    f"Connected to '{server_name}' successfully. "
                    f"Registered tools: {[t.name for t in response.tools]}"
                )
            except Exception as e:
                print(f"No tools registered for {server_name}: {e}")

            try:
                prompts_response = await session.list_prompts()
                if prompts_response and prompts_response.prompts:
                    for prompt in prompts_response.prompts:
                        self.sessions[prompt.name] = session
                        self.available_prompts.append({
                            "name": prompt.name,
                            "description": prompt.description,
                            "arguments": [
                                {
                                    "name": arg.name if hasattr(arg, "name") else arg.get("name", ""),
                                    "description": arg.description if hasattr(arg, "description") else arg.get("description", ""),
                                    "required": arg.required if hasattr(arg, "required") else arg.get("required", False),
                                }
                                for arg in prompt.arguments
                            ] if prompt.arguments else [],
                        })
                    print(f"Registered prompts for '{server_name}': {[p.name for p in prompts_response.prompts]}")
            except Exception as e:
                print(f"No prompts registered for {server_name}: {e}")

            try:
                resources_response = await session.list_resources()
                if resources_response and resources_response.resources:
                    for resource in resources_response.resources:
                        resource_uri = str(resource.uri)
                        self.sessions[resource_uri] = session
                    print(f"Registered resources for '{server_name}': {[str(r.uri) for r in resources_response.resources]}")
            except Exception as e:
                print(f"No resources registered for {server_name}: {e}")

        except Exception as e:
            print(f"Error connecting to {server_name}: {e}")

    async def connect_to_servers(self):
        try:
            with open("server_config.json", "r") as file:
                data = json.load(file)
            servers = data.get("mcpServers", {})
            for server_name, server_config in servers.items():
                await self.connect_to_server(server_name, server_config)
        except Exception as e:
            print(f"Error loading server config: {e}")
            raise

    # ------------------------------------------------------------------
    # LLM query loop — provider-agnostic
    # ------------------------------------------------------------------

    async def process_query(self, query: str) -> dict:
        """
        Send a query through the configured LLM provider, executing any
        MCP tool calls requested by the model until a final text response
        is produced.
        """
        if not self.llm:
            return {
                "response": "LLM provider is not configured. Check your .env settings.",
                "tool_calls": [],
            }

        messages: list[dict] = [{"role": "user", "content": query}]
        tool_calls_executed: list[dict] = []
        final_response_text = ""

        while True:
            result = await self.llm.chat(
                messages=messages,
                tools=self.available_tools if self.available_tools else None,
            )

            text = result["text"]
            tool_calls = result["tool_calls"]
            stop_reason = result["stop_reason"]

            if text:
                final_response_text += text

            if stop_reason != "tool_use" or not tool_calls:
                break

            # Build assistant message to append to history.
            # We store tool calls in a format both providers can reconstruct from.
            assistant_tool_blocks = [
                {
                    "type": "tool_use",
                    "id": tc["id"],
                    "name": tc["name"],
                    "input": tc["input"],
                }
                for tc in tool_calls
            ]
            if text:
                assistant_tool_blocks.insert(0, {"type": "text", "text": text})

            messages.append({"role": "assistant", "content": assistant_tool_blocks})

            # Execute each tool call via the appropriate MCP session
            tool_result_blocks: list[dict] = []
            for tc in tool_calls:
                tool_calls_executed.append({
                    "id": tc["id"],
                    "name": tc["name"],
                    "input": tc["input"],
                })

                session = self.sessions.get(tc["name"])
                if not session:
                    tool_result_blocks.append({
                        "type": "tool_result",
                        "tool_use_id": tc["id"],
                        "content": f"Tool '{tc['name']}' not found.",
                        "is_error": True,
                    })
                    continue

                try:
                    mcp_result = await session.call_tool(tc["name"], arguments=tc["input"])
                    content_list = []
                    for item in mcp_result.content:
                        if hasattr(item, "text"):
                            content_list.append({"type": "text", "text": item.text})
                        else:
                            content_list.append({"type": "text", "text": str(item)})
                    tool_result_blocks.append({
                        "type": "tool_result",
                        "tool_use_id": tc["id"],
                        "content": content_list,
                    })
                except Exception as e:
                    tool_result_blocks.append({
                        "type": "tool_result",
                        "tool_use_id": tc["id"],
                        "content": str(e),
                        "is_error": True,
                    })

            messages.append({"role": "user", "content": tool_result_blocks})

        return {
            "response": final_response_text,
            "tool_calls": tool_calls_executed,
        }

    # ------------------------------------------------------------------
    # Resources & Prompts
    # ------------------------------------------------------------------

    async def get_resource(self, resource_uri: str) -> str:
        session = self.sessions.get(resource_uri)

        if not session and resource_uri.startswith("papers://"):
            for uri, sess in self.sessions.items():
                if uri.startswith("papers://"):
                    session = sess
                    break

        if not session:
            raise ValueError(f"Resource '{resource_uri}' not found.")

        result = await session.read_resource(uri=resource_uri)
        if result and result.contents:
            return result.contents[0].text
        return ""

    async def execute_prompt(self, prompt_name: str, args: dict) -> dict:
        session = self.sessions.get(prompt_name)
        if not session:
            raise ValueError(f"Prompt '{prompt_name}' not found.")

        result = await session.get_prompt(prompt_name, arguments=args)
        if result and result.messages:
            prompt_content = result.messages[0].content

            if isinstance(prompt_content, str):
                text = prompt_content
            elif hasattr(prompt_content, "text"):
                text = prompt_content.text
            else:
                text = " ".join(
                    item.text if hasattr(item, "text") else str(item)
                    for item in prompt_content
                )

            return await self.process_query(text)
        return {"response": "Failed to retrieve prompt content.", "tool_calls": []}

    async def cleanup(self):
        await self.exit_stack.aclose()
