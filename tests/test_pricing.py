"""Pricing algorithm tests."""

from app.config import settings
from app.models.schemas import ColumnSummary, DataSummary, Scope
from app.services import pricing


def _summary(rows=100, cols=4):
    cats = [ColumnSummary(name=f"c{i}", dtype="float64", non_null=rows, n_unique=rows)
            for i in range(cols)]
    return DataSummary(n_rows=rows, n_cols=cols, columns=cats)


def test_quote_breakdown_sums_to_total():
    q = pricing.quote(scope=Scope.thesis, data_summary=_summary(), n_tests=3, word_count=1500)
    assert q.amount_egp == sum(q.breakdown.values())
    assert q.estimated_tests == 3
    assert q.word_count == 1500


def test_thesis_costs_more_than_paper_at_same_inputs():
    s = _summary()
    thesis = pricing.quote(scope=Scope.thesis, data_summary=s, n_tests=2, word_count=1000)
    paper = pricing.quote(scope=Scope.studies, data_summary=s, n_tests=2, word_count=1000)
    assert thesis.amount_egp > paper.amount_egp
    assert thesis.amount_egp - paper.amount_egp == (
        settings.price_base_thesis_egp - settings.price_base_paper_egp
    )


def test_more_tests_and_words_cost_more():
    s = _summary()
    small = pricing.quote(scope=Scope.studies, data_summary=s, n_tests=1, word_count=500)
    big = pricing.quote(scope=Scope.studies, data_summary=s, n_tests=5, word_count=5000)
    assert big.amount_egp > small.amount_egp


def test_heuristic_test_count_fallback_no_api_key():
    # With no MOONSHOT_API_KEY, estimate_test_count falls back to the heuristic
    # (constructing KimiClient raises, which is caught).
    n = pricing.estimate_test_count("compare groups", _summary(cols=4))
    assert 1 <= n <= 8
