from app.config import settings
from app.llm.base import BaseLLMProvider


def get_llm_provider() -> BaseLLMProvider:
    """
    Factory that reads LLM_PROVIDER from settings and returns the
    appropriate provider instance.

    Supported values for LLM_PROVIDER:
      - "anthropic"  →  AnthropicProvider (default)
      - "groq"       →  GroqProvider

    Raises:
        ValueError: If LLM_PROVIDER is set to an unsupported value.
        ValueError: If the required API key for the chosen provider is missing.
    """
    provider = settings.LLM_PROVIDER.lower().strip()

    if provider == "anthropic":
        from app.llm.anthropic_provider import AnthropicProvider
        if not settings.ANTHROPIC_API_KEY or settings.ANTHROPIC_API_KEY == "your_anthropic_api_key_here":
            raise ValueError(
                "LLM_PROVIDER=anthropic but ANTHROPIC_API_KEY is not set. "
                "Add it to your .env file."
            )
        return AnthropicProvider(
            api_key=settings.ANTHROPIC_API_KEY,
            model=settings.ANTHROPIC_MODEL,
        )

    if provider == "groq":
        from app.llm.groq_provider import GroqProvider
        if not settings.GROQ_API_KEY or settings.GROQ_API_KEY == "your_groq_api_key_here":
            raise ValueError(
                "LLM_PROVIDER=groq but GROQ_API_KEY is not set. "
                "Add it to your .env file."
            )
        return GroqProvider(
            api_key=settings.GROQ_API_KEY,
            model=settings.GROQ_MODEL,
        )

    raise ValueError(
        f"Unsupported LLM_PROVIDER='{provider}'. "
        "Supported values: 'anthropic', 'groq'."
    )
