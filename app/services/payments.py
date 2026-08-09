"""EasyKash payment integration (create link + verify success callback).

Flow:
  1. create_payment_link(user) -> a URL we send the user to, plus a `reference`
     that identifies this payment. The reference encodes the user id so the
     callback can be tied back to the right account.
  2. EasyKash redirects the user to pay, then POSTs a success callback to our
     webhook. verify_callback() checks it's authentic and returns the user id
     to unlock.

NOTE: EasyKash's exact request/response field names and signing scheme should be
confirmed against their current merchant docs and adjusted in the two mapping
functions below (`_build_link_request` / `verify_callback`). The structure here
is deliberately isolated so that's the only place to change.
"""

from __future__ import annotations

import hashlib
import hmac

import httpx

from app.config import settings
from app.models.schemas import PaymentCallback, PaymentLink, UserPublic

# We prefix our reference so we can recover the user id from the callback without
# needing a payments table yet. Replace with a real payments record + DB later.
_REF_PREFIX = "ra"


def _make_reference(user_id: str) -> str:
    return f"{_REF_PREFIX}_{user_id}"


def user_id_from_reference(reference: str) -> str | None:
    if reference.startswith(f"{_REF_PREFIX}_"):
        return reference.split("_", 1)[1]
    return None


def _sign(reference: str) -> str:
    """HMAC signature over the reference, used to validate callbacks."""
    return hmac.new(
        settings.easykash_webhook_secret.encode(),
        reference.encode(),
        hashlib.sha256,
    ).hexdigest()


def _build_link_request(user: UserPublic, reference: str) -> dict:
    """Map our data to EasyKash's create-payment payload. Confirm field names."""
    return {
        "amount": settings.price_egp,
        "currency": "EGP",
        "reference": reference,
        "customer_email": user.email,
        "description": "AI Research Assistant — Results section",
    }


def create_payment_link(user: UserPublic) -> PaymentLink:
    """Create an EasyKash payment link for this user.

    If no API key is configured (local dev), returns a stub link that still
    carries a valid reference so the rest of the flow can be exercised.
    """
    reference = _make_reference(user.id)

    if not settings.easykash_api_key:
        return PaymentLink(
            url=f"https://pay.easykash.example/checkout?ref={reference}",
            reference=reference,
            amount_egp=settings.price_egp,
        )

    resp = httpx.post(
        f"{settings.easykash_base_url}/payment",
        json=_build_link_request(user, reference),
        headers={"Authorization": f"Bearer {settings.easykash_api_key}"},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    # Adjust the key below to EasyKash's actual response field for the pay URL.
    url = data.get("redirect_url") or data.get("url") or data.get("payment_url")
    return PaymentLink(url=url, reference=reference, amount_egp=settings.price_egp)


def verify_callback(callback: PaymentCallback) -> str | None:
    """Validate a success callback. Returns the user id to unlock, or None.

    Two checks: the status is a success, and (when a webhook secret is set) the
    signature matches. Confirm EasyKash's real status string + signing scheme.
    """
    if callback.status.lower() not in {"success", "paid", "completed"}:
        return None

    if settings.easykash_webhook_secret:
        expected = _sign(callback.reference)
        if not callback.signature or not hmac.compare_digest(expected, callback.signature):
            return None

    return user_id_from_reference(callback.reference)
