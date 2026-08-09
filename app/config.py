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

    # Kimi / Moonshot (OpenAI-compatible API)
    moonshot_api_key: str = ""
    kimi_base_url: str = "https://api.moonshot.ai/v1"
    kimi_model: str = "kimi-k3"

    # External integrations
    copyleaks_api_key: str = ""
    pubmed_api_key: str = ""
    unpaywall_email: str = ""

    # Sandbox
    sandbox_image: str = "research-assistant-sandbox:latest"
    sandbox_timeout_seconds: int = 120
    # When Docker isn't available (e.g. early local dev), allow running scripts
    # directly in a subprocess. NEVER enable this in production — it removes the
    # isolation boundary. Off by default.
    sandbox_allow_subprocess_fallback: bool = False

    # Auth (JWT)
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24  # 24h

    # Payments (EasyKash)
    easykash_api_key: str = ""
    easykash_webhook_secret: str = ""
    easykash_base_url: str = "https://back.easykash.net/api/v1"

    # --- Pricing (all EGP). Tunable — change these to reprice without code edits. ---
    price_base_thesis_egp: int = 1500     # base price for a thesis results chapter
    price_base_paper_egp: int = 800       # base price for a paper's results section
    price_per_test_egp: int = 300         # per estimated statistical test
    price_per_1000_words_egp: int = 100   # per 1000 words of Results text
    price_per_1000_cells_egp: int = 20    # per 1000 data cells (rows x cols)

    # Storage retention: inputs + outputs kept this many days after acceptance.
    retention_days: int = 30

    # Storage — where uploads, generated scripts, and artifacts live at runtime.
    data_dir: str = "data"

    # Database. SQLite by default so the app runs with zero setup; point this at
    # Postgres for production, e.g. postgresql+psycopg2://user:pass@host:5432/db
    database_url: str = "sqlite:///./data/app.db"

    # CORS — comma-separated list of allowed frontend origins.
    cors_origins: str = "*"


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()


settings = get_settings()
