"""FastAPI entrypoint for the AI Research Assistant.

Run locally with:
    uvicorn app.main:app --reload

Full pipeline (all authenticated + paid, except signup/login and the payment
webhook):
    signup/login -> pay -> create run -> upload -> plan -> approve
    -> script -> execute -> results -> download
"""

import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi import _rate_limit_exceeded_handler

from app.api.routes import admin, auth, health, payments, runs, tools
from app.config import settings
from app.db import init_db
from app.ratelimit import limiter

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

app = FastAPI(
    title="Neura",
    description=(
        "Neura — the smart research assistant. AI proposes; a human confirms "
        "every judgment call; nothing is treated as fact until the sandbox or a "
        "human has verified it."
    ),
    version="1.0.0",
)

_origins = ["*"] if settings.cors_origins.strip() == "*" else [
    o.strip() for o in settings.cors_origins.split(",") if o.strip()
]
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    # We authenticate with bearer tokens (not cookies), so credentials aren't
    # needed — and "*" origins with credentials is invalid per the CORS spec.
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(payments.router)
app.include_router(runs.router)
app.include_router(tools.router)
app.include_router(admin.router)

# Serve the frontend from /ui when the folder is present (dev convenience).
_frontend_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
if os.path.isdir(_frontend_dir):
    app.mount("/ui", StaticFiles(directory=_frontend_dir, html=True), name="ui")


@app.on_event("startup")
def _startup() -> None:
    init_db()
    for sub in ("uploads", "artifacts", "outputs"):
        os.makedirs(os.path.join(settings.data_dir, sub), exist_ok=True)
    logging.getLogger("app").info("Neura %s started", app.version)


@app.get("/")
def root():
    return {
        "name": "Neura",
        "version": app.version,
        "docs": "/docs",
    }
