"""Coverage test: every endpoint is exercised at least once.

Walks the full happy path AND checks the important failure paths (unauthenticated
access, payment gate). Kimi calls are stubbed; the sandbox runs a real script via
the dev subprocess fallback. A completeness assertion at the end fails if a new
route is added to the app without being covered here.
"""

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.models.schemas import ProposedTest
from app.services import planner, results_writer, stats_executor

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

# Every path that must be touched (with {run_id} normalised).
EXPECTED = {
    "/", "/health",
    "/auth/signup", "/auth/login", "/auth/me",
    "/payments/link", "/payments/callback",
    "/runs", "/runs/{run_id}", "/runs/{run_id}/upload", "/runs/{run_id}/plan",
    "/runs/{run_id}/approve", "/runs/{run_id}/script", "/runs/{run_id}/execute",
    "/runs/{run_id}/results", "/runs/{run_id}/download",
}


@pytest.fixture(autouse=True)
def _stub(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "data_dir", str(tmp_path), raising=False)
    monkeypatch.setattr(settings, "sandbox_allow_subprocess_fallback", True, raising=False)
    monkeypatch.setattr(planner, "propose_plan", lambda **k: FAKE_PLAN)
    monkeypatch.setattr(stats_executor, "generate_script", lambda **k: REAL_SCRIPT)
    monkeypatch.setattr(results_writer, "write_results", lambda **k: "## Results\n\nDone.")


def test_every_endpoint(tmp_path):
    hit: set[str] = set()

    # ---- public ----
    assert client.get("/").status_code == 200; hit.add("/")
    assert client.get("/health").status_code == 200; hit.add("/health")

    # ---- auth ----
    signup = client.post("/auth/signup", json={
        "email": "all@ep.com", "password": "supersecret", "scope": "thesis"})
    assert signup.status_code == 201; hit.add("/auth/signup")
    token = signup.json()["access_token"]
    auth = {"Authorization": f"Bearer {token}"}

    login = client.post("/auth/login", json={"email": "all@ep.com", "password": "supersecret"})
    assert login.status_code == 200; hit.add("/auth/login")
    assert client.post("/auth/login", json={"email": "all@ep.com", "password": "wrong"}).status_code == 401

    assert client.get("/auth/me", headers=auth).status_code == 200; hit.add("/auth/me")
    assert client.get("/auth/me").status_code in (401, 403)  # no token rejected

    # ---- payment gate before paying ----
    assert client.post("/runs", headers=auth).status_code == 402

    # ---- payments ----
    link = client.post("/payments/link", headers=auth)
    assert link.status_code == 200; hit.add("/payments/link")
    ref = link.json()["reference"]
    assert client.post("/payments/callback", json={"reference": ref, "status": "success"}).status_code == 200
    hit.add("/payments/callback")

    # ---- runs pipeline ----
    run_id = client.post("/runs", headers=auth).json()["id"]; hit.add("/runs")

    data = tmp_path / "d.csv"
    pd.DataFrame({"group": ["a", "a", "b", "b"], "score": [10, 11, 20, 21]}).to_csv(data, index=False)
    with data.open("rb") as f:
        up = client.post(f"/runs/{run_id}/upload", headers=auth,
                         data={"protocol": "compare a vs b"},
                         files={"data_file": ("d.csv", f, "text/csv")})
    assert up.status_code == 200; hit.add("/runs/{run_id}/upload")

    assert client.post(f"/runs/{run_id}/plan", headers=auth).status_code == 200; hit.add("/runs/{run_id}/plan")
    assert client.post(f"/runs/{run_id}/approve", headers=auth, json={"confirmed": True}).status_code == 200
    hit.add("/runs/{run_id}/approve")
    assert client.post(f"/runs/{run_id}/script?language=python", headers=auth).status_code == 200
    hit.add("/runs/{run_id}/script")
    ex = client.post(f"/runs/{run_id}/execute", headers=auth)
    assert ex.status_code == 200 and ex.json()["status"] == "executed", ex.text
    hit.add("/runs/{run_id}/execute")
    assert client.post(f"/runs/{run_id}/results", headers=auth).status_code == 200; hit.add("/runs/{run_id}/results")

    assert client.get(f"/runs/{run_id}", headers=auth).status_code == 200; hit.add("/runs/{run_id}")
    dl = client.get(f"/runs/{run_id}/download", headers=auth)
    assert dl.status_code == 200 and dl.content[:2] == b"PK"; hit.add("/runs/{run_id}/download")

    # ---- ownership / not-found guard ----
    assert client.get("/runs/does-not-exist", headers=auth).status_code == 404

    # ---- completeness: every declared route was hit ----
    declared = {
        p for p in app.openapi()["paths"]
        if not any(x in p for x in ("openapi", "docs", "redoc"))
    }
    missing = declared - hit
    assert not missing, f"Endpoints not covered by tests: {sorted(missing)}"
    assert EXPECTED <= hit
