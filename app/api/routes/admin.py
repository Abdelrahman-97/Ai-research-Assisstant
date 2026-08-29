"""Admin / ops endpoints — guarded by a shared ADMIN_TOKEN header.

Minimal operational visibility so you can see activity and mark refunds without
touching the database directly. Disabled entirely unless settings.admin_token is
set. Send the token in the `X-Admin-Token` header.
"""

from __future__ import annotations

from collections import Counter

from fastapi import APIRouter, Depends, Header, HTTPException, status

from app.config import settings
from app.models.schemas import Run
from app.store import repository

router = APIRouter(prefix="/admin", tags=["admin"])


def _require_admin(x_admin_token: str | None = Header(default=None)) -> None:
    if not settings.admin_token:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Not found."
        )  # feature disabled -> don't reveal it exists
    if x_admin_token != settings.admin_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid admin token."
        )


@router.get("/stats", dependencies=[Depends(_require_admin)])
def stats() -> dict:
    users = repository.users.all()
    runs = repository.runs.all()
    by_status = Counter(r.status.value for r in runs)
    paid = [r for r in runs if r.paid]
    revenue = sum((r.quote.amount_egp if r.quote else 0) for r in paid if not r.refunded)
    return {
        "users": len(users),
        "runs_total": len(runs),
        "runs_by_status": dict(by_status),
        "paid_runs": len(paid),
        "refunded_runs": sum(1 for r in runs if r.refunded),
        "net_revenue_egp": revenue,
    }


@router.get("/runs", response_model=list[Run], dependencies=[Depends(_require_admin)])
def list_all_runs() -> list[Run]:
    return sorted(repository.runs.all(), key=lambda r: r.created_at, reverse=True)


@router.post("/runs/{run_id}/refund", response_model=Run, dependencies=[Depends(_require_admin)])
def mark_refunded(run_id: str) -> Run:
    run = repository.runs.get(run_id)
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found.")
    run.refunded = True
    return repository.runs.save(run)
