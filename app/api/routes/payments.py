"""Payment webhook: receive the EasyKash success callback.

- POST /payments/callback  (public webhook) -> EasyKash calls this on success.
  We (1) verify the HMAC signature over the raw body, (2) confirm success, and
  (3) unlock the corresponding RUN. The frontend is never trusted for payment.

The pay link itself is created per-run at POST /runs/{id}/pay-link (it needs the
run's price quote), so it lives in the runs router.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Request, status

from app.config import settings
from app.models.schemas import PaymentCallback
from app.ratelimit import limiter
from app.services import orchestrator, payments
from app.store import repository

router = APIRouter(prefix="/payments", tags=["payments"])


@router.post("/callback")
@limiter.limit("60/minute")
async def callback(request: Request) -> dict:
    """Public webhook hit by EasyKash after a payment. Signature-verified."""
    raw = await request.body()
    signature = request.headers.get(settings.easykash_signature_header)

    # 1) authenticity — HMAC over the raw body (skipped only if no secret set)
    if not payments.verify_raw_signature(raw, signature):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook signature.",
        )

    # 2) parse — map EasyKash's payload into our normalized shape.
    try:
        data = json.loads(raw or b"{}")
    except json.JSONDecodeError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Malformed body.")
    callback = PaymentCallback(
        reference=str(data.get("reference", "")),
        status=str(data.get("status", "")),
        signature=signature,
    )

    # 3) confirm success + map to a run
    run_id = payments.resolve_paid_run(callback)
    if not run_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or unsuccessful payment callback.",
        )
    run = repository.runs.get(run_id)
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown run.")

    orchestrator.mark_paid(run, callback.reference)
    return {"status": "ok", "run_id": run_id, "paid": True}
