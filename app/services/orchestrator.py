"""Pipeline orchestrator — the run state machine.

Coordinates the services in order and persists the Run after each step. Two gates
are enforced here:
  - PAYMENT: no analysis step runs until the run is paid (payment happens after
    the free upload + price estimate).
  - HUMAN CHECKPOINT: propose_plan() stops at `awaiting_approval`, and no script
    is generated or executed until approve_plan() is called.

    create_run
      -> ingest(protocol, data_path)       # integrity check + summary  -> uploaded
      -> estimate(word_count)              # price quote  -> awaiting_payment
      -> mark_paid(reference)              # payment confirmed  -> paid
      -> propose_plan()                    # AI proposes  -> awaiting_approval
      -> approve_plan(confirmation)         # HUMAN confirms/edits  -> approved
      -> generate_script(language)          # AI writes script  -> script_ready
      -> run_script()                      # sandbox executes  -> executed
      -> write_results()                   # AI verifies + writes  -> completed (docx+pdf)
      -> accept()                          # user accepts  -> accepted (30-day clock)
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.config import settings
from app.models.schemas import (
    Language,
    PriceQuote,
    Run,
    RunStatus,
    Scope,
    TaskType,
    TestConfirmation,
)
from app.services import (
    evidence,
    integrity_checker,
    planner,
    pricing,
    report_writer,
    results_writer,
    stats_executor,
)
from app.store import repository


class PipelineError(RuntimeError):
    """Raised when a pipeline step is called out of order or fails."""


def _touch(run: Run) -> Run:
    run.updated_at = datetime.now(timezone.utc)
    return repository.runs.save(run)


def create_run(user_id: str, task: TaskType, scope: Scope) -> Run:
    run = Run(id=repository.new_id(), user_id=user_id, task=task, scope=scope)
    return repository.runs.create(run)


def ingest(run: Run, protocol_text: str, data_path: str) -> Run:
    """Step 1 (free): validate + summarize the uploaded data."""
    report = integrity_checker.check_data_file(data_path)
    if not report.ok:
        run.status = RunStatus.failed
        run.error = "; ".join(report.issues) or "Data file failed validation."
        return _touch(run)

    run.protocol_text = protocol_text
    run.data_path = data_path
    run.data_summary = report.summary
    run.status = RunStatus.uploaded
    run.error = None
    return _touch(run)


def estimate(run: Run, word_count: int) -> Run:
    """Step 2 (free): estimate the price from scope, data, tests, and word count."""
    if run.status not in (RunStatus.uploaded, RunStatus.awaiting_payment):
        raise PipelineError("Upload valid data before requesting a price estimate.")

    n_tests = pricing.estimate_test_count(run.protocol_text or "", run.data_summary)
    quote: PriceQuote = pricing.quote(
        scope=run.scope,
        data_summary=run.data_summary,
        n_tests=n_tests,
        word_count=word_count,
    )
    run.quote = quote
    run.status = RunStatus.awaiting_payment
    return _touch(run)


def mark_paid(run: Run, reference: str) -> Run:
    """Payment confirmed by the gateway callback — unlock the analysis."""
    if run.status not in (RunStatus.awaiting_payment, RunStatus.paid):
        raise PipelineError("Get a price estimate before paying.")
    run.paid = True
    run.payment_reference = reference
    run.status = RunStatus.paid
    return _touch(run)


def _require_paid(run: Run) -> None:
    if not run.paid:
        raise PipelineError("This run has not been paid for yet.")


def propose_plan(run: Run) -> Run:
    """Step 3: AI proposes a plan, then STOP for the human checkpoint."""
    _require_paid(run)
    if run.status != RunStatus.paid or run.data_summary is None:
        raise PipelineError("Pay for the run before requesting a plan.")

    run.proposed_test = planner.propose_plan(
        protocol=run.protocol_text or "",
        data_summary=run.data_summary,
        scope=run.scope,
    )
    run.status = RunStatus.awaiting_approval
    return _touch(run)


def approve_plan(run: Run, confirmation: TestConfirmation) -> Run:
    """Human checkpoint: confirm or edit the plan. Nothing runs until this passes."""
    _require_paid(run)
    if run.status != RunStatus.awaiting_approval:
        raise PipelineError("There is no plan awaiting approval on this run.")
    if not confirmation.confirmed and confirmation.edited_plan is None:
        raise PipelineError(
            "Plan not approved and no edited plan supplied — cannot proceed."
        )

    run.approved_test = confirmation.edited_plan or run.proposed_test
    # Re-attach curated evidence in case the user edited the test choice.
    if run.approved_test is not None:
        evidence.attach(run.approved_test)
    run.status = RunStatus.approved
    return _touch(run)


def generate_script(run: Run, language: Language) -> Run:
    """Step 4: AI writes the script. Returned for mandatory preview before running.

    Also usable as a retry: after a failed execution the user can regenerate the
    script and run again (the approved plan is preserved).
    """
    _require_paid(run)
    retryable = {RunStatus.approved, RunStatus.script_ready, RunStatus.failed}
    if run.status not in retryable or run.approved_test is None:
        raise PipelineError("Approve a plan before generating a script.")

    data_filename = f"data{Path(run.data_path).suffix.lower()}" if run.data_path else "data.csv"
    run.language = language
    run.script = stats_executor.generate_script(
        test=run.approved_test,
        data_filename=data_filename,
        language=language,
    )
    run.status = RunStatus.script_ready
    return _touch(run)


def run_script(run: Run) -> Run:
    """Step 5: execute the previewed script in the sandbox."""
    _require_paid(run)
    if run.status != RunStatus.script_ready or not run.script or not run.language:
        raise PipelineError("Generate a script before running it.")

    run.status = RunStatus.executing
    _touch(run)

    execution = stats_executor.execute(run.script, run.language, run.data_path)
    run.execution = execution
    if execution.status == RunStatus.failed:
        run.status = RunStatus.failed
        run.error = execution.stderr or "Script execution failed."
        return _touch(run)

    run.status = RunStatus.executed
    run.error = None
    return _touch(run)


def write_results(run: Run) -> Run:
    """Step 6: AI verifies output, writes the Results section, exports docx + pdf."""
    _require_paid(run)
    if run.status != RunStatus.executed or run.execution is None or run.approved_test is None:
        raise PipelineError("Run the script before writing results.")

    run.status = RunStatus.writing
    _touch(run)

    try:
        markdown = results_writer.write_results(
            test=run.approved_test,
            execution=run.execution,
            scope=run.scope,
        )
        # Append the reliable, curated methodological evidence (real citation).
        ev_md = evidence.to_markdown(run.approved_test.evidence, run.approved_test.name)
        if ev_md:
            markdown = f"{markdown}\n\n{ev_md}"
        out_dir = Path(settings.data_dir) / "outputs"
        docx_path = out_dir / f"results_{run.id}.docx"
        pdf_path = out_dir / f"results_{run.id}.pdf"
        report_writer.markdown_to_docx(markdown, run.execution.artifacts, docx_path)
        report_writer.markdown_to_pdf(markdown, run.execution.artifacts, pdf_path)
    except Exception:
        # Revert so the user can retry writing without re-running the analysis.
        run.status = RunStatus.executed
        _touch(run)
        raise

    run.results_markdown = markdown
    run.docx_path = str(docx_path)
    run.pdf_path = str(pdf_path)
    run.status = RunStatus.completed
    return _touch(run)


def accept(run: Run) -> Run:
    """User accepts the finished results — starts the retention clock."""
    if run.status not in (RunStatus.completed, RunStatus.accepted):
        raise PipelineError("Results are not ready to accept yet.")
    now = datetime.now(timezone.utc)
    run.accepted_at = now
    run.expires_at = now + timedelta(days=settings.retention_days)
    run.status = RunStatus.accepted
    return _touch(run)
