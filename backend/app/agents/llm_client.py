"""LLM client factory — returns the right async client based on llm_provider config."""
from __future__ import annotations

from typing import Any

from app.core.config import get_settings


def make_agent_client() -> tuple[Any, str, str]:
    """Return (client, model, overseer_model) based on the configured provider.

    Raises ValueError if the required API key is missing.
    """
    settings = get_settings()
    provider = settings.llm_provider.lower()

    if provider == "cerebras":
        if not settings.cerebras_api_key:
            raise ValueError(
                "llm_provider=cerebras but CEREBRAS_API_KEY is not set. "
                "Get a free key at https://cloud.cerebras.ai and add CEREBRAS_API_KEY to your .env"
            )
        from openai import AsyncOpenAI
        client = AsyncOpenAI(
            api_key=settings.cerebras_api_key,
            base_url="https://api.cerebras.ai/v1",
        )
        return client, settings.cerebras_model, settings.cerebras_overseer_model

    if provider == "gemini":
        if not settings.gemini_api_key:
            raise ValueError(
                "llm_provider=gemini but GEMINI_API_KEY is not set. "
                "Get a free key at https://aistudio.google.com and add GEMINI_API_KEY to your .env"
            )
        from openai import AsyncOpenAI
        client = AsyncOpenAI(
            api_key=settings.gemini_api_key,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        )
        return client, settings.gemini_model, settings.gemini_overseer_model

    if provider == "groq":
        if not settings.groq_api_key:
            raise ValueError(
                "llm_provider=groq but GROQ_API_KEY is not set. "
                "Sign up free at https://console.groq.com and add GROQ_API_KEY to your .env"
            )
        from openai import AsyncOpenAI
        client = AsyncOpenAI(
            api_key=settings.groq_api_key,
            base_url="https://api.groq.com/openai/v1",
        )
        return client, settings.groq_model, settings.groq_overseer_model

    if provider == "anthropic":
        if not settings.anthropic_api_key:
            raise ValueError("llm_provider=anthropic but ANTHROPIC_API_KEY is not set.")
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        return client, settings.agent_model, settings.agent_overseer_model

    raise ValueError(f"Unknown llm_provider={provider!r}. Must be 'gemini', 'groq' or 'anthropic'.")


def make_overseer_client() -> tuple[Any, str]:
    """Return (client, model) for the overseer + debate phase.

    Uses OVERSEER_LLM_PROVIDER if set, otherwise falls back to the main llm_provider.
    """
    settings = get_settings()
    provider = (settings.overseer_llm_provider or settings.llm_provider).lower()

    if provider == "anthropic":
        if not settings.anthropic_api_key:
            raise ValueError(
                "overseer_llm_provider=anthropic but ANTHROPIC_API_KEY is not set."
            )
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        return client, settings.agent_overseer_model

    if provider == "cerebras":
        from openai import AsyncOpenAI
        client = AsyncOpenAI(
            api_key=settings.cerebras_api_key,
            base_url="https://api.cerebras.ai/v1",
        )
        return client, settings.cerebras_overseer_model

    if provider == "gemini":
        from openai import AsyncOpenAI
        client = AsyncOpenAI(
            api_key=settings.gemini_api_key,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        )
        return client, settings.gemini_overseer_model

    if provider == "groq":
        from openai import AsyncOpenAI
        client = AsyncOpenAI(
            api_key=settings.groq_api_key,
            base_url="https://api.groq.com/openai/v1",
        )
        return client, settings.groq_overseer_model

    raise ValueError(f"Unknown overseer_llm_provider={provider!r}.")
