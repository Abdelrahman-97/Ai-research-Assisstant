"""EasyKash payment integration (create link + verify success callback).

Payment is per-RUN and happens after the price estimate. Flow:
  1. create_payment_link(run, email, amount) -> a URL we send the user to, plus a
     `reference` that identifies this run's payment (the reference encodes the
     run id, so the callback can be tied back to the right run).
  2. EasyKash redirects the user to pay, then POSTs a success callback to our
     webhook. verify_callback() checks it's authentic and returns the run id to
     unlock.

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
from app.models.schemas import PaymentCallback, PaymentLink

# We prefix our reference so we can recover the run id from the callback.
_REF_PREFIX = "run"


def _make_reference(run_id: str) -> str:
    return f"{_REF_PREFIX}_{run_id}"


def run_id_from_reference(reference: str) -> str | None:
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


def _build_link_request(email: str, reference: str, amount_egp: int) -> dict:
    """Map our data to EasyKash's create-payment payload. Confirm field names."""
    return {
        "amount": amount_egp,
        "currency": "EGP",
        "reference": reference,
        "customer_email": email,
        "description": "AI Research Assistant — Results section",
    }


def create_payment_link(run_id: str, email: str, amount_egp: int) -> PaymentLink:
    """Create an EasyKash payment link for this run.

    If no API key is configured (local dev), returns a stub link that still
    carries a valid reference so the rest of the flow can be exercised.
    """
    reference = _make_reference(run_id)

    if not settings.easykash_api_key:
        return PaymentLink(
            url=f"https://pay.easykash.example/checkout?ref={reference}",
            reference=reference,
            amount_egp=amount_egp,
        )

    resp = httpx.post(
        f"{settings.easykash_base_url}/payment",
        json=_build_link_request(email, reference, amount_egp),
        headers={"Authorization": f"Bearer {settings.easykash_api_key}"},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    # Adjust the key below to EasyKash's actual response field for the pay URL.
    url = data.get("redirect_url") or data.get("url") or data.get("payment_url")
    return PaymentLink(url=url, reference=reference, amount_egp=amount_egp)


def verify_callback(callback: PaymentCallback) -> str | None:
    """Validate a success callback. Returns the run id to unlock, or None.

    Two checks: the status is a success, and (when a webhook secret is set) the
    signature matches. Confirm EasyKash's real status string + signing scheme.
    """
    if callback.status.lower() not in {"success", "paid", "completed"}:
        return None

    if settings.easykash_webhook_secret:
        expected = _sign(callback.reference)
        if not callback.signature or not hmac.compare_digest(expected, callback.signature):
            return None

    return run_id_from_reference(callback.reference)
