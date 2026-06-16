import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Settings:
    # --- Provider selection ---
    # Set to "cerebras", "groq", or "anthropic"
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "cerebras")

    # --- Cerebras ---
    CEREBRAS_API_KEY: str = os.getenv("CEREBRAS_API_KEY", "")
    CEREBRAS_MODEL: str = os.getenv("CEREBRAS_MODEL", "gpt-oss-120b")

    # --- Groq ---
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    GROQ_MODEL: str = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

    # --- Anthropic ---
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    ANTHROPIC_MODEL: str = os.getenv("ANTHROPIC_MODEL", "claude-3-7-sonnet-20250219")

    # --- Server ---
    HOST: str = os.getenv("HOST", "127.0.0.1")
    PORT: int = int(os.getenv("PORT", "8000"))

    # Path to the MCP servers configuration JSON file.
    # Can be overridden via SERVER_CONFIG_PATH in .env
    SERVER_CONFIG_PATH: str = os.getenv("SERVER_CONFIG_PATH", "server_config.json")
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "info")

    # Maximum seconds to wait for a prompt execution to complete.
    # Increase this for prompts that chain many tool calls (e.g. compare_papers
    # with uncached paper IDs that trigger search_papers + extract_info).
    PROMPT_TIMEOUT_SECS: int = int(os.getenv("PROMPT_TIMEOUT_SECS", "300"))

settings = Settings()
