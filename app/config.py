"""Application configuration.

Loads settings from environment variables (and a local .env file in dev)
using pydantic-settings. Import `settings` anywhere you need config.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Application
    app_env: str = "development"
    log_level: str = "INFO"

    # Anthropic / Claude
    anthropic_api_key: str = ""

    # External integrations
    copyleaks_api_key: str = ""
    pubmed_api_key: str = ""
    unpaywall_email: str = ""

    # Sandbox
    sandbox_image: str = "research-assistant-sandbox:latest"
    sandbox_timeout_seconds: int = 120


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()


settings = get_settings()
