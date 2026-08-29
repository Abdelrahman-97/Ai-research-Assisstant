"""Email verification + password reset flows.

Email sending is captured (not actually sent) so we can pull the tokens out of
the links the app generates.
"""

import re

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import email

client = TestClient(app)


@pytest.fixture
def sent(monkeypatch):
    """Capture verification + reset links instead of emailing them."""
    box: dict[str, str] = {}

    def _token(link: str) -> str:
        m = re.search(r"token=([^\s&]+)", link)
        return m.group(1) if m else ""

    monkeypatch.setattr(email, "send_verification", lambda to, link: box.__setitem__("verify", _token(link)))
    monkeypatch.setattr(email, "send_password_reset", lambda to, link: box.__setitem__("reset", _token(link)))
    return box


def _signup(e="v@example.com"):
    return client.post("/auth/signup", json={"email": e, "password": "supersecret", "scope": "thesis"})


def test_signup_sends_verification_and_verify_works(sent):
    r = _signup("verify@example.com")
    assert r.status_code == 201
    assert r.json()["user"]["email_verified"] is False
    assert sent.get("verify")  # a verification email was generated

    v = client.post("/auth/verify-email", json={"token": sent["verify"]})
    assert v.status_code == 200 and v.json()["email_verified"] is True


def test_verify_bad_token_rejected(sent):
    assert client.post("/auth/verify-email", json={"token": "garbage"}).status_code == 400


def test_forgot_password_is_generic_for_unknown_email(sent):
    # Unknown email still returns ok (no user enumeration).
    r = client.post("/auth/forgot-password", json={"email": "nobody@example.com"})
    assert r.status_code == 200 and r.json()["ok"] is True
    assert "reset" not in sent  # nothing sent for a non-existent account


def test_password_reset_flow_and_session_invalidation(sent):
    _signup("reset@example.com")
    old = client.post("/auth/login", json={"email": "reset@example.com", "password": "supersecret"})
    old_token = old.json()["access_token"]
    old_auth = {"Authorization": f"Bearer {old_token}"}
    assert client.get("/auth/me", headers=old_auth).status_code == 200

    # request reset
    client.post("/auth/forgot-password", json={"email": "reset@example.com"})
    assert sent.get("reset")

    # reset with the token
    res = client.post("/auth/reset-password", json={"token": sent["reset"], "new_password": "brandnewpass"})
    assert res.status_code == 200
    new_auth = {"Authorization": f"Bearer {res.json()['access_token']}"}

    # old session is now invalid (token_version bumped)
    assert client.get("/auth/me", headers=old_auth).status_code == 401
    # new session works
    assert client.get("/auth/me", headers=new_auth).status_code == 200

    # login with new password works, old password fails
    assert client.post("/auth/login", json={"email": "reset@example.com", "password": "brandnewpass"}).status_code == 200
    assert client.post("/auth/login", json={"email": "reset@example.com", "password": "supersecret"}).status_code == 401

    # the used reset link can't be reused
    assert client.post("/auth/reset-password", json={"token": sent["reset"], "new_password": "anotherpass"}).status_code == 400
