"""Tests for the audited statistical-test engines (Results-section library)."""

import numpy as np
import pandas as pd
import pytest

from app.services import sample_size
from app.services.stat_engines import EngineError, catalogue, registry, run_engine


@pytest.fixture
def df():
    rng = np.random.default_rng(42)
    return pd.DataFrame({
        "group": ["A"] * 20 + ["B"] * 20,
        "arm3": (["A", "B", "C"] * 14)[:40],
        "score": np.r_[rng.normal(10, 2, 20), rng.normal(13, 2, 20)],
        "pre": rng.normal(5, 1, 40),
        "post": rng.normal(6, 1, 40),
        "x": rng.normal(0, 1, 40),
        "sex": (["M", "F"] * 20),
    })


def _is_png(path):
    with open(path, "rb") as f:
        return f.read(8) == b"\x89PNG\r\n\x1a\n"


def test_catalogue_lists_engines():
    keys = {e["key"] for e in catalogue()}
    assert {"independent_ttest", "one_way_anova", "correlation",
            "linear_regression", "chi_square"} <= keys


def test_independent_ttest(df, tmp_path):
    r = run_engine("independent_ttest", df, {"outcome": "score", "group": "group"}, fig_dir=tmp_path)
    v = r["values"]
    assert v["p_value"] < 0.05                      # groups differ by design
    assert v["cohens_d"] is not None
    assert "method" in v and r["references"]
    assert _is_png(r["figure_path"])
    # wrong number of groups is a clear error
    with pytest.raises(EngineError):
        run_engine("independent_ttest", df, {"outcome": "score", "group": "arm3"})


def test_ttest_matches_scipy(df):
    from scipy import stats
    a = df[df.group == "A"]["score"]
    b = df[df.group == "B"]["score"]
    t, p = stats.ttest_ind(a, b, equal_var=True)
    r = run_engine("independent_ttest", df, {"outcome": "score", "group": "group"})
    # our Levene may pick Welch; force-compare only when equal-var path chosen
    if r["values"]["equal_variances"]:
        assert abs(r["values"]["t"] - t) < 1e-3


def test_paired_and_wilcoxon(df, tmp_path):
    r = run_engine("paired_ttest", df, {"pre": "pre", "post": "post"}, fig_dir=tmp_path)
    assert r["values"]["n_pairs"] == 40 and r["values"]["cohens_dz"] is not None
    w = run_engine("wilcoxon", df, {"pre": "pre", "post": "post"})
    assert "p_value" in w["values"]


def test_anova_and_kruskal(df):
    a = run_engine("one_way_anova", df, {"outcome": "score", "group": "arm3"})
    assert a["values"]["df_between"] == 2 and a["values"]["eta_squared"] is not None
    k = run_engine("kruskal_wallis", df, {"outcome": "score", "group": "arm3"})
    assert k["values"]["df"] == 2


def test_correlation_pearson_and_spearman(df):
    p = run_engine("correlation", df, {"var1": "x", "var2": "score", "method": "pearson"})
    assert p["values"]["ci95"] is not None and p["values"]["r_squared"] is not None
    s = run_engine("correlation", df, {"var1": "x", "var2": "score", "method": "spearman"})
    assert s["values"]["method"] == "spearman"


def test_chi_square(df):
    r = run_engine("chi_square", df, {"var1": "group", "var2": "sex"})
    assert r["values"]["df"] == 1 and r["values"]["cramers_v"] is not None


def test_linear_regression(df):
    r = run_engine("linear_regression", df, {"outcome": "score", "predictors": ["x", "pre"]})
    v = r["values"]
    assert v["r_squared"] is not None
    assert len(v["coefficients"]) == 3           # intercept + 2 predictors
    assert v["coefficients"][0]["term"] == "Intercept"


def test_descriptives(df):
    r = run_engine("descriptive_summary", df, {"variables": ["score", "x"], "group": "group"})
    assert len(r["values"]["rows"]) == 4          # 2 vars x 2 groups
    assert all("mean" in row for row in r["values"]["rows"])


def test_unknown_engine_errors(df):
    with pytest.raises(EngineError):
        run_engine("nope", df, {})


def test_missing_column_errors(df):
    with pytest.raises(EngineError):
        run_engine("correlation", df, {"var1": "x", "var2": "missing"})


def test_power_curve(tmp_path):
    res = sample_size.two_means(effect_size=0.5)
    p = sample_size.power_curve(res, tmp_path / "pc.png")
    assert p and _is_png(p)
    # survival has no meaningful power curve
    surv = sample_size.survival(hazard_ratio=0.7, event_probability=0.6)
    assert sample_size.power_curve(surv, tmp_path / "none.png") is None
