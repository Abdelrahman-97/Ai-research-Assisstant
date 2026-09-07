"""Tests for meta-analysis data ingestion (spreadsheet upload -> studies)."""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import meta_analysis, meta_ingest

client = TestClient(app)


def _write(tmp_path, name, text):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


def test_parse_generic_with_optional_columns(tmp_path):
    p = _write(tmp_path, "s.csv",
               "name,effect,standard_error,group,moderator,year\n"
               "Smith 2019,0.20,0.10,adults,55,2019\n"
               "Jones 2020,0.40,0.15,kids,40,2020\n")
    r = meta_ingest.parse(p, "generic")
    assert r["n_valid"] == 2 and not r["invalid"]
    assert r["has_group"] and r["has_moderator"] and r["has_year"]
    s0 = r["studies"][0]
    assert s0["effect"] == 0.20 and s0["group"] == "adults" and s0["year"] == 2019
    # parsed studies feed the engine unchanged
    assert meta_analysis.analyze(r["studies"], measure="generic")["k"] == 2


def test_parse_or_with_header_aliases(tmp_path):
    p = _write(tmp_path, "s.csv",
               "Study,Events (T),N_t,eventsc,ncontrol\n"
               "A,20,100,30,100\nB,15,80,25,90\n")
    r = meta_ingest.parse(p, "or")
    assert r["n_valid"] == 2
    assert r["mapped_columns"]["e1"] == "Events (T)"
    assert r["studies"][0]["e1"] == 20.0


def test_invalid_rows_are_flagged_not_fatal(tmp_path):
    p = _write(tmp_path, "s.csv",
               "name,events1,n1,events2,n2\n"
               "Good1,20,100,30,100\nGood2,15,80,25,90\n"
               "Bad,50,10,5,20\n")   # events exceed N
    r = meta_ingest.parse(p, "or")
    assert r["n_valid"] == 2
    assert len(r["invalid"]) == 1
    assert "exceed" in r["invalid"][0]["reason"]
    assert r["warnings"]


def test_parse_change_from_baseline_with_global_corr(tmp_path):
    p = _write(tmp_path, "s.csv",
               "name,n1,pre1_mean,pre1_sd,post1_mean,post1_sd,n2,pre2_mean,pre2_sd,post2_mean,post2_sd\n"
               "A,30,52.1,8,44.3,7.5,30,51.8,8.2,49,7.9\n"
               "B,25,50,7,43,7,25,50,7,48,7\n")
    r = meta_ingest.parse(p, "md_change", corr=0.6)
    assert r["n_valid"] == 2
    assert r["studies"][0]["corr"] == 0.6      # global correlation injected
    assert meta_analysis.analyze(r["studies"], measure="md_change")["k"] == 2


def test_missing_required_column_raises(tmp_path):
    p = _write(tmp_path, "s.csv", "name,effect\nA,0.2\nB,0.3\n")
    with pytest.raises(meta_ingest.MetaIngestError) as exc:
        meta_ingest.parse(p, "generic")
    assert "standard_error" in str(exc.value)


def test_generic_accepts_variance_instead_of_se(tmp_path):
    p = _write(tmp_path, "s.csv", "name,effect,variance\nA,0.2,0.01\nB,0.3,0.02\n")
    r = meta_ingest.parse(p, "generic")
    assert r["n_valid"] == 2


def test_too_few_valid_studies_raises(tmp_path):
    p = _write(tmp_path, "s.csv",
               "name,events1,n1,events2,n2\nA,20,100,30,100\nBad,50,10,5,20\n")
    with pytest.raises(meta_ingest.MetaIngestError):
        meta_ingest.parse(p, "or")


def test_template_columns_match_schema():
    assert meta_ingest.template_columns("or") == ["name", "events1", "n1", "events2", "n2"]
    assert meta_ingest.template_columns("smd", group=True, year=True)[-2:] == ["group", "year"]


def test_endpoint_meta_parse_and_template():
    r = client.post("/auth/signup",
                    json={"email": "ingest@ep.com", "password": "supersecret", "scope": "studies"})
    assert r.status_code == 201
    auth = {"Authorization": f"Bearer {r.json()['access_token']}"}
    run = client.post("/runs", headers=auth, json={"task": "meta_analysis"}).json()

    csv = "name,effect,standard_error\nA,0.2,0.1\nB,0.3,0.15\n"
    res = client.post(
        f"/runs/{run['id']}/meta-parse",
        headers=auth,
        data={"measure": "generic"},
        files={"data_file": ("studies.csv", csv, "text/csv")},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["n_valid"] == 2 and len(body["studies"]) == 2

    tpl = client.get("/runs/meta-template", headers=auth, params={"measure": "or"})
    assert tpl.status_code == 200
    assert "events1" in tpl.text
