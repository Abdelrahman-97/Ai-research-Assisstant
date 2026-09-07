"""Specialized engines (Batch 6): one-sample t-test, Poisson / negative-binomial /
ordinal regression, partial & point-biserial correlation."""

import numpy as np
import pandas as pd
import pytest

from app.services.stat_engines import EngineError, catalogue, run_engine


@pytest.fixture
def df():
    rng = np.random.default_rng(21)
    n = 90
    return pd.DataFrame({
        "x1": rng.normal(0, 1, n),
        "x2": rng.normal(0, 1, n),
        "score": rng.normal(50, 10, n),
        "count": rng.poisson(3, n),
        "count_od": rng.negative_binomial(2, 0.3, n),
        "grade": rng.integers(1, 4, n),          # 3-level ordinal
        "sex": rng.integers(0, 2, n).astype(str),
    })


def test_registry_30():
    assert len(catalogue()) >= 30


def test_manova():
    rng = np.random.default_rng(8)
    g = np.array(["A", "B", "C"] * 30)
    d = pd.DataFrame({"g": g, "y1": rng.normal(0, 1, 90) + (g == "B"),
                      "y2": rng.normal(0, 1, 90) + (g == "C")})
    r = run_engine("manova", d, {"outcomes": ["y1", "y2"], "group": "g"})
    assert r["values"]["wilks_lambda"]["p_value"] is not None
    with pytest.raises(EngineError):     # needs 2+ outcomes
        run_engine("manova", d, {"outcomes": ["y1"], "group": "g"})


def test_mixed_effects():
    rng = np.random.default_rng(9)
    subj = np.repeat(np.arange(30), 3)
    time = np.tile([0, 1, 2], 30)
    val = time * 0.5 + np.repeat(rng.normal(0, 1, 30), 3) + rng.normal(0, 0.5, 90)
    d = pd.DataFrame({"subj": subj, "time": time, "val": val})
    r = run_engine("mixed_effects", d, {"outcome": "val", "predictors": ["time"], "group": "subj"})
    v = r["values"]
    assert v["n_groups"] == 30 and v["group_variance"] is not None
    assert any(c["term"] == "time" for c in v["fixed_effects"])


def test_one_sample_ttest(df):
    r = run_engine("one_sample_ttest", df, {"outcome": "score", "popmean": 45})
    v = r["values"]
    assert v["df"] == len(df) - 1 and v["cohens_d"] is not None
    with pytest.raises(EngineError):
        run_engine("one_sample_ttest", df, {"outcome": "score"})   # no reference


def test_poisson_regression(df):
    r = run_engine("poisson_regression", df, {"outcome": "count", "predictors": ["x1", "x2"]})
    v = r["values"]
    assert any(c["term"] == "x1" for c in v["coefficients"])
    assert all("ratio" in c for c in v["coefficients"])
    assert "dispersion" in v


def test_negative_binomial(df):
    r = run_engine("negative_binomial_regression", df, {"outcome": "count_od", "predictors": ["x1"]})
    assert r["values"]["coefficients"][0]["ratio"] is not None


def test_ordinal_logistic(df):
    r = run_engine("ordinal_logistic_regression", df, {"outcome": "grade", "predictors": ["x1", "x2"]})
    v = r["values"]
    assert v["n_levels"] == 3 and len(v["coefficients"]) == 2
    with pytest.raises(EngineError):     # binary outcome -> not ordinal
        run_engine("ordinal_logistic_regression", df, {"outcome": "sex", "predictors": ["x1"]})


def test_partial_correlation(df):
    r = run_engine("partial_correlation", df, {"var1": "x1", "var2": "score", "covariates": ["x2"]})
    assert r["values"]["df"] == len(df) - 3 and r["values"]["r"] is not None


def test_point_biserial(df):
    r = run_engine("point_biserial", df, {"binary": "sex", "continuous": "score"})
    assert -1 <= r["values"]["r"] <= 1
    with pytest.raises(EngineError):     # non-binary
        run_engine("point_biserial", df, {"binary": "grade", "continuous": "score"})
