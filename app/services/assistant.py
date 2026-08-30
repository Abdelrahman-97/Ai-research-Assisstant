"""Analyst assistant — the free-text control layer over the pipeline.

The user writes freely; the model does NOT just chat back. It interprets each
message into a structured action from a fixed whitelist, bound to *this run's*
data and the statistics workflow. The backend then validates and applies the
action through the existing guarded pipeline. Every result claim stays grounded
in real execution output; the model never invents numbers and declines anything
outside the study.

Flow per message:
    respond(run, text)
      -> interpret(run, text)      # LLM -> {reply, action}
      -> apply(run, action)        # validate + execute the whitelisted action
      -> record messages, decrement the interaction allowance, save

Allowed action types (validated in `apply`):
    none / explain      - reply only, no side effect
    set_test            - replace the proposed test (name/reasoning/variables)
    edit_variables      - change which columns the current test uses
    set_word_count      - adjust the target Results length
    regenerate_script   - re-generate the analysis script
    run_analysis        - execute (inline) or enqueue (worker) the analysis
    write_results       - write the Results section + documents
    filter_data         - subset the dataset by a simple structured rule
    add_test            - add another statistical test to the run
"""

from __future__ import annotations

import json
from pathlib import Path

from app.config import settings
from app.models.schemas import (
    Analysis,
    AssistantAction,
    ChatMessage,
    Language,
    ProposedTest,
    Run,
    RunStatus,
)
from app.services import evidence, integrity_checker, orchestrator
from app.services.llm_client import LLMClient
from app.store import blobs, repository

# Action types the model is allowed to emit. Anything else becomes a plain reply.
_ALLOWED = {
    "none", "explain", "set_test", "edit_variables", "set_word_count",
    "regenerate_script", "run_analysis", "write_results", "filter_data", "add_test",
}

# Statuses at which the plan (test choice / variables) may still be changed.
_PRE_RUN = {
    RunStatus.paid, RunStatus.awaiting_approval, RunStatus.approved,
    RunStatus.script_ready, RunStatus.failed, RunStatus.executed,
}


class AssistantError(RuntimeError):
    """The analyst request could not be applied (surfaced to the user)."""


# --------------------------------------------------------------------------- #
# Prompt construction
# --------------------------------------------------------------------------- #
_SYSTEM = (
    "You are Neura's statistical analyst assistant. You help a researcher run and "
    "refine the statistical analysis of THEIR uploaded dataset. You are NOT a "
    "general chatbot: politely decline anything unrelated to this study or to "
    "statistics. Never invent data values or results — only ever refer to numbers "
    "that appear in the provided execution output. You propose concrete actions; "
    "the researcher stays in control and the system runs them."
)

_INSTRUCTIONS = """\
Interpret the researcher's message and respond with ONLY a JSON object (no prose,
no code fence) shaped exactly like:
{{
  "reply": "a short, plain-language reply to show the researcher",
  "action": {{ "type": "<one of the allowed types>", "params": {{ ... }} }}
}}

Allowed action types and their params:
- "none": reply only (a clarification or refusal). params: {{}}
- "explain": explain the current test / an assumption / a result, grounded in the
  context below. params: {{}}
- "set_test": choose or replace the statistical test.
  params: {{"name": "Independent samples t-test", "reasoning": "...",
            "variables": ["col1","col2"]}}
- "edit_variables": change the columns the current test uses.
  params: {{"variables": ["col1","col2"]}}
- "set_word_count": change the target Results length.
  params: {{"word_count": 1200}}
- "regenerate_script": regenerate the analysis script. params: {{}}
- "run_analysis": run the analysis now. params: {{}}
- "write_results": write the Results section + documents. params: {{}}
- "filter_data": subset the dataset by ONE simple rule.
  params: {{"column": "group", "op": "!=", "value": "pilot"}}
  (op is one of ==, !=, >, <, >=, <=, in, not_in; for in/not_in, value is a list)
- "add_test": add ANOTHER statistical test to this run.
  params: {{"name": "...", "reasoning": "...", "variables": ["..."]}}

Rules:
- Pick the single most helpful action. If the user is only asking a question, use
  "explain" (or "none"). Only choose a state-changing action when they clearly ask
  to change or run something.
- Use ONLY column names that exist in the data summary below.
- Keep "reply" concise and specific to their study.

--- CURRENT RUN CONTEXT ---
{context}

--- CONVERSATION SO FAR (most recent last) ---
{history}

--- RESEARCHER MESSAGE ---
{message}
"""


def _format_context(run: Run) -> str:
    lines = [f"Run status: {run.status.value}", f"Scope: {run.scope.value}"]
    if run.protocol_text:
        lines.append(f"Protocol (excerpt): {run.protocol_text.strip()[:600]}")
    if run.data_summary:
        cols = ", ".join(
            f"{c.name} [{c.dtype}]" for c in run.data_summary.columns
        )
        lines.append(
            f"Data: {run.data_summary.n_rows} rows x {run.data_summary.n_cols} cols. "
            f"Columns: {cols}"
        )
    current = run.approved_test or run.proposed_test
    if current:
        lines.append(
            f"Current test: {current.name} | variables: {', '.join(current.variables) or '(none)'}"
        )
    if run.additional_analyses:
        extra = "; ".join(a.test.name for a in run.additional_analyses)
        lines.append(f"Additional tests: {extra}")
    if run.execution and run.execution.stdout:
        lines.append(f"Latest execution output:\n{run.execution.stdout.strip()[:1500]}")
    if run.error:
        lines.append(f"Last error: {run.error[:300]}")
    return "\n".join(lines)


def _format_history(run: Run, limit: int = 8) -> str:
    msgs = run.messages[-limit:]
    if not msgs:
        return "(no messages yet)"
    return "\n".join(f"{m.role}: {m.content}" for m in msgs)


def interpret(
    run: Run, message: str, *, client: LLMClient | None = None
) -> tuple[str, AssistantAction]:
    """Ask the model to map a free-text message to {reply, action}."""
    client = client or LLMClient(
        model=settings.assistant_model or None
    )
    prompt = _INSTRUCTIONS.format(
        context=_format_context(run),
        history=_format_history(run),
        message=message.strip()[: settings.assistant_max_message_chars],
    )
    payload = client.chat_json(
        [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": prompt},
        ]
    )
    reply = str(payload.get("reply", "")).strip() or "Done."
    raw_action = payload.get("action") or {}
    a_type = str(raw_action.get("type", "none"))
    if a_type not in _ALLOWED:
        a_type = "none"
    params = raw_action.get("params") if isinstance(raw_action.get("params"), dict) else {}
    return reply, AssistantAction(type=a_type, params=params or {})


# --------------------------------------------------------------------------- #
# Action application
# --------------------------------------------------------------------------- #
def _current_test(run: Run) -> ProposedTest | None:
    return run.approved_test or run.proposed_test


def _set_test(run: Run, name: str, reasoning: str, variables: list[str]) -> str:
    test = ProposedTest(
        name=name.strip(),
        reasoning=(reasoning or "Chosen via the analyst assistant.").strip(),
        variables=[str(v) for v in (variables or [])],
    )
    evidence.attach(test)
    run.proposed_test = test
    # Changing the test invalidates any approved plan / script / execution:
    run.approved_test = None
    run.script = None
    run.execution = None
    run.error = None
    if run.status in _PRE_RUN or run.status == RunStatus.completed:
        run.status = RunStatus.awaiting_approval
    return f"Set the test to '{test.name}'. Review and approve it to continue."


def _apply_set_test(run: Run, params: dict) -> str:
    if run.status not in (_PRE_RUN | {RunStatus.completed}):
        raise AssistantError("The test can only be changed before results are accepted.")
    name = params.get("name")
    if not name:
        raise AssistantError("I need the name of the test to set.")
    base = _current_test(run)
    variables = params.get("variables") or (base.variables if base else [])
    reasoning = params.get("reasoning") or (base.reasoning if base else "")
    return _set_test(run, name, reasoning, variables)


def _apply_edit_variables(run: Run, params: dict) -> str:
    test = _current_test(run)
    if test is None:
        raise AssistantError("There's no test yet — propose one first.")
    variables = params.get("variables")
    if not isinstance(variables, list) or not variables:
        raise AssistantError("Tell me which columns the test should use.")
    return _set_test(run, test.name, test.reasoning, [str(v) for v in variables])


def _apply_set_word_count(run: Run, params: dict) -> str:
    wc = params.get("word_count")
    try:
        wc = int(wc)
    except (TypeError, ValueError):
        raise AssistantError("Give me a target word count as a number.")
    wc = max(100, min(20000, wc))
    if run.quote:
        run.quote.word_count = wc
    note = f"Target Results length set to about {wc} words."
    if run.status not in (RunStatus.uploaded, RunStatus.awaiting_payment):
        note += " (Your price is already locked, so this only affects length.)"
    return note


def _execution_mode_run(run: Run) -> str:
    if settings.execution_mode == "worker":
        orchestrator.enqueue_execution(run)
        return "Queued the analysis — it'll run in the background."
    orchestrator.run_script(run)
    if run.status == RunStatus.failed:
        return f"The analysis failed: {run.error}"
    return "Ran the analysis. You can now write the Results section."


def _apply_run_analysis(run: Run) -> str:
    if run.status == RunStatus.approved:
        # Be helpful: generate the script first, then run.
        orchestrator.generate_script(run, run.language or Language.python)
    if run.status not in (RunStatus.script_ready, RunStatus.queued):
        raise AssistantError("Approve a plan and generate a script before running.")
    return _execution_mode_run(run)


def _apply_filter_data(run: Run, params: dict) -> str:
    if run.data_path is None and run.data_blob_id is None:
        raise AssistantError("There's no dataset attached to filter.")
    col = params.get("column")
    op = params.get("op")
    value = params.get("value")
    if not col or op not in {"==", "!=", ">", "<", ">=", "<=", "in", "not_in"}:
        raise AssistantError("I need a column, an operator, and a value to filter by.")

    # Materialize the dataset (prefer the durable blob).
    out_dir = Path(settings.data_dir) / "uploads" / run.id
    out_dir.mkdir(parents=True, exist_ok=True)
    src_path = out_dir / "data.csv"
    if run.data_blob_id:
        got = blobs.get(run.data_blob_id)
        if not got:
            raise AssistantError("The dataset is no longer available.")
        (out_dir / got[0]).write_bytes(got[1])
        df = integrity_checker.read_dataframe(out_dir / got[0])
    else:
        df = integrity_checker.read_dataframe(run.data_path)

    if col not in df.columns:
        raise AssistantError(f"There's no column called '{col}'.")

    s = df[col]
    try:
        if op == "==":
            mask = s == value
        elif op == "!=":
            mask = s != value
        elif op == ">":
            mask = s.astype(float) > float(value)
        elif op == "<":
            mask = s.astype(float) < float(value)
        elif op == ">=":
            mask = s.astype(float) >= float(value)
        elif op == "<=":
            mask = s.astype(float) <= float(value)
        elif op == "in":
            mask = s.isin(value if isinstance(value, list) else [value])
        else:  # not_in
            mask = ~s.isin(value if isinstance(value, list) else [value])
    except (ValueError, TypeError):
        raise AssistantError("That value doesn't work for this column.")

    filtered = df[mask]
    if len(filtered) < 2:
        raise AssistantError("That filter would leave too few rows to analyse.")

    filtered.to_csv(src_path, index=False)
    run.data_path = str(src_path)
    run.data_blob_id = blobs.put(
        run.id, kind="upload", filename="data.csv", content=src_path.read_bytes()
    )
    run.data_summary = integrity_checker.summarize(filtered)
    # A different dataset invalidates any script/execution.
    run.script = None
    run.execution = None
    if run.status in (RunStatus.script_ready, RunStatus.executed, RunStatus.completed, RunStatus.failed):
        run.status = RunStatus.approved if run.approved_test else RunStatus.awaiting_approval
    return (
        f"Filtered the data to {col} {op} {value!r}: "
        f"{len(filtered)} of {len(df)} rows kept. Re-run the analysis when ready."
    )


def _apply_add_test(run: Run, params: dict) -> str:
    name = params.get("name")
    if not name:
        raise AssistantError("I need the name of the test to add.")
    test = ProposedTest(
        name=str(name).strip(),
        reasoning=str(params.get("reasoning") or "Added via the analyst assistant.").strip(),
        variables=[str(v) for v in (params.get("variables") or [])],
    )
    evidence.attach(test)
    run.additional_analyses.append(Analysis(test=test, language=run.language or Language.python))
    return (
        f"Added '{test.name}' as an additional analysis. It will run and appear in "
        "the Results alongside the primary test."
    )


def apply(run: Run, action: AssistantAction) -> str:
    """Validate and execute a whitelisted action. Returns a note for the user."""
    t = action.type
    p = action.params or {}
    if t in ("none", "explain"):
        return ""                                  # reply-only
    if t == "set_test":
        return _apply_set_test(run, p)
    if t == "edit_variables":
        return _apply_edit_variables(run, p)
    if t == "set_word_count":
        return _apply_set_word_count(run, p)
    if t == "regenerate_script":
        orchestrator.generate_script(run, run.language or Language.python)
        return "Regenerated the analysis script. Preview it, then run."
    if t == "run_analysis":
        return _apply_run_analysis(run)
    if t == "write_results":
        orchestrator.write_results(run)
        return "Wrote the Results section and rebuilt the documents."
    if t == "filter_data":
        return _apply_filter_data(run, p)
    if t == "add_test":
        return _apply_add_test(run, p)
    return ""


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def remaining(run: Run) -> int:
    return max(0, run.assistant_allowance - run.assistant_used)


def respond(run: Run, message: str, *, client: LLMClient | None = None) -> tuple[str, AssistantAction]:
    """Handle one analyst message end to end. Returns (reply, action)."""
    if not settings.assistant_enabled:
        raise AssistantError("The assistant is currently unavailable.")
    if remaining(run) <= 0:
        raise AssistantError(
            "You've used all the assistant messages included with this job. "
            "You can still approve and download your results."
        )

    run.messages.append(ChatMessage(role="user", content=message.strip()))
    reply, action = interpret(run, message, client=client)

    note = ""
    try:
        note = apply(run, action)
    except (AssistantError, orchestrator.PipelineError) as exc:
        # Turn a failed action into a graceful assistant reply, not an HTTP error.
        reply = f"{reply}\n\n(I couldn't do that: {exc})".strip()
        action = AssistantAction(type="none")

    full_reply = f"{reply}\n\n{note}".strip() if note else reply
    run.assistant_used += 1
    run.messages.append(ChatMessage(role="assistant", content=full_reply, action=action))
    repository.runs.save(run)
    return full_reply, action
