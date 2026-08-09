"""FastAPI entrypoint for the AI Research Assistant.

Run locally with:
    uvicorn app.main:app --reload
"""

from fastapi import FastAPI

from app.api.routes import health

app = FastAPI(
    title="AI Research Assistant",
    description=(
        "Statistical analysis and Results-section writing assistant. "
        "AI proposes; a human confirms every judgment call; nothing is "
        "treated as fact until the sandbox or a human has verified it."
    ),
    version="0.1.0",
)

app.include_router(health.router)


@app.get("/")
def root():
    return {
        "name": "AI Research Assistant",
        "version": app.version,
        "docs": "/docs",
    }
