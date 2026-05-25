from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=["../.env", ".env"], extra="ignore")

    database_url: str = "postgresql+asyncpg://advisor:advisor@localhost:5432/commodity_advisor"
    redis_url: str = "redis://localhost:6379"
    fred_api_key: str = ""
    timezone: str = "America/New_York"

    scheduler_enabled: bool = True
    finbert_device: int = -1

    sentiment_rss_timeout_s: float = 15.0
    yfinance_delay_s: float = 1.0

    cors_origins: str = "*"

    # API key auth. If empty, write endpoints are unprotected (dev mode).
    # Set in .env as ``API_KEY=<random-string>`` for any deployed instance.
    api_key: str = ""

    # Agent pipeline (Claude + web search).
    anthropic_api_key: str = ""
    tavily_api_key: str = ""
    agent_top_n_per_sector: int = 10
    agent_model: str = "claude-sonnet-4-6"
    agent_overseer_model: str = "claude-sonnet-4-6"


@lru_cache
def get_settings() -> Settings:
    return Settings()


def parse_cors(s: str) -> list[str]:
    if s.strip() == "*":
        return ["*"]
    return [x.strip() for x in s.split(",") if x.strip()]
