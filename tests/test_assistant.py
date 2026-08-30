"""Analyst assistant tests — tiers, allowance, and each whitelisted action.

The interpreter (LLM call) is stubbed; we assert the *apply* logic and guardrails.
"""

import pandas as pd
import pytest

from app.config import get_tier, settings
from app.models.schemas import (
    AssistantAction,
    DataSummary,
    ColumnSummary,
    ProposedTest,
    Run,
    RunStatus,
    Scope,
    TaskType,
)
from app.services import assistant, pricing
from app.store import blobs, repository


# ---- pricing / tiers ------------------------------------------------------- #
def test_tier_surcharge_and_allowance_in_quote():
    q = pricing.quote(scope=Scope.thesis, data_summary=None, n_tests=1,
                      word_count=800, assistant_tier="standard")
    assert q.assistant_tier == "standard"
    assert q.assistant_allowance == get_tier("standard")["messages"]
    # surcharge appears as a line item and is included in the total
    line = next((v for k, v in q.breakdown.items() if "interaction" in k), None)
    assert line == get_tier("standard")["extra_egp"]
    assert sum(q.breakdown.values()) == q.amount_egp


def test_basic_tier_has_no_interaction_line():
    q = pricing.quote(scope=Scope.thesis, data_summary=None, n_tests=1,
                      word_count=800, assistant_tier="basic")
    assert not any("interaction" in k for k in q.breakdown)
    assert q.assistant_allowance == get_tier("basic")["messages"]


# ---- helpers --------------------------------------------------------------- #
def _paid_run(**over) -> Run:
    run = Run(
        id=repository.new_id(), user_id="u1", task=TaskType.results_section,
        scope=Scope.studies, status=RunStatus.paid, paid=True,
        assistant_allowance=5, assistant_used=0,
        data_summary=DataSummary(n_rows=6, n_cols=2, columns=[
            ColumnSummary(name="group", dtype="object", non_null=6, n_unique=2,
                          sample_values=["a", "b"]),
            ColumnSummary(name="score", dtype="int64", non_null=6, n_unique=6,
                          sample_values=["10", "20"]),
        ]),
    )
    for k, v in over.items():
        setattr(run, k, v)
    return repository.runs.create(run)


def _stub(monkeypatch, action: AssistantAction, reply="ok"):
    monkeypatch.setattr(assistant, "interpret", lambda run, message, **k: (reply, action))


# ---- allowance ------------------------------------------------------------- #
def test_allowance_is_decremented(monkeypatch):
    run = _paid_run()
    _stub(monkeypatch, AssistantAction(type="none"))
    assistant.respond(run, "hello")
    assert run.assistant_used == 1
    assert assistant.remaining(run) == 4


def test_allowance_exhausted_raises(monkeypatch):
    run = _paid_run(assistant_allowance=1, assistant_used=1)
    _stub(monkeypatch, AssistantAction(type="none"))
    with pytest.raises(assistant.AssistantError):
        assistant.respond(run, "again")


# ---- plan-editing actions -------------------------------------------------- #
def test_set_test_updates_plan_and_attaches_evidence(monkeypatch):
    run = _paid_run()
    _stub(monkeypatch, AssistantAction(type="set_test", params={
        "name": "Mann-Whitney U test", "variables": ["group", "score"]}))
    reply, action = assistant.respond(run, "use a non-parametric test")
    assert run.proposed_test.name == "Mann-Whitney U test"
    assert run.status == RunStatus.awaiting_approval
    assert run.proposed_test.evidence and run.proposed_test.evidence.matched


def test_edit_variables(monkeypatch):
    run = _paid_run(proposed_test=ProposedTest(name="Independent samples t-test",
                                               reasoning="x", variables=["group", "score"]),
                    status=RunStatus.awaiting_approval)
    _stub(monkeypatch, AssistantAction(type="edit_variables",
                                       params={"variables": ["group", "score", "age"]}))
    assistant.respond(run, "adjust for age")
    assert "age" in run.proposed_test.variables


def test_add_test_appends_additional_analysis(monkeypatch):
    run = _paid_run(approved_test=ProposedTest(name="Independent samples t-test",
                                               reasoning="x", variables=["group", "score"]),
                    status=RunStatus.approved)
    _stub(monkeypatch, AssistantAction(type="add_test", params={
        "name": "Mann-Whitney U test", "variables": ["group", "score"]}))
    assistant.respond(run, "also add a non-parametric test")
    assert len(run.additional_analyses) == 1
    assert run.additional_analyses[0].test.name == "Mann-Whitney U test"


def test_set_word_count(monkeypatch):
    from app.models.schemas import PriceQuote
    run = _paid_run(quote=PriceQuote(amount_egp=100, word_count=800))
    _stub(monkeypatch, AssistantAction(type="set_word_count", params={"word_count": 1500}))
    assistant.respond(run, "make it longer")
    assert run.quote.word_count == 1500


# ---- data filter ----------------------------------------------------------- #
def test_filter_data_subsets_and_resummarizes(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "data_dir", str(tmp_path), raising=False)
    df = pd.DataFrame({"group": ["a", "a", "b", "b", "pilot", "pilot"],
                       "score": [10, 12, 20, 22, 1, 2]})
    csv = tmp_path / "orig.csv"
    df.to_csv(csv, index=False)
    run = _paid_run()
    run.data_blob_id = blobs.put(run.id, "upload", "data.csv", csv.read_bytes())
    repository.runs.save(run)

    _stub(monkeypatch, AssistantAction(type="filter_data",
                                       params={"column": "group", "op": "!=", "value": "pilot"}))
    assistant.respond(run, "drop the pilot group")
    assert run.data_summary.n_rows == 4       # pilot rows removed


def test_off_topic_reply_changes_nothing(monkeypatch):
    run = _paid_run(proposed_test=ProposedTest(name="Independent samples t-test",
                                               reasoning="x", variables=["group", "score"]),
                    status=RunStatus.awaiting_approval)
    _stub(monkeypatch, AssistantAction(type="none"), reply="I can only help with your analysis.")
    reply, action = assistant.respond(run, "what's the weather?")
    assert action.type == "none"
    assert run.proposed_test.name == "Independent samples t-test"  # unchanged
