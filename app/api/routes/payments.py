"""Payment webhook: receive the EasyKash success callback.

- POST /payments/callback  (public webhook) -> EasyKash calls this on success;
  we verify it and unlock the corresponding RUN.

The pay link itself is created per-run at POST /runs/{id}/pay-link (it needs the
run's price quote), so it lives in the runs router.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.models.schemas import PaymentCallback
from app.services import orchestrator, payments
from app.store import repository

router = APIRouter(prefix="/payments", tags=["payments"])


@router.post("/callback")
def callback(body: PaymentCallback) -> dict:
    """Public webhook hit by EasyKash after a successful payment."""
    run_id = payments.verify_callback(body)
    if not run_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or unsuccessful payment callback.",
        )
    run = repository.runs.get(run_id)
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Unknown run."
        )
    orchestrator.mark_paid(run, body.reference)
    return {"status": "ok", "run_id": run_id, "paid": True}
