"""Tests for the advanced engines (Batch 3): logistic, ANCOVA, RM-ANOVA,
survival/log-rank, Cox, Cohen's kappa, ICC, Bland-Altman."""

import numpy as np
import pandas as pd
import pytest

from app.services.stat_engines import EngineError, catalogue, run_engine


@pytest.fixture
def df():
    rng = np.random.default_rng(7)
    n = 60
    g = np.array(["ctrl", "trt"] * (n // 2))
    age = rng.normal(50, 10, n)
    d = pd.DataFrame({
        "group": g,
        "y": np.where(g == "trt", 12, 10) + rng.normal(0, 2, n),
        "binout": rng.binomial(1, np.where(g == "trt", 0.6, 0.3)),
        "age": age,
        "time": rng.exponential(6, n).round(2),
        "event": rng.binomial(1, 0.7, n),
        "mA": rng.normal(100, 10, n),
        "rr1": rng.normal(5, 1, n),
    })
    d["mB"] = d["mA"] + rng.normal(0, 3, n)
    d["rr2"] = d["rr1"] + rng.normal(0, 0.4, n)
    d["r1"] = rng.integers(0, 3, n).astype(str)
    d["r2"] = d["r1"].where(rng.random(n) < 0.7, rng.integers(0, 3, n).astype(str))
    return d


def _png(p):
    with open(p, "rb") as f:
        return f.read(8) == b"\x89PNG\r\n\x1a\n"


def test_registry_has_18_engines():
    assert len(catalogue()) >= 18


def test_logistic_regression(df):
    r = run_engine("logistic_regression", df, {"outcome": "binout", "predictors": ["age", "group"]})
    v = r["values"]
    assert v["pseudo_r2"] is not None
    assert any(c["term"] == "age" for c in v["coefficients"])
    assert all("odds_ratio" in c for c in v["coefficients"])
    with pytest.raises(EngineError):     # non-binary outcome
        run_engine("logistic_regression", df, {"outcome": "age", "predictors": ["y"]})


def test_ancova(df):
    r = run_engine("ancova", df, {"outcome": "y", "group": "group", "covariates": ["age"]})
    v = r["values"]
    assert "group_effect" in v and v["group_effect"]["partial_eta_sq"] is not None
    assert "age" in v["covariate_effects"]


def test_cox_regression(df):
    r = run_engine("cox_regression", df, {"time": "time", "event": "event", "predictors": ["age"]})
    v = r["values"]
    assert v["events"] > 0 and v["coefficients"][0]["hr"] is not None


def test_survival_logrank(df, tmp_path):
    r = run_engine("survival_logrank", df, {"time": "time", "event": "event", "group": "group"},
                   fig_dir=tmp_path)
    assert r["values"]["logrank"]["p_value"] is not None
    assert set(r["values"]["groups"]) == {"ctrl", "trt"}
    assert _png(r["figure_path"])


def test_cohens_kappa(df):
    r = run_engine("cohens_kappa", df, {"rater1": "r1", "rater2": "r2"})
    v = r["values"]
    assert -1 <= v["kappa"] <= 1 and v["interpretation"]


def test_icc(df):
    r = run_engine("icc", df, {"raters": ["rr1", "rr2"]})
    assert r["values"]["icc"] is not None and r["values"]["n_raters"] == 2
    with pytest.raises(EngineError):
        run_engine("icc", df, {"raters": ["rr1"]})


def test_bland_altman(df, tmp_path):
    r = run_engine("bland_altman", df, {"method1": "mA", "method2": "mB"}, fig_dir=tmp_path)
    v = r["values"]
    assert v["loa_lower"] < v["bias"] < v["loa_upper"]
    assert _png(r["figure_path"])


def test_repeated_measures_anova():
    rng = np.random.default_rng(3)
    long = pd.DataFrame({
        "subj": list(range(20)) * 3,
        "cond": ["t1"] * 20 + ["t2"] * 20 + ["t3"] * 20,
        "val": np.r_[rng.normal(5, 1, 20), rng.normal(6, 1, 20), rng.normal(7.5, 1, 20)],
    })
    r = run_engine("repeated_measures_anova", long,
                   {"subject": "subj", "within": "cond", "outcome": "val"})
    v = r["values"]
    assert v["p_value"] < 0.05 and len(v["levels"]) == 3
