"""Background worker + blob store tests.

Covers the production execution topology: the API enqueues a run (worker mode),
the dataset travels through the shared blob store, and the worker runs the script
and writes the Results doc end-to-end. Kimi calls are stubbed; the sandbox runs a
real scipy t-test via the subprocess fallback.
"""

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app import worker
from app.config import settings
from app.main import app
from app.models.schemas import ProposedTest, RunStatus
from app.services import planner, pricing, results_writer, stats_executor
from app.store import blobs

client = TestClient(app)

REAL_SCRIPT = '''\
import os, pandas as pd
from scipy import stats
df = pd.read_csv("data.csv")
a = df[df["group"] == "a"]["score"]; b = df[df["group"] == "b"]["score"]
t, p = stats.ttest_ind(a, b)
print(f"t={t:.4f}, p={p:.4f}")
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
    monkeypatch.setattr(settings, "execution_mode", "worker", raising=False)
    monkeypatch.setattr(pricing, "estimate_test_count", lambda *a, **k: 2)
    monkeypatch.setattr(planner, "propose_plan", lambda **k: FAKE_PLAN)
    monkeypatch.setattr(stats_executor, "generate_script", lambda **k: REAL_SCRIPT)
    monkeypatch.setattr(results_writer, "write_results", lambda **k: "## Results\n\nDone.")


def _auth(email):
    r = client.post("/auth/signup",
                    json={"email": email, "password": "supersecret", "scope": "studies"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _paid_run_ready_to_execute(auth, tmp_path):
    data = tmp_path / "study.csv"
    pd.DataFrame({"group": ["a", "a", "a", "b", "b", "b"],
                  "score": [10, 12, 11, 20, 22, 19]}).to_csv(data, index=False)
    run_id = client.post("/runs", headers=auth, json={"scope": "studies"}).json()["id"]
    with data.open("rb") as f:
        client.post(f"/runs/{run_id}/upload", headers=auth,
                    data={"protocol": "Compare score between a and b."},
                    files={"data_file": ("study.csv", f, "text/csv")})
    client.post(f"/runs/{run_id}/estimate", headers=auth, json={"word_count": 800})
    ref = client.post(f"/runs/{run_id}/pay-link", headers=auth).json()["reference"]
    client.post("/payments/callback", json={"reference": ref, "status": "success"})
    client.post(f"/runs/{run_id}/plan", headers=auth)
    client.post(f"/runs/{run_id}/approve", headers=auth, json={"confirmed": True})
    client.post(f"/runs/{run_id}/script?language=python", headers=auth)
    return run_id


def test_execute_enqueues_in_worker_mode(tmp_path):
    auth = _auth("worker-queue@example.com")
    run_id = _paid_run_ready_to_execute(auth, tmp_path)

    # In worker mode /execute must NOT run the script — it only queues it.
    ex = client.post(f"/runs/{run_id}/execute", headers=auth)
    assert ex.json()["status"] == "queued"


def test_upload_is_persisted_as_blob(tmp_path):
    auth = _auth("worker-blob@example.com")
    run_id = _paid_run_ready_to_execute(auth, tmp_path)
    run = client.get(f"/runs/{run_id}", headers=auth).json()
    assert run["data_blob_id"]
    got = blobs.get(run["data_blob_id"])
    assert got is not None
    filename, content = got
    assert b"group" in content and b"score" in content  # the uploaded CSV bytes


def _drain_until_terminal(auth, run_id, max_passes=8):
    """Run worker passes until this run reaches a terminal state.

    The worker claims the oldest queued run across the whole queue, so with the
    shared test DB a pass may process a sibling test's run first — drain until
    ours is done.
    """
    terminal = {"completed", "accepted", "failed"}
    for _ in range(max_passes):
        status = client.get(f"/runs/{run_id}", headers=auth).json()["status"]
        if status in terminal:
            return status
        if worker.run_once() == 0:
            break
    return client.get(f"/runs/{run_id}", headers=auth).json()["status"]


def test_worker_runs_queued_job_end_to_end(tmp_path):
    auth = _auth("worker-e2e@example.com")
    run_id = _paid_run_ready_to_execute(auth, tmp_path)
    client.post(f"/runs/{run_id}/execute", headers=auth)  # -> queued

    assert _drain_until_terminal(auth, run_id) == "completed"

    run = client.get(f"/runs/{run_id}", headers=auth).json()
    assert run["status"] == "completed", run.get("error")
    assert run["docx_blob_id"] and run["pdf_blob_id"]

    # Downloads are served from the blob store (worker built them on "another" service).
    word = client.get(f"/runs/{run_id}/download?format=word", headers=auth)
    assert word.status_code == 200 and word.content[:2] == b"PK"
    pdf = client.get(f"/runs/{run_id}/download?format=pdf", headers=auth)
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"


def test_worker_marks_failed_when_dataset_missing(tmp_path):
    auth = _auth("worker-nodata@example.com")
    run_id = _paid_run_ready_to_execute(auth, tmp_path)
    client.post(f"/runs/{run_id}/execute", headers=auth)

    # Simulate the dataset having been purged before the worker got to it.
    from app.store import repository
    run = repository.runs.get(run_id)
    blobs.delete_for_run(run_id)
    run.data_blob_id = "missing"
    repository.runs.save(run)

    assert _drain_until_terminal(auth, run_id) == "failed"
    assert repository.runs.get(run_id).status == RunStatus.failed


def test_subprocess_env_is_stripped_of_secrets(monkeypatch):
    # The hardened subprocess env must not carry DATABASE_URL / LLM key etc.
    from app.sandbox import docker_runner
    monkeypatch.setenv("DATABASE_URL", "postgres://secret")
    monkeypatch.setenv("LLM_API_KEY", "super-secret-key")
    env = docker_runner._safe_subprocess_env()
    assert "DATABASE_URL" not in env
    assert "LLM_API_KEY" not in env
    assert env.get("MPLBACKEND") == "Agg"
