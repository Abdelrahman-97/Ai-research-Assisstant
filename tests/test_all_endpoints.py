"""Coverage test: every endpoint is exercised at least once.

Walks the full happy path AND checks key failure paths. Kimi calls are stubbed;
the sandbox runs a real script via the dev subprocess fallback. A completeness
assertion at the end fails if a route is added without being covered here.
"""

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.models.schemas import AssistantAction, ProposedTest
from app.services import assistant, planner, pricing, results_writer, stats_executor

client = TestClient(app)

REAL_SCRIPT = '''\
import os, pandas as pd
from scipy import stats
df = pd.read_csv("data.csv")
a = df[df["group"] == "a"]["score"]; b = df[df["group"] == "b"]["score"]
t, p = stats.ttest_ind(a, b)
print(f"t={t:.4f} p={p:.4f}")
os.makedirs("artifacts", exist_ok=True)
pd.DataFrame({"t":[t],"p":[p]}).to_csv("artifacts/summary.csv", index=False)
'''

FAKE_PLAN = ProposedTest(
    name="Independent samples t-test", reasoning="Two groups, continuous outcome.",
    variables=["group", "score"], assumptions=["normality"], citations=[],
)


@pytest.fixture(autouse=True)
def _stub(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "data_dir", str(tmp_path), raising=False)
    monkeypatch.setattr(settings, "sandbox_allow_subprocess_fallback", True, raising=False)
    monkeypatch.setattr(pricing, "estimate_test_count", lambda *a, **k: 2)
    monkeypatch.setattr(planner, "propose_plan", lambda **k: FAKE_PLAN)
    monkeypatch.setattr(stats_executor, "generate_script", lambda **k: REAL_SCRIPT)
    monkeypatch.setattr(results_writer, "write_results", lambda **k: "## Results\n\nDone.")
    monkeypatch.setattr(assistant, "interpret",
                        lambda run, message, **k: ("Sure.", AssistantAction(type="none")))


def test_every_endpoint(tmp_path):
    hit: set[str] = set()

    assert client.get("/").status_code == 200; hit.add("/")
    assert client.get("/health").status_code == 200; hit.add("/health")

    signup = client.post("/auth/signup", json={
        "email": "all@ep.com", "password": "supersecret", "scope": "thesis"})
    assert signup.status_code == 201; hit.add("/auth/signup")
    auth = {"Authorization": f"Bearer {signup.json()['access_token']}"}

    assert client.post("/auth/login", json={"email": "all@ep.com", "password": "supersecret"}).status_code == 200
    hit.add("/auth/login")
    assert client.get("/auth/me", headers=auth).status_code == 200; hit.add("/auth/me")
    assert client.get("/auth/me").status_code in (401, 403)

    # account-management endpoints (full flows are in test_email_auth.py)
    client.post("/auth/verify-email", json={"token": "x"}); hit.add("/auth/verify-email")
    client.post("/auth/resend-verification", json={"email": "all@ep.com"}); hit.add("/auth/resend-verification")
    client.post("/auth/forgot-password", json={"email": "all@ep.com"}); hit.add("/auth/forgot-password")
    client.post("/auth/reset-password", json={"token": "x", "new_password": "supersecret"}); hit.add("/auth/reset-password")

    run_id = client.post("/runs", headers=auth, json={"scope": "studies"}).json()["id"]; hit.add("/runs")
    assert client.get("/runs", headers=auth).status_code == 200  # list (same path "/runs")

    data = tmp_path / "d.csv"
    pd.DataFrame({"group": ["a", "a", "b", "b"], "score": [10, 11, 20, 21]}).to_csv(data, index=False)
    with data.open("rb") as f:
        up = client.post(f"/runs/{run_id}/upload", headers=auth,
                         data={"protocol": "compare a vs b"},
                         files={"data_file": ("d.csv", f, "text/csv")})
    assert up.status_code == 200; hit.add("/runs/{run_id}/upload")

    est = client.post(f"/runs/{run_id}/estimate", headers=auth, json={"word_count": 800})
    assert est.status_code == 200; hit.add("/runs/{run_id}/estimate")

    ref = client.post(f"/runs/{run_id}/pay-link", headers=auth).json()["reference"]
    hit.add("/runs/{run_id}/pay-link")
    assert client.post("/payments/callback", json={"reference": ref, "status": "success"}).status_code == 200
    hit.add("/payments/callback")

    # analyst assistant (paid run required) — stubbed interpret, no real LLM call
    asst = client.post(f"/runs/{run_id}/assistant", headers=auth, json={"message": "hi"})
    assert asst.status_code == 200; hit.add("/runs/{run_id}/assistant")

    assert client.post(f"/runs/{run_id}/plan", headers=auth).status_code == 200; hit.add("/runs/{run_id}/plan")
    assert client.post(f"/runs/{run_id}/approve", headers=auth, json={"confirmed": True}).status_code == 200
    hit.add("/runs/{run_id}/approve")
    assert client.post(f"/runs/{run_id}/script?language=python", headers=auth).status_code == 200
    hit.add("/runs/{run_id}/script")
    ex = client.post(f"/runs/{run_id}/execute", headers=auth)
    assert ex.status_code == 200 and ex.json()["status"] == "executed", ex.text
    hit.add("/runs/{run_id}/execute")
    assert client.post(f"/runs/{run_id}/results", headers=auth).status_code == 200; hit.add("/runs/{run_id}/results")
    assert client.post(f"/runs/{run_id}/accept", headers=auth).status_code == 200; hit.add("/runs/{run_id}/accept")

    assert client.get(f"/runs/{run_id}", headers=auth).status_code == 200; hit.add("/runs/{run_id}")
    w = client.get(f"/runs/{run_id}/download?format=word", headers=auth)
    assert w.status_code == 200 and w.content[:2] == b"PK"; hit.add("/runs/{run_id}/download")
    p = client.get(f"/runs/{run_id}/download?format=pdf", headers=auth)
    assert p.status_code == 200 and p.content[:4] == b"%PDF"

    assert client.get("/runs/does-not-exist", headers=auth).status_code == 404

    # account deletion + admin (full flows in test_hardening.py) — hit for coverage
    client.delete("/auth/me", headers=auth); hit.add("/auth/me")
    for p in ("/admin/stats", "/admin/runs"):
        client.get(p); hit.add(p)
    client.post("/admin/runs/x/refund"); hit.add("/admin/runs/{run_id}/refund")

    declared = {
        pth for pth in app.openapi()["paths"]
        if not any(x in pth for x in ("openapi", "docs", "redoc"))
    }
    missing = declared - hit
    assert not missing, f"Endpoints not covered by tests: {sorted(missing)}"
