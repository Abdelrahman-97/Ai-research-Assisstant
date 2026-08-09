"""End-to-end pipeline test.

Drives the whole run through the real HTTP API. The three Kimi calls (propose
plan, write script, write Results) are stubbed; the *sandbox actually executes* a
real scipy t-test script via the dev subprocess fallback, and the .docx is built
for real. This exercises every stage and the human checkpoint.
"""

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.models.schemas import ProposedTest
from app.services import planner, results_writer, stats_executor

client = TestClient(app)

# A real, runnable analysis script returned in place of the AI's output.
REAL_SCRIPT = '''\
import os
import pandas as pd
from scipy import stats

df = pd.read_csv("data.csv")
a = df[df["group"] == "a"]["score"]
b = df[df["group"] == "b"]["score"]
t, p = stats.ttest_ind(a, b)
print(f"Independent t-test: t={t:.4f}, p={p:.4f}, n_a={len(a)}, n_b={len(b)}")

os.makedirs("artifacts", exist_ok=True)
pd.DataFrame({"t_stat": [t], "p_value": [p]}).to_csv("artifacts/summary.csv", index=False)
'''

FAKE_PLAN = ProposedTest(
    name="Independent samples t-test",
    reasoning="Two independent groups with a continuous outcome.",
    variables=["group", "score"],
    assumptions=["normality", "equal variances"],
    citations=["Student (1908)"],
)


@pytest.fixture(autouse=True)
def _stub_ai_and_sandbox(monkeypatch, tmp_path):
    # Point all runtime output at a temp dir and allow local execution.
    monkeypatch.setattr(settings, "data_dir", str(tmp_path), raising=False)
    monkeypatch.setattr(settings, "sandbox_allow_subprocess_fallback", True, raising=False)
    # Stub the three Kimi-backed steps.
    monkeypatch.setattr(planner, "propose_plan", lambda **kw: FAKE_PLAN)
    monkeypatch.setattr(stats_executor, "generate_script", lambda **kw: REAL_SCRIPT)
    monkeypatch.setattr(
        results_writer,
        "write_results",
        lambda **kw: "## Results\n\nAn independent samples t-test was conducted.",
    )


def _paid_client(email="e2e@example.com"):
    r = client.post(
        "/auth/signup",
        json={"email": email, "password": "supersecret", "scope": "studies"},
    )
    token = r.json()["access_token"]
    auth = {"Authorization": f"Bearer {token}"}
    ref = client.post("/payments/link", headers=auth).json()["reference"]
    client.post("/payments/callback", json={"reference": ref, "status": "success"})
    return auth


def test_full_pipeline(tmp_path):
    auth = _paid_client()

    # data file
    data = tmp_path / "study.csv"
    pd.DataFrame(
        {"group": ["a", "a", "a", "b", "b", "b"], "score": [10, 12, 11, 20, 22, 19]}
    ).to_csv(data, index=False)

    # 1. create run
    run_id = client.post("/runs", headers=auth).json()["id"]

    # 2. upload protocol + data
    with data.open("rb") as f:
        up = client.post(
            f"/runs/{run_id}/upload",
            headers=auth,
            data={"protocol": "Compare score between groups a and b."},
            files={"data_file": ("study.csv", f, "text/csv")},
        )
    assert up.status_code == 200 and up.json()["status"] == "uploaded"

    # 3. propose plan -> human checkpoint
    plan = client.post(f"/runs/{run_id}/plan", headers=auth)
    assert plan.json()["status"] == "awaiting_approval"
    assert plan.json()["proposed_test"]["name"] == "Independent samples t-test"

    # 4. HUMAN CHECKPOINT — approve
    appr = client.post(f"/runs/{run_id}/approve", headers=auth, json={"confirmed": True})
    assert appr.json()["status"] == "approved"

    # 5. generate script (preview) -> 6. execute in sandbox
    scr = client.post(f"/runs/{run_id}/script?language=python", headers=auth)
    assert scr.json()["status"] == "script_ready"
    assert "ttest_ind" in scr.json()["script"]

    ex = client.post(f"/runs/{run_id}/execute", headers=auth)
    body = ex.json()
    assert body["status"] == "executed", body.get("error")
    assert "Independent t-test" in body["execution"]["stdout"]
    assert any(a["kind"] == "table" for a in body["execution"]["artifacts"])

    # 7. verify + write results -> .docx
    res = client.post(f"/runs/{run_id}/results", headers=auth)
    assert res.json()["status"] == "completed"
    assert res.json()["docx_path"]

    # 8. download
    dl = client.get(f"/runs/{run_id}/download", headers=auth)
    assert dl.status_code == 200
    assert dl.content[:2] == b"PK"  # .docx is a zip


def test_cannot_skip_the_human_checkpoint(tmp_path):
    """Generating a script before approving the plan must fail."""
    auth = _paid_client("checkpoint@example.com")
    data = tmp_path / "d.csv"
    pd.DataFrame({"group": ["a", "b"], "score": [1, 2]}).to_csv(data, index=False)
    run_id = client.post("/runs", headers=auth).json()["id"]
    with data.open("rb") as f:
        client.post(
            f"/runs/{run_id}/upload",
            headers=auth,
            data={"protocol": "x"},
            files={"data_file": ("d.csv", f, "text/csv")},
        )
    client.post(f"/runs/{run_id}/plan", headers=auth)  # awaiting_approval
    # Skip approve, try to generate a script:
    scr = client.post(f"/runs/{run_id}/script?language=python", headers=auth)
    assert scr.status_code == 409  # blocked
