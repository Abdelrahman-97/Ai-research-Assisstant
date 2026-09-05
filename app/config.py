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
    llm_timeout_seconds: int = 60      # per-request timeout
    llm_max_retries: int = 2           # SDK retries transient errors (429/5xx/network)

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

    # Execution mode:
    #   "inline"  — /execute runs the script synchronously in the API process
    #               (default; used by dev + the whole test suite).
    #   "worker"  — /execute only enqueues the run; a separate background worker
    #               service picks it up, runs it, writes the results, and marks
    #               it completed. This is the production topology on Render.
    execution_mode: str = "inline"
    # How often the worker polls the queue, and how many runs it claims per pass.
    worker_poll_seconds: float = 5.0
    worker_batch: int = 1

    # Auth (JWT)
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24  # 24h
    verify_token_minutes: int = 60 * 24        # email verification link: 24h
    reset_token_minutes: int = 30              # password reset link: 30 min

    # Email (SMTP). If smtp_host is empty, emails are logged instead of sent (dev).
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_use_tls: bool = True
    # Base URL of the frontend, used to build verification/reset links.
    frontend_url: str = "http://localhost:8000/ui"

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
    max_upload_mb: int = 25              # reject data files larger than this
    max_summary_columns: int = 60        # cap columns described to the model

    # Admin/ops. If set, unlocks the /admin endpoints (guarded by this token).
    admin_token: str = ""

    # --- Pricing (all EGP). Tunable — change these to reprice without code edits. ---
    price_base_thesis_egp: int = 600      # base price for a thesis results chapter
    price_base_paper_egp: int = 350       # base price for a paper's results section
    price_per_test_egp: int = 100         # per estimated statistical test
    price_per_1000_words_egp: int = 40    # per 1000 words of Results text
    price_per_1000_cells_egp: int = 10    # per 1000 data cells (rows x cols)
    # Optional human expert add-ons (EGP). "review" = an expert checks the AI's
    # results; "full" = an expert performs the whole analysis (longer turnaround).
    price_consultation_review_egp: int = 500
    price_consultation_full_egp: int = 3000

    # --- Analyst assistant (free-text control layer) ---
    assistant_enabled: bool = True
    assistant_model: str = ""             # falls back to llm_model if empty
    assistant_max_message_chars: int = 4000
    # Default interaction tier when the user doesn't pick one.
    assistant_default_tier: str = "basic"

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


# --------------------------------------------------------------------------- #
# Interaction (assistant) tiers.
#
# Each tier includes a number of analyst messages and adds a surcharge to the
# quote. Chosen at the price-estimate step. Edit freely to reprice — order here
# is the order shown to the user; the first is the default/free tier.
# --------------------------------------------------------------------------- #
ASSISTANT_TIERS: dict[str, dict] = {
    "basic":    {"label": "Basic",    "messages": 8,   "extra_egp": 0,
                 "blurb": "Edit the plan and ask a few questions."},
    "standard": {"label": "Standard", "messages": 25,  "extra_egp": 75,
                 "blurb": "Refine tests, re-run, and iterate comfortably."},
    "pro":      {"label": "Pro",      "messages": 80,  "extra_egp": 200,
                 "blurb": "Heavy back-and-forth and multiple analyses."},
}


def get_tier(name: str | None) -> dict:
    """Return a tier config by name, falling back to the default tier."""
    return ASSISTANT_TIERS.get(
        name or settings.assistant_default_tier,
        ASSISTANT_TIERS[settings.assistant_default_tier],
    )
