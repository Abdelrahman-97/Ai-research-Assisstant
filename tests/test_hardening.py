"""Hardening tests: upload cap, LLM-failure handling, account deletion, admin."""

import io

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.services import planner
from app.services.llm_client import LLMError

client = TestClient(app)


def _auth(email):
    r = client.post("/auth/signup", json={"email": email, "password": "supersecret", "scope": "studies"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_oversized_upload_rejected(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "data_dir", str(tmp_path), raising=False)
    monkeypatch.setattr(settings, "max_upload_mb", 1, raising=False)  # 1 MB cap
    auth = _auth("big@ex.com")
    run_id = client.post("/runs", headers=auth, json={"scope": "studies"}).json()["id"]

    big = io.BytesIO(b"group,score\n" + b"a,1\n" * 400_000)  # ~1.6 MB > 1 MB cap
    r = client.post(f"/runs/{run_id}/upload", headers=auth,
                    data={"protocol": "x"}, files={"data_file": ("big.csv", big, "text/csv")})
    assert r.status_code == 413


def test_llm_failure_returns_503(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "data_dir", str(tmp_path), raising=False)
    # Make the planner raise as if the AI provider failed.
    monkeypatch.setattr(planner, "propose_plan", lambda **k: (_ for _ in ()).throw(LLMError("boom")))

    auth = _auth("fail@ex.com")
    run_id = client.post("/runs", headers=auth, json={"scope": "studies"}).json()["id"]
    data = tmp_path / "d.csv"
    pd.DataFrame({"group": ["a", "b"], "score": [1, 2]}).to_csv(data, index=False)
    with data.open("rb") as f:
        client.post(f"/runs/{run_id}/upload", headers=auth,
                    data={"protocol": "x"}, files={"data_file": ("d.csv", f, "text/csv")})
    client.post(f"/runs/{run_id}/estimate", headers=auth, json={"word_count": 500})
    ref = client.post(f"/runs/{run_id}/pay-link", headers=auth).json()["reference"]
    client.post("/payments/callback", json={"reference": ref, "status": "success"})

    r = client.post(f"/runs/{run_id}/plan", headers=auth)
    assert r.status_code == 503  # graceful, not a raw 500
    # run is still 'paid' so the user can retry
    assert client.get(f"/runs/{run_id}", headers=auth).json()["status"] == "paid"


def test_delete_account_purges(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "data_dir", str(tmp_path), raising=False)
    auth = _auth("del@ex.com")
    client.post("/runs", headers=auth, json={"scope": "studies"})
    assert client.get("/auth/me", headers=auth).status_code == 200

    d = client.delete("/auth/me", headers=auth)
    assert d.status_code == 204
    # token no longer works (user gone)
    assert client.get("/auth/me", headers=auth).status_code == 401


def test_admin_disabled_without_token(monkeypatch):
    monkeypatch.setattr(settings, "admin_token", "", raising=False)
    assert client.get("/admin/stats").status_code == 404


def test_admin_with_token(monkeypatch):
    monkeypatch.setattr(settings, "admin_token", "secret", raising=False)
    assert client.get("/admin/stats").status_code == 401  # missing header
    ok = client.get("/admin/stats", headers={"X-Admin-Token": "secret"})
    assert ok.status_code == 200 and "users" in ok.json()
