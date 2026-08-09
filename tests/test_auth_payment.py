"""Auth + payment-gate tests."""

from fastapi.testclient import TestClient

from app.main import app
from app.services import payments

client = TestClient(app)


def _signup(email="a@b.com"):
    return client.post(
        "/auth/signup",
        json={"email": email, "password": "supersecret", "scope": "thesis"},
    )


def test_signup_login_me():
    r = _signup("user1@example.com")
    assert r.status_code == 201
    token = r.json()["access_token"]
    assert r.json()["user"]["scope"] == "thesis"
    assert r.json()["user"]["has_paid"] is False

    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == "user1@example.com"


def test_duplicate_signup_rejected():
    _signup("dupe@example.com")
    r = _signup("dupe@example.com")
    assert r.status_code == 409


def test_pipeline_requires_payment_then_unlocks():
    r = _signup("payer@example.com")
    token = r.json()["access_token"]
    auth = {"Authorization": f"Bearer {token}"}

    # Blocked before payment.
    blocked = client.post("/runs", headers=auth)
    assert blocked.status_code == 402

    # Get a payment link (stub link in dev, but reference is real).
    link = client.post("/payments/link", headers=auth)
    assert link.status_code == 200
    reference = link.json()["reference"]

    # Simulate EasyKash success callback (no webhook secret set in tests).
    cb = client.post(
        "/payments/callback", json={"reference": reference, "status": "success"}
    )
    assert cb.status_code == 200 and cb.json()["unlocked"] is True

    # Now allowed.
    ok = client.post("/runs", headers=auth)
    assert ok.status_code == 201


def test_bad_callback_rejected():
    cb = client.post(
        "/payments/callback", json={"reference": "ra_nope", "status": "failed"}
    )
    assert cb.status_code == 400
