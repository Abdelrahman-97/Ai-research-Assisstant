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

    # LLM (any OpenAI-compatible provider: Gemini, Groq, OpenRouter, Ollama, Kimi…).
    # Switch providers by changing these three values — no code changes.
    # Default points at Google Gemini's OpenAI-compatible endpoint.
    llm_api_key: str = ""
    llm_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai/"
    llm_model: str = "gemini-2.5-flash"

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
    # Force subprocess execution even if Docker is present (used by the proof
    # harness so it runs without building the sandbox image). Dev only.
    sandbox_force_subprocess: bool = False

    # Auth (JWT)
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24  # 24h

    # Payments (EasyKash)
    easykash_api_key: str = ""
    easykash_webhook_secret: str = ""
    easykash_base_url: str = "https://back.easykash.net/api/v1"
    # Header EasyKash sends the callback signature in. Confirm exact name in the
    # merchant portal; this is the commonly-used default.
    easykash_signature_header: str = "X-EasyKash-Signature"
    # Fees: 3.5% commission + flat buyer surcharge (EGP). If pass_fees_to_customer
    # is true, the customer is billed enough that you net your quoted price.
    easykash_commission_rate: float = 0.035
    easykash_flat_fee_egp: int = 5
    easykash_pass_fees_to_customer: bool = True

    # Security
    rate_limit_enabled: bool = True
    max_protocol_chars: int = 20000

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
