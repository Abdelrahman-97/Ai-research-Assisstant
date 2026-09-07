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


def test_registry_has_all_engines():
    assert len(catalogue()) >= 22


def test_kruskal_dunn_posthoc():
    rng = np.random.default_rng(9)
    g = np.array(["A", "B", "C"] * 20)
    d = pd.DataFrame({"g": g, "y": np.select([g == "A", g == "B", g == "C"], [5, 7, 11])
                      + rng.normal(0, 1.5, 60)})
    r = run_engine("kruskal_wallis", d, {"outcome": "y", "group": "g"})
    ph = r["values"]["posthoc_dunn"]
    assert len(ph) == 3 and all("p_bonferroni" in c for c in ph)


def test_two_way_anova():
    rng = np.random.default_rng(4)
    a = np.array(["x", "y"] * 30)
    b = np.array((["p", "q", "r"] * 20))
    d = pd.DataFrame({"a": a, "b": b, "y": rng.normal(0, 1, 60) + (a == "y") * 2})
    r = run_engine("two_way_anova", d, {"outcome": "y", "factor1": "a", "factor2": "b"})
    eff = r["values"]["effects"]
    assert {"factor1", "factor2", "interaction"} <= set(eff)
    assert eff["factor1"]["partial_eta_sq"] is not None


def test_anova_posthoc_and_normality():
    rng = np.random.default_rng(11)
    g = np.array(["A", "B", "C"] * 20)
    d = pd.DataFrame({"g": g, "y": np.select([g == "A", g == "B", g == "C"], [10, 12, 15])
                      + rng.normal(0, 2, 60)})
    r = run_engine("one_way_anova", d, {"outcome": "y", "group": "g"})
    assert len(r["values"]["posthoc_tukey"]) == 3        # 3 pairwise comparisons
    assert len(r["values"]["normality"]) == 3            # Shapiro per group
    assert all("p_value" in c for c in r["values"]["posthoc_tukey"])


def test_friedman():
    rng = np.random.default_rng(5)
    long = pd.DataFrame({
        "subj": list(range(15)) * 3,
        "cond": ["t1"] * 15 + ["t2"] * 15 + ["t3"] * 15,
        "val": np.r_[rng.normal(5, 1, 15), rng.normal(6, 1, 15), rng.normal(8, 1, 15)],
    })
    r = run_engine("friedman", long, {"subject": "subj", "within": "cond", "outcome": "val"})
    assert r["values"]["df"] == 2 and r["values"]["kendalls_w"] is not None


def test_fishers_exact():
    d = pd.DataFrame({"exposure": ["y"] * 10 + ["n"] * 10,
                      "disease": ["y"] * 3 + ["n"] * 7 + ["y"] * 8 + ["n"] * 2})
    r = run_engine("fishers_exact", d, {"var1": "exposure", "var2": "disease"})
    assert r["values"]["odds_ratio"] is not None and r["values"]["n"] == 20
    with pytest.raises(EngineError):    # not 2x2
        big = pd.DataFrame({"a": ["x", "y", "z"] * 5, "b": ["p", "q"] * 7 + ["p"]})
        run_engine("fishers_exact", big, {"var1": "a", "var2": "b"})


def test_mcnemar():
    d = pd.DataFrame({"before": ["pos"] * 8 + ["neg"] * 12,
                      "after": ["pos"] * 5 + ["neg"] * 3 + ["pos"] * 7 + ["neg"] * 5})
    r = run_engine("mcnemar", d, {"var1": "before", "var2": "after"})
    assert r["values"]["p_value"] is not None


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
