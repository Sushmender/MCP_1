import json
from contextlib import AsyncExitStack
from anthropic import AsyncAnthropic
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from app.config import settings

class MCPClientManager:
    def __init__(self):
        self.exit_stack = AsyncExitStack()
        self.anthropic = None
        self.available_tools = []
        self.available_prompts = []
        self.sessions = {}  # maps tool/prompt names and resources to sessions

    async def initialize(self):
        """Initialize connection to Anthropic client and all MCP servers."""
        if not settings.ANTHROPIC_API_KEY or settings.ANTHROPIC_API_KEY == "your_anthropic_api_key_here":
            print("[Warning] ANTHROPIC_API_KEY is not configured or is using the placeholder.")
        self.anthropic = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        await self.connect_to_servers()

    async def connect_to_server(self, server_name: str, server_config: dict):
        try:
            print(f"Connecting to MCP Server '{server_name}'...")
            
            # StdioServerParameters configuration
            server_params = StdioServerParameters(
                command=server_config["command"],
                args=server_config.get("args", []),
                env=server_config.get("env")
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
                # List available tools
                response = await session.list_tools()
                for tool in response.tools:
                    self.sessions[tool.name] = session
                    self.available_tools.append({
                        "name": tool.name,
                        "description": tool.description,
                        "input_schema": tool.inputSchema
                    })
                print(f"Connected to '{server_name}' successfully. Registered tools: {[t.name for t in response.tools]}")
            except Exception as e:
                print(f"No tools registered for {server_name}: {e}")
            
            try:
                # List available prompts
                prompts_response = await session.list_prompts()
                if prompts_response and prompts_response.prompts:
                    for prompt in prompts_response.prompts:
                        self.sessions[prompt.name] = session
                        self.available_prompts.append({
                            "name": prompt.name,
                            "description": prompt.description,
                            "arguments": [
                                {
                                    "name": arg.name if hasattr(arg, 'name') else arg.get('name', ''),
                                    "description": arg.description if hasattr(arg, 'description') else arg.get('description', ''),
                                    "required": arg.required if hasattr(arg, 'required') else arg.get('required', False)
                                }
                                for arg in prompt.arguments
                            ] if prompt.arguments else []
                        })
                    print(f"Registered prompts for '{server_name}': {[p.name for p in prompts_response.prompts]}")
            except Exception as e:
                print(f"No prompts registered for {server_name}: {e}")

            try:
                # List available resources
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

    async def process_query(self, query: str):
        """Send a query to Anthropic with tool options and resolve tool execution loop."""
        messages = [{'role': 'user', 'content': query}]
        tool_calls_executed = []
        final_response_text = ""
        
        while True:
            # Map standard tools list to Claude API format
            tools_arg = self.available_tools if self.available_tools else None
            
            response = await self.anthropic.messages.create(
                max_tokens=2048,
                model='claude-3-7-sonnet-20250219',
                tools=tools_arg,
                messages=messages
            )
            
            assistant_content = []
            has_tool_use = False
            
            for content in response.content:
                if content.type == 'text':
                    final_response_text += content.text
                    assistant_content.append(content)
                elif content.type == 'tool_use':
                    has_tool_use = True
                    assistant_content.append(content)
                    
                    # Record the tool call
                    tool_calls_executed.append({
                        "id": content.id,
                        "name": content.name,
                        "input": content.input
                    })
                    
                    # Append assistant message with tool use block
                    messages.append({'role': 'assistant', 'content': assistant_content})
                    
                    # Get session and call tool
                    session = self.sessions.get(content.name)
                    if not session:
                        err_msg = f"Tool '{content.name}' not found."
                        messages.append({
                            "role": "user",
                            "content": [
                                {
                                    "type": "tool_result",
                                    "tool_use_id": content.id,
                                    "content": err_msg,
                                    "is_error": True
                                }
                            ]
                        })
                        break
                        
                    try:
                        result = await session.call_tool(content.name, arguments=content.input)
                        # Serialize content to plain structures
                        content_list = []
                        for item in result.content:
                            if hasattr(item, 'text'):
                                content_list.append({"type": "text", "text": item.text})
                            else:
                                content_list.append({"type": "text", "text": str(item)})
                        
                        messages.append({
                            "role": "user", 
                            "content": [
                                {
                                    "type": "tool_result",
                                    "tool_use_id": content.id,
                                    "content": content_list
                                }
                            ]
                        })
                    except Exception as e:
                        messages.append({
                            "role": "user",
                            "content": [
                                {
                                    "type": "tool_result",
                                    "tool_use_id": content.id,
                                    "content": str(e),
                                    "is_error": True
                                }
                            ]
                        })
            
            if not has_tool_use:
                break
                
        return {
            "response": final_response_text,
            "tool_calls": tool_calls_executed
        }

    async def get_resource(self, resource_uri: str) -> str:
        session = self.sessions.get(resource_uri)
        
        # Fallback for papers URIs
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
        else:
            return ""

    async def execute_prompt(self, prompt_name: str, args: dict) -> dict:
        session = self.sessions.get(prompt_name)
        if not session:
            raise ValueError(f"Prompt '{prompt_name}' not found.")
        
        result = await session.get_prompt(prompt_name, arguments=args)
        if result and result.messages:
            prompt_content = result.messages[0].content
            
            # Extract text from content
            if isinstance(prompt_content, str):
                text = prompt_content
            elif hasattr(prompt_content, 'text'):
                text = prompt_content.text
            else:
                text = " ".join(item.text if hasattr(item, 'text') else str(item) 
                              for item in prompt_content)
            
            return await self.process_query(text)
        return {"response": "Failed to retrieve prompt content.", "tool_calls": []}

    async def cleanup(self):
        await self.exit_stack.aclose()
