from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.endpoints import router as api_router
from app.mcp_client import MCPClientManager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize MCP client manager and connect to servers
    print("Initializing MCP Client Manager and connecting to servers...")
    mcp_client = MCPClientManager()
    await mcp_client.initialize()
    app.state.mcp_client = mcp_client
    
    yield
    
    # Shutdown: Close all MCP sessions and stop subprocesses
    print("Cleaning up MCP sessions and connection exit stacks...")
    await mcp_client.cleanup()

app = FastAPI(
    title="MCP Production Backend",
    description="FastAPI service for Model Context Protocol client-side orchestration",
    version="1.0.0",
    lifespan=lifespan
)

# Allow CORS for easy frontend integration (e.g. React/Vite, Next.js, or simple index.html)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api")

@app.get("/")
async def root():
    return {
        "status": "healthy",
        "service": "MCP Backend Server",
        "documentation": "/docs"
    }
