"""End-to-end pipeline test (new flow: upload -> estimate -> pay -> analyse).

Drives the whole run through the real HTTP API. Kimi calls (propose plan, write
script, write Results, and the test-count estimate) are stubbed; the sandbox
actually executes a real scipy t-test via the dev subprocess fallback, and both
.docx and .pdf are built for real.
"""

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.models.schemas import ProposedTest
from app.services import planner, pricing, results_writer, stats_executor

client = TestClient(app)

REAL_SCRIPT = '''\
import os, pandas as pd
from scipy import stats
df = pd.read_csv("data.csv")
a = df[df["group"] == "a"]["score"]; b = df[df["group"] == "b"]["score"]
t, p = stats.ttest_ind(a, b)
print(f"Independent t-test: t={t:.4f}, p={p:.4f}")
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


def _auth(email):
    r = client.post("/auth/signup",
                    json={"email": email, "password": "supersecret", "scope": "studies"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_full_pipeline(tmp_path):
    auth = _auth("e2e@example.com")

    data = tmp_path / "study.csv"
    pd.DataFrame({"group": ["a", "a", "a", "b", "b", "b"],
                  "score": [10, 12, 11, 20, 22, 19]}).to_csv(data, index=False)

    run_id = client.post("/runs", headers=auth, json={"scope": "studies"}).json()["id"]

    with data.open("rb") as f:
        up = client.post(f"/runs/{run_id}/upload", headers=auth,
                         data={"protocol": "Compare score between a and b."},
                         files={"data_file": ("study.csv", f, "text/csv")})
    assert up.json()["status"] == "uploaded"

    # price estimate (free)
    est = client.post(f"/runs/{run_id}/estimate", headers=auth, json={"word_count": 800})
    assert est.json()["status"] == "awaiting_payment"
    quote = est.json()["quote"]
    assert quote["amount_egp"] > 0
    assert sum(quote["breakdown"].values()) == quote["amount_egp"]

    # pay
    ref = client.post(f"/runs/{run_id}/pay-link", headers=auth).json()["reference"]
    paid = client.post("/payments/callback", json={"reference": ref, "status": "success"})
    assert paid.json()["paid"] is True
    assert client.get(f"/runs/{run_id}", headers=auth).json()["status"] == "paid"

    # analysis
    assert client.post(f"/runs/{run_id}/plan", headers=auth).json()["status"] == "awaiting_approval"
    assert client.post(f"/runs/{run_id}/approve", headers=auth, json={"confirmed": True}).json()["status"] == "approved"
    assert client.post(f"/runs/{run_id}/script?language=python", headers=auth).json()["status"] == "script_ready"
    ex = client.post(f"/runs/{run_id}/execute", headers=auth)
    assert ex.json()["status"] == "executed", ex.json().get("error")
    res = client.post(f"/runs/{run_id}/results", headers=auth)
    assert res.json()["status"] == "completed"
    assert res.json()["docx_path"] and res.json()["pdf_path"]

    # accept -> starts retention clock
    acc = client.post(f"/runs/{run_id}/accept", headers=auth)
    assert acc.json()["status"] == "accepted"
    assert acc.json()["expires_at"]

    # download both formats
    word = client.get(f"/runs/{run_id}/download?format=word", headers=auth)
    assert word.status_code == 200 and word.content[:2] == b"PK"
    pdf = client.get(f"/runs/{run_id}/download?format=pdf", headers=auth)
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"


def test_cannot_analyse_before_paying(tmp_path):
    auth = _auth("nopay@example.com")
    data = tmp_path / "d.csv"
    pd.DataFrame({"group": ["a", "b"], "score": [1, 2]}).to_csv(data, index=False)
    run_id = client.post("/runs", headers=auth, json={"scope": "studies"}).json()["id"]
    with data.open("rb") as f:
        client.post(f"/runs/{run_id}/upload", headers=auth,
                    data={"protocol": "x"}, files={"data_file": ("d.csv", f, "text/csv")})
    client.post(f"/runs/{run_id}/estimate", headers=auth, json={"word_count": 500})
    # Try to get a plan without paying:
    assert client.post(f"/runs/{run_id}/plan", headers=auth).status_code == 409


def test_cannot_skip_human_checkpoint(tmp_path):
    auth = _auth("skip@example.com")
    data = tmp_path / "d.csv"
    pd.DataFrame({"group": ["a", "b"], "score": [1, 2]}).to_csv(data, index=False)
    run_id = client.post("/runs", headers=auth, json={"scope": "studies"}).json()["id"]
    with data.open("rb") as f:
        client.post(f"/runs/{run_id}/upload", headers=auth,
                    data={"protocol": "x"}, files={"data_file": ("d.csv", f, "text/csv")})
    client.post(f"/runs/{run_id}/estimate", headers=auth, json={"word_count": 500})
    ref = client.post(f"/runs/{run_id}/pay-link", headers=auth).json()["reference"]
    client.post("/payments/callback", json={"reference": ref, "status": "success"})
    client.post(f"/runs/{run_id}/plan", headers=auth)  # awaiting_approval
    # Skip approve, try to generate a script:
    assert client.post(f"/runs/{run_id}/script?language=python", headers=auth).status_code == 409
