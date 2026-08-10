"""Auth tests + payment webhook bad-path."""

from fastapi.testclient import TestClient

from app.main import app

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

    login = client.post(
        "/auth/login", json={"email": "user1@example.com", "password": "supersecret"}
    )
    assert login.status_code == 200

    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == "user1@example.com"


def test_login_wrong_password():
    _signup("pw@example.com")
    r = client.post("/auth/login", json={"email": "pw@example.com", "password": "nope12345"})
    assert r.status_code == 401


def test_duplicate_signup_rejected():
    _signup("dupe@example.com")
    r = _signup("dupe@example.com")
    assert r.status_code == 409


def test_bad_payment_callback_rejected():
    cb = client.post(
        "/payments/callback", json={"reference": "run_nope", "status": "failed"}
    )
    assert cb.status_code == 400


def test_unauthenticated_pipeline_blocked():
    # No token -> rejected before reaching any run logic.
    assert client.post("/runs", json={"scope": "thesis"}).status_code in (401, 403)
