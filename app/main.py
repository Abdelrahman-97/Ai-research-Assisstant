"""FastAPI entrypoint for the AI Research Assistant.

Run locally with:
    uvicorn app.main:app --reload

Full pipeline (all authenticated + paid, except signup/login and the payment
webhook):
    signup/login -> pay -> create run -> upload -> plan -> approve
    -> script -> execute -> results -> download
"""

from fastapi import FastAPI

from app.api.routes import auth, health, payments, runs

app = FastAPI(
    title="AI Research Assistant",
    description=(
        "Statistical analysis and Results-section writing assistant. "
        "AI proposes; a human confirms every judgment call; nothing is "
        "treated as fact until the sandbox or a human has verified it."
    ),
    version="0.2.0",
)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(payments.router)
app.include_router(runs.router)


@app.get("/")
def root():
    return {
        "name": "AI Research Assistant",
        "version": app.version,
        "docs": "/docs",
    }
