"""Curated methodological-evidence base tests."""

from app.models.schemas import ProposedTest
from app.services import evidence


def test_parametric_t_test_evidence():
    ev = evidence.lookup("Independent samples t-test")
    assert ev.matched
    assert ev.family == "parametric"
    assert "Student" in ev.citation
    assert ev.assumptions


def test_nonparametric_mann_whitney_evidence():
    ev = evidence.lookup("Mann-Whitney U test")
    assert ev.matched
    assert ev.family == "non-parametric"
    assert "Mann" in ev.citation and "Whitney" in ev.citation


def test_alias_matching_variants():
    assert evidence.lookup("unpaired t test").canonical_name == "independent t test"
    assert evidence.lookup("one-way ANOVA").canonical_name == "one way anova"
    assert evidence.lookup("Kruskal–Wallis test").canonical_name == "kruskal wallis"
    assert evidence.lookup("Chi-square test of independence").canonical_name == "chi square"
    assert evidence.lookup("Spearman's rank correlation").canonical_name == "spearman correlation"


def test_extended_tests_matched():
    assert evidence.lookup("linear mixed-effects model").canonical_name == "linear mixed model"
    assert evidence.lookup("McNemar's test").canonical_name == "mcnemar"
    assert evidence.lookup("log-rank test").canonical_name == "log rank"
    assert evidence.lookup("Poisson regression").canonical_name == "poisson regression"
    assert "Bland" in evidence.lookup("Bland-Altman analysis").citation


def test_welch_anova_beats_welch_t_test():
    # "Welch's ANOVA" must not be swallowed by the "welch" -> t-test alias.
    assert evidence.lookup("Welch's ANOVA").canonical_name == "welch anova"
    assert evidence.lookup("Welch's t-test").canonical_name == "independent t test"


def test_every_alias_target_exists():
    from app.services.evidence import _ALIASES, _BASE
    for _, key in _ALIASES:
        assert key in _BASE, f"alias points to missing base entry: {key}"


def test_unknown_test_is_unmatched_not_invented():
    ev = evidence.lookup("some bespoke bootstrap permutation thing")
    assert not ev.matched
    assert ev.citation is None
    assert ev.note  # tells the user to verify manually


def test_attach_and_markdown():
    t = ProposedTest(name="Paired t-test", reasoning="x", variables=[])
    evidence.attach(t)
    assert t.evidence and t.evidence.matched
    md = evidence.to_markdown(t.evidence, t.name)
    assert "## Statistical method" in md
    assert "Reference:" in md
    assert "Student" in md
    # unmatched -> empty markdown (nothing invented)
    assert evidence.to_markdown(evidence.lookup("nonexistent"), "nonexistent") == ""
