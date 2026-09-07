"""Analyst chat can edit the engine plan (add/remove/replace) before running."""

import pytest

from app.models.schemas import (
    ColumnSummary, DataSummary, EnginePlan, EnginePlanItem, Run, RunStatus, Scope, TaskType,
)
from app.services import assistant


def _run():
    cols = [ColumnSummary(name=n, dtype="x", non_null=10, n_unique=3, sample_values=["1"])
            for n in ("score", "arm", "age")]
    r = Run(id="r1", user_id="u1", task=TaskType.meta_analysis, scope=Scope.studies,
            status=RunStatus.awaiting_approval)
    r.data_summary = DataSummary(n_rows=10, n_cols=3, columns=cols)
    r.analysis_mode = "engine"
    r.engine_plan = EnginePlan(items=[EnginePlanItem(
        engine="independent_ttest", label="Independent-samples t-test",
        params={"outcome": "score", "group": "arm"})])
    r.approved_test = None
    return r


def test_add_engine():
    r = _run()
    note = assistant._apply_add_engine(r, {"engine": "correlation",
                                           "params": {"var1": "age", "var2": "score"}})
    assert "Correlation" in note
    assert [i.engine for i in r.engine_plan.items] == ["independent_ttest", "correlation"]
    assert r.status == RunStatus.awaiting_approval


def test_set_engines_replaces_plan():
    r = _run()
    assistant._apply_set_engines(r, {"analyses": [
        {"engine": "one_way_anova", "params": {"outcome": "score", "group": "arm"}}]})
    assert [i.engine for i in r.engine_plan.items] == ["one_way_anova"]


def test_remove_engine_keeps_at_least_one():
    r = _run()
    r.engine_plan.items.append(EnginePlanItem(engine="correlation",
                                              params={"var1": "age", "var2": "score"}))
    assistant._apply_remove_engine(r, {"engine": "correlation"})
    assert [i.engine for i in r.engine_plan.items] == ["independent_ttest"]
    with pytest.raises(assistant.AssistantError):
        assistant._apply_remove_engine(r, {"engine": "independent_ttest"})


def test_invalid_engine_rejected():
    r = _run()
    with pytest.raises(assistant.AssistantError):
        assistant._apply_add_engine(r, {"engine": "bogus", "params": {}})
    with pytest.raises(assistant.AssistantError):
        assistant._apply_add_engine(r, {"engine": "correlation",
                                        "params": {"var1": "age", "var2": "missing"}})


def test_set_test_drops_engine_mode():
    r = _run()
    assistant._set_test(r, "Friedman test", "non-parametric", ["score", "arm"])
    assert r.analysis_mode == "script"
    assert r.engine_plan is None
