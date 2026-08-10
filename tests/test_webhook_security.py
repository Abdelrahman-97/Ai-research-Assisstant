"""Webhook signature enforcement (raw-body HMAC)."""

import hashlib
import hmac
import json

from fastapi.testclient import TestClient

from app.config import settings
from app.main import app

client = TestClient(app)


def test_bad_signature_rejected(monkeypatch):
    monkeypatch.setattr(settings, "easykash_webhook_secret", "shhh", raising=False)
    body = json.dumps({"reference": "run_x", "status": "success"}).encode()
    r = client.post(
        "/payments/callback",
        content=body,
        headers={"Content-Type": "application/json", "X-EasyKash-Signature": "deadbeef"},
    )
    assert r.status_code == 401


def test_good_signature_passes_check(monkeypatch):
    monkeypatch.setattr(settings, "easykash_webhook_secret", "shhh", raising=False)
    body = json.dumps({"reference": "run_unknown", "status": "success"}).encode()
    sig = hmac.new(b"shhh", body, hashlib.sha256).hexdigest()
    r = client.post(
        "/payments/callback",
        content=body,
        headers={"Content-Type": "application/json", "X-EasyKash-Signature": sig},
    )
    # Signature accepted; the run doesn't exist -> 404 (proves we got past auth).
    assert r.status_code == 404


def test_no_secret_skips_signature(monkeypatch):
    # Default test config has no secret -> signature not required (dev behaviour).
    monkeypatch.setattr(settings, "easykash_webhook_secret", "", raising=False)
    r = client.post("/payments/callback", json={"reference": "run_x", "status": "failed"})
    assert r.status_code == 400  # parsed fine, but status not a success
