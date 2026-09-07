"""The engine-first router: validates the model's engine choices against the
registry and the data's real columns, and falls back to the script path when
nothing fits."""

from app.models.schemas import ColumnSummary, DataSummary, Scope
from app.services import analysis_router


def _summary():
    return DataSummary(n_rows=10, n_cols=2, columns=[
        ColumnSummary(name="score", dtype="float64", non_null=10, n_unique=9, sample_values=["1", "2"]),
        ColumnSummary(name="group", dtype="object", non_null=10, n_unique=2, sample_values=["a", "b"]),
    ])


class _FakeClient:
    def __init__(self, payload):
        self._p = payload

    def chat_json(self, messages):
        return self._p


def test_valid_engine_plan():
    plan = analysis_router.propose(
        protocol="compare", data_summary=_summary(), scope=Scope.studies,
        client=_FakeClient({"analyses": [
            {"engine": "independent_ttest", "params": {"outcome": "score", "group": "group"},
             "reasoning": "two groups"}], "fallback": False}))
    assert not plan.fallback_to_script
    assert plan.items[0].engine == "independent_ttest"
    assert plan.items[0].label == "Independent-samples t-test"


def test_missing_column_triggers_fallback():
    plan = analysis_router.propose(
        protocol="x", data_summary=_summary(), scope=Scope.studies,
        client=_FakeClient({"analyses": [
            {"engine": "independent_ttest", "params": {"outcome": "missing", "group": "group"}}],
            "fallback": False}))
    assert plan.fallback_to_script


def test_unknown_engine_dropped():
    plan = analysis_router.propose(
        protocol="x", data_summary=_summary(), scope=Scope.studies,
        client=_FakeClient({"analyses": [{"engine": "made_up_test", "params": {}}], "fallback": False}))
    assert plan.fallback_to_script


def test_explicit_fallback_kept():
    plan = analysis_router.propose(
        protocol="x", data_summary=_summary(), scope=Scope.studies,
        client=_FakeClient({"analyses": [], "fallback": True, "note": "needs a mixed model"}))
    assert plan.fallback_to_script and "mixed model" in plan.note


def test_llm_error_falls_back():
    class Boom:
        def chat_json(self, messages):
            raise RuntimeError("llm down")

    plan = analysis_router.propose(protocol="x", data_summary=_summary(),
                                   scope=Scope.studies, client=Boom())
    assert plan.fallback_to_script
