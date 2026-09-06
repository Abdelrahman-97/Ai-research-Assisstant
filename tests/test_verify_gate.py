"""The email-verification gate: when enabled, a user must verify before starting
a job; when disabled (default), nothing changes."""

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.store import repository

client = TestClient(app)


def _signup(email):
    r = client.post("/auth/signup", json={"email": email, "password": "supersecret", "scope": "studies"})
    assert r.status_code == 201
    return r.json()["access_token"], r.json()["user"]["id"]


def test_gate_blocks_then_allows(monkeypatch):
    monkeypatch.setattr(settings, "require_email_verification", True, raising=False)
    token, uid = _signup("gate@ep.com")
    auth = {"Authorization": f"Bearer {token}"}

    # Unverified → blocked from starting a job.
    r = client.post("/runs", headers=auth, json={"scope": "studies"})
    assert r.status_code == 403

    # Verify the user, then it works.
    u = repository.users.get(uid)
    u.email_verified = True
    repository.users.save(u)
    r = client.post("/runs", headers=auth, json={"scope": "studies"})
    assert r.status_code == 201


def test_gate_off_by_default(monkeypatch):
    monkeypatch.setattr(settings, "require_email_verification", False, raising=False)
    token, _ = _signup("nogate@ep.com")
    auth = {"Authorization": f"Bearer {token}"}
    r = client.post("/runs", headers=auth, json={"scope": "studies"})
    assert r.status_code == 201
