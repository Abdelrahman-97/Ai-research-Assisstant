"""Meta-analysis is written up as a thesis/paper Results section.

Covers the narrative writer (grounded in deterministic facts), the compute path
with an AI narrative, and the deterministic fallback when no LLM is configured.
"""

from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.models.schemas import Scope
from app.services import orchestrator, results_writer

client = TestClient(app)

STUDIES = [
    {"name": "A", "effect": 0.20, "se": 0.10},
    {"name": "B", "effect": 0.40, "se": 0.15},
    {"name": "C", "effect": 0.10, "se": 0.12},
]


def _paid_meta_run(auth, inputs):
    run = client.post("/runs", headers=auth, json={"task": "meta_analysis"}).json()
    te = client.post(f"/runs/{run['id']}/tool-estimate", headers=auth, json={"inputs": inputs})
    assert te.status_code == 200, te.text
    ref = client.post(f"/runs/{run['id']}/pay-link", headers=auth).json()["reference"]
    client.post("/payments/callback", json={"reference": ref, "status": "success"})
    return run["id"]


def _auth(email):
    r = client.post("/auth/signup", json={"email": email, "password": "supersecret", "scope": "studies"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_write_meta_narrative_uses_scope_and_facts():
    captured = {}

    class FakeClient:
        def chat(self, messages):
            captured["prompt"] = messages[-1]["content"]
            return "## Results\n\nWe pooled three studies."

    out = results_writer.write_meta_narrative(
        facts="k = 3 studies; pooled 0.24 (95% CI ...)", scope=Scope.thesis,
        language="en", client=FakeClient(),
    )
    assert out.startswith("## Results")
    assert "thesis" in captured["prompt"]
    assert "pooled 0.24" in captured["prompt"]  # facts passed through verbatim


def test_compute_meta_with_narrative(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "data_dir", str(tmp_path), raising=False)
    monkeypatch.setattr(settings, "llm_api_key", "test-key", raising=False)
    monkeypatch.setattr(results_writer, "write_meta_narrative",
                        lambda **k: "## Results (Meta-analysis)\n\nAI narrative here.")
    auth = _auth("metawrite@ep.com")
    rid = _paid_meta_run(auth, {"studies": STUDIES, "measure": "generic",
                                "scope": "thesis", "output_language": "en", "preset": "apa"})
    tc = client.post(f"/runs/{rid}/tool-compute", headers=auth)
    assert tc.status_code == 200, tc.text
    md = tc.json()["results_markdown"]
    assert "AI narrative here." in md
    assert "Detailed statistical output" in md   # deterministic tables appended


def test_compute_meta_fallback_without_llm(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "data_dir", str(tmp_path), raising=False)
    monkeypatch.setattr(settings, "llm_api_key", "", raising=False)
    auth = _auth("metafallback@ep.com")
    rid = _paid_meta_run(auth, {"studies": STUDIES, "measure": "generic",
                                "scope": "studies", "output_language": "en"})
    tc = client.post(f"/runs/{rid}/tool-compute", headers=auth)
    assert tc.status_code == 200, tc.text
    md = tc.json()["results_markdown"]
    assert "## Summary" in md            # deterministic report used as-is
    assert md.startswith("# Meta-analysis")


def test_estimate_tool_captures_scope_language(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "data_dir", str(tmp_path), raising=False)
    auth = _auth("metascope@ep.com")
    run = client.post("/runs", headers=auth, json={"task": "meta_analysis"}).json()
    client.post(f"/runs/{run['id']}/tool-estimate", headers=auth,
                json={"inputs": {"studies": STUDIES, "measure": "generic",
                                 "scope": "thesis", "output_language": "ar", "preset": "vancouver"}})
    got = client.get(f"/runs/{run['id']}", headers=auth).json()
    assert got["scope"] == "thesis"
    assert got["output_language"] == "ar"
