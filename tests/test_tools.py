"""Tests for the free statistics tools: sample size, diagnostic accuracy, meta."""

import pytest

from app.services import citations, diagnostic, meta_analysis, sample_size


# --------------------------------------------------------------------------- #
# Sample size
# --------------------------------------------------------------------------- #
def test_sample_size_two_means():
    r = sample_size.two_means(effect_size=0.5)
    assert r["n_group1"] == 64 and r["total"] == 128
    assert r["references"]  # cites Cohen


def test_sample_size_solve_power():
    r = sample_size.two_means(effect_size=0.5, nobs1=64, solve="power")
    assert 0.78 <= r["power"] <= 0.82


def test_sample_size_more_designs():
    assert sample_size.paired_means(effect_size=0.5)["total"] > 0
    assert sample_size.one_mean(effect_size=0.5)["total"] > 0
    assert sample_size.two_proportions(p1=0.5, p2=0.3)["total"] > 0
    assert sample_size.one_proportion(p1=0.6, p0=0.5)["total"] > 0
    assert sample_size.anova(effect_size=0.25, k_groups=3)["total"] > 0
    assert sample_size.correlation(r=0.3)["total"] > 0
    assert sample_size.chi_square(effect_size=0.3, df=2)["total"] > 0


def test_sample_size_dropout_inflates():
    base = sample_size.two_means(effect_size=0.5)["total"]
    infl = sample_size.two_means(effect_size=0.5, dropout=0.2)["total"]
    assert infl > base


def test_sample_size_validation():
    with pytest.raises(sample_size.SampleSizeError):
        sample_size.two_means(effect_size=0.0)


# --------------------------------------------------------------------------- #
# Diagnostic
# --------------------------------------------------------------------------- #
def test_diagnostic_metrics():
    r = diagnostic.accuracy_2x2(tp=90, fp=10, fn=20, tn=80)
    assert round(r["sensitivity"]["value"], 3) == 0.818
    assert round(r["specificity"]["value"], 3) == 0.889
    assert r["lr_positive"] > 1 and r["lr_negative"] < 1
    with pytest.raises(diagnostic.DiagnosticError):
        diagnostic.accuracy_2x2(0, 0, 0, 0)


# --------------------------------------------------------------------------- #
# Meta-analysis
# --------------------------------------------------------------------------- #
def _generic():
    return [
        {"name": "A", "effect": 0.20, "se": 0.10, "group": "x", "moderator": 2010, "year": 2010},
        {"name": "B", "effect": 0.40, "se": 0.15, "group": "x", "moderator": 2015, "year": 2015},
        {"name": "C", "effect": 0.10, "se": 0.12, "group": "y", "moderator": 2018, "year": 2018},
        {"name": "D", "effect": 0.50, "se": 0.20, "group": "y", "moderator": 2020, "year": 2020},
    ]


def test_meta_core():
    r = meta_analysis.analyze(_generic(), model="random")
    assert r["k"] == 4
    assert "estimate" in r["random"] and "estimate" in r["fixed"]
    assert 0 <= r["heterogeneity"]["I2_percent"] <= 100
    assert r["prediction_interval"] is not None
    assert len(r["leave_one_out"]) == 4
    assert "groups" in r["subgroups"] and r["subgroups"]["test_for_differences"] is not None
    assert "meta_regression" in r and "cumulative" in r
    assert r["publication_bias"]["egger"] is not None
    assert abs(sum(s["weight_pct"] for s in r["studies"]) - 100) < 1.0
    assert r["references"]


@pytest.mark.parametrize("method", ["DL", "PM", "REML"])
def test_meta_tau2_methods(method):
    r = meta_analysis.analyze(_generic(), tau2_method=method)
    assert r["heterogeneity"]["tau2_method"] == method
    assert r["heterogeneity"]["tau2"] >= 0


def test_meta_hksj_uses_t():
    r = meta_analysis.analyze(_generic(), hksj=True)
    assert r["random"]["method"] == "Hartung-Knapp"


def test_meta_binary_or():
    studies = [
        {"name": "A", "e1": 20, "n1": 100, "e2": 30, "n2": 100, "group": "g1"},
        {"name": "B", "e1": 15, "n1": 80, "e2": 25, "n2": 90, "group": "g1"},
        {"name": "C", "e1": 5, "n1": 50, "e2": 10, "n2": 55, "group": "g2"},
    ]
    r = meta_analysis.analyze(studies, measure="or")
    assert r["effect_measure"] == "or" and r["log_scale"] is True
    assert "transformed" in r["random"]      # back-transformed OR
    assert r["random"]["transformed"]["estimate"] > 0


def test_meta_smd_from_raw():
    studies = [
        {"name": "A", "n1": 30, "m1": 5.0, "sd1": 1.2, "n2": 30, "m2": 4.0, "sd2": 1.3},
        {"name": "B", "n1": 40, "m1": 5.5, "sd1": 1.1, "n2": 42, "m2": 4.2, "sd2": 1.4},
    ]
    r = meta_analysis.analyze(studies, measure="smd")
    assert r["scale_label"].startswith("SMD")
    assert r["random"]["estimate"] > 0


def test_meta_fisher_z():
    studies = [{"name": "A", "r": 0.3, "n": 50}, {"name": "B", "r": 0.4, "n": 60}]
    r = meta_analysis.analyze(studies, measure="fisher_z")
    assert "transformed" in r["random"]  # back to r


def test_diagnostic_roc(tmp_path):
    pairs = [[0.9, 1], [0.8, 1], [0.7, 0], [0.6, 1], [0.55, 0],
             [0.5, 1], [0.4, 0], [0.3, 0], [0.2, 1], [0.1, 0]]
    r = diagnostic.roc_auc(pairs)
    assert 0 <= r["auc"] <= 1
    assert r["auc_ci_low"] <= r["auc"] <= r["auc_ci_high"]
    assert r["youden_cutoff"] is not None
    assert len(r["roc_points"]) >= 3
    assert "sensitivity" in r["at_optimal_cutoff"]
    fp = tmp_path / "roc.png"
    diagnostic.roc_plot(r, str(fp))
    assert fp.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    with pytest.raises(diagnostic.DiagnosticError):
        diagnostic.roc_auc([[0.5, 1], [0.6, 1]])  # no negatives


def test_meta_plots(tmp_path):
    r = meta_analysis.analyze(_generic(), model="random")
    fp = tmp_path / "forest.png"
    fn = tmp_path / "funnel.png"
    meta_analysis.forest_plot(r, str(fp))
    meta_analysis.funnel_plot(r, str(fn))
    assert fp.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    assert fn.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_meta_requires_two():
    with pytest.raises(meta_analysis.MetaAnalysisError):
        meta_analysis.analyze([{"effect": 0.2, "se": 0.1}])


def test_citations_registry():
    assert citations.ref("dersimonian1986").startswith("DerSimonian")
    assert len(citations.refs(["egger1997", "egger1997", "begg1994"])) == 2
