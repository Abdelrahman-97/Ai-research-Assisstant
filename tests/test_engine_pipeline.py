"""Engine-first pipeline: the AI router picks audited engines, the pipeline runs
them deterministically (no sandbox script), and writes the Results section."""

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.models.schemas import EnginePlan, EnginePlanItem
from app.services import analysis_router, pricing, results_writer

client = TestClient(app)

ENGINE_PLAN = EnginePlan(items=[
    EnginePlanItem(engine="independent_ttest", label="Independent-samples t-test",
                   params={"outcome": "score", "group": "group"},
                   reasoning="Two groups, continuous outcome."),
], fallback_to_script=False)


@pytest.fixture(autouse=True)
def _stub(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "data_dir", str(tmp_path), raising=False)
    monkeypatch.setattr(settings, "llm_api_key", "test-key", raising=False)
    monkeypatch.setattr(pricing, "estimate_test_count", lambda *a, **k: 1)
    monkeypatch.setattr(analysis_router, "propose", lambda **k: ENGINE_PLAN)
    # narrative writer stubbed (no real LLM); the deterministic facts still apply
    monkeypatch.setattr(results_writer, "write_engine_results",
                        lambda **k: "## Results\n\nThe groups differed.")


def _auth(email):
    r = client.post("/auth/signup", json={"email": email, "password": "supersecret", "scope": "studies"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_engine_pipeline_end_to_end(tmp_path):
    auth = _auth("engine@ep.com")
    data = tmp_path / "study.csv"
    pd.DataFrame({"group": ["a"] * 6 + ["b"] * 6,
                  "score": [10, 12, 11, 9, 13, 10, 20, 22, 19, 21, 18, 23]}).to_csv(data, index=False)

    rid = client.post("/runs", headers=auth, json={"scope": "studies"}).json()["id"]
    with data.open("rb") as f:
        client.post(f"/runs/{rid}/upload", headers=auth,
                    data={"protocol": "Compare score between a and b."},
                    files={"data_file": ("study.csv", f, "text/csv")})
    client.post(f"/runs/{rid}/estimate", headers=auth, json={"word_count": 600})
    ref = client.post(f"/runs/{rid}/pay-link", headers=auth).json()["reference"]
    client.post("/payments/callback", json={"reference": ref, "status": "success"})

    plan = client.post(f"/runs/{rid}/plan", headers=auth).json()
    assert plan["status"] == "awaiting_approval"
    assert plan["analysis_mode"] == "engine"
    assert plan["engine_plan"]["items"][0]["engine"] == "independent_ttest"

    client.post(f"/runs/{rid}/approve", headers=auth, json={"confirmed": True})
    sr = client.post(f"/runs/{rid}/script?language=python", headers=auth).json()
    assert sr["status"] == "script_ready"
    assert "Audited analyses" in sr["script"]           # no code generated

    ex = client.post(f"/runs/{rid}/execute", headers=auth).json()
    assert ex["status"] == "executed", ex.get("error")

    res = client.post(f"/runs/{rid}/results", headers=auth).json()
    assert res["status"] == "completed"
    md = res["results_markdown"]
    assert "Detailed statistical output" in md          # deterministic facts appended
    assert "t(" in md                                    # real t-test statistic present
    assert "## References" in md

    word = client.get(f"/runs/{rid}/download?format=word", headers=auth)
    assert word.status_code == 200 and word.content[:2] == b"PK"
