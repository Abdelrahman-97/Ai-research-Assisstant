"""Tests for the free statistics tools: sample size, diagnostic accuracy, meta."""

import pytest

from app.services import diagnostic, meta_analysis, sample_size


def test_sample_size_two_means():
    # Classic result: d=0.5, alpha=.05, power=.80 -> ~64 per group.
    r = sample_size.two_means(0.5)
    assert r["n_group1"] == 64 and r["total"] == 128


def test_sample_size_designs_positive():
    assert sample_size.two_proportions(0.5, 0.3)["total"] > 0
    assert sample_size.anova(0.25, 3)["total"] > 0
    assert sample_size.correlation(0.3)["total"] > 0


def test_sample_size_validation():
    with pytest.raises(sample_size.SampleSizeError):
        sample_size.two_means(0.0)
    with pytest.raises(sample_size.SampleSizeError):
        sample_size.two_proportions(0.4, 0.4)


def test_diagnostic_metrics():
    r = diagnostic.accuracy_2x2(tp=90, fp=10, fn=20, tn=80)
    assert round(r["sensitivity"]["value"], 3) == 0.818
    assert round(r["specificity"]["value"], 3) == 0.889
    assert r["lr_positive"] > 1 and r["lr_negative"] < 1
    assert r["sensitivity"]["ci_low"] is not None
    with pytest.raises(diagnostic.DiagnosticError):
        diagnostic.accuracy_2x2(0, 0, 0, 0)


def test_meta_analysis():
    studies = [
        {"name": "A", "effect": 0.20, "se": 0.10, "group": "x"},
        {"name": "B", "effect": 0.40, "se": 0.15, "group": "x"},
        {"name": "C", "effect": 0.10, "se": 0.12, "group": "y"},
        {"name": "D", "effect": 0.50, "se": 0.20, "group": "y"},
    ]
    r = meta_analysis.analyze(studies, model="random")
    assert r["k"] == 4
    assert "estimate" in r["random"] and "estimate" in r["fixed"]
    assert 0 <= r["heterogeneity"]["I2_percent"] <= 100
    assert len(r["leave_one_out"]) == 4
    assert "x" in r["subgroups"] and "y" in r["subgroups"]
    # study weights sum to ~100%
    assert abs(sum(s["weight_pct"] for s in r["studies"]) - 100) < 1.0


def test_meta_requires_two():
    with pytest.raises(meta_analysis.MetaAnalysisError):
        meta_analysis.analyze([{"effect": 0.2, "se": 0.1}])
