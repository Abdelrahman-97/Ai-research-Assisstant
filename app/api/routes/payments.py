"""Payment routes: create an EasyKash link, and receive the success callback.

- POST /payments/link      (authenticated) -> returns a payment URL
- POST /payments/callback  (public webhook) -> EasyKash calls this on success;
  we verify it and unlock the user's access.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_current_user
from app.models.schemas import PaymentCallback, PaymentLink, User, UserPublic
from app.services import payments
from app.store import repository

router = APIRouter(prefix="/payments", tags=["payments"])


@router.post("/link", response_model=PaymentLink)
def create_link(user: User = Depends(get_current_user)) -> PaymentLink:
    return payments.create_payment_link(UserPublic(**user.model_dump()))


@router.post("/callback")
def callback(body: PaymentCallback) -> dict:
    """Public webhook hit by EasyKash after a successful payment."""
    user_id = payments.verify_callback(body)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or unsuccessful payment callback.",
        )
    user = repository.users.get(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Unknown user."
        )
    user.has_paid = True
    repository.users.save(user)
    return {"status": "ok", "unlocked": True}
