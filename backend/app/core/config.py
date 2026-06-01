from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=["../.env", ".env"], extra="ignore")

    database_url: str = "postgresql+asyncpg://advisor:advisor@localhost:5432/commodity_advisor"
    redis_url: str = "redis://localhost:6379"
    fred_api_key: str = ""
    eia_api_key: str = ""
    timezone: str = "America/New_York"

    scheduler_enabled: bool = True
    finbert_device: int = -1

    sentiment_rss_timeout_s: float = 15.0
    yfinance_delay_s: float = 1.0

    cors_origins: str = "*"

    # API key auth. If empty, write endpoints are unprotected (dev mode).
    # Set in .env as ``API_KEY=<random-string>`` for any deployed instance.
    api_key: str = ""

    # Agent pipeline — LLM provider selection.
    # "groq" = free tier with Llama 3.3 70B (sign up at console.groq.com, no billing required)
    # "anthropic" = Claude models (paid — use as fallback or for higher quality)
    llm_provider: str = "cerebras"  # "cerebras" | "gemini" | "groq" | "anthropic"

    # Cerebras settings (free — 1M tokens/day, sign up at cloud.cerebras.ai)
    cerebras_api_key: str = ""
    cerebras_model: str = "zai-glm-4.7"
    cerebras_overseer_model: str = "zai-glm-4.7"

    # Gemini settings (free — 20 req/day on 2.5-flash)
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    gemini_overseer_model: str = "gemini-2.5-flash"

    # Groq settings (free — 100K TPD on 70B)
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"
    groq_overseer_model: str = "llama-3.3-70b-versatile"

    # Anthropic settings (fallback / paid)
    anthropic_api_key: str = ""
    agent_model: str = "claude-haiku-4-5-20251001"
    agent_overseer_model: str = "claude-haiku-4-5-20251001"

    # Optionally use a different provider just for the overseer + debate agents.
    # Empty string = use llm_provider for everything.
    # Example: set OVERSEER_LLM_PROVIDER=anthropic to use Claude for the overseer
    # while sub-agents run on the cheaper/free llm_provider.
    overseer_llm_provider: str = ""

    tavily_api_key: str = ""
    agent_top_n_per_sector: int = 10
    # Set to true to run the full agent pipeline on schedule (Mon-Fri 09:00 NY).
    agent_analysis_scheduled: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()


def get_active_model(*, overseer: bool = False) -> str:
    """Return the correct model name for the configured llm_provider."""
    s = get_settings()
    if s.llm_provider == "cerebras":
        return s.cerebras_overseer_model if overseer else s.cerebras_model
    if s.llm_provider == "gemini":
        return s.gemini_overseer_model if overseer else s.gemini_model
    if s.llm_provider == "groq":
        return s.groq_overseer_model if overseer else s.groq_model
    return s.agent_overseer_model if overseer else s.agent_model


def get_active_overseer_model() -> str:
    """Return the model name for the overseer/debate phase.

    Respects overseer_llm_provider if set, otherwise falls back to get_active_model(overseer=True).
    """
    s = get_settings()
    provider = s.overseer_llm_provider or s.llm_provider
    if provider == "cerebras":
        return s.cerebras_overseer_model
    if provider == "gemini":
        return s.gemini_overseer_model
    if provider == "groq":
        return s.groq_overseer_model
    return s.agent_overseer_model


def parse_cors(s: str) -> list[str]:
    if s.strip() == "*":
        return ["*"]
    return [x.strip() for x in s.split(",") if x.strip()]
