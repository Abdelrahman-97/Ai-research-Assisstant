"""Pipeline orchestrator — the run state machine.

Coordinates the services in order and persists the Run after each step. This is
where the MANDATORY HUMAN CHECKPOINT is enforced: propose_plan() stops at
`awaiting_approval`, and no script is generated or executed until approve_plan()
is called. Each method advances the run by one stage.

    create_run
      -> ingest(protocol, data_path)      # integrity check + summary
      -> propose_plan()                   # AI proposes -> awaiting_approval
      -> approve_plan(confirmation)        # HUMAN confirms/edits -> approved
      -> generate_script(language)         # AI writes script -> script_ready (preview)
      -> run_script()                     # sandbox executes -> executed
      -> write_results()                  # AI verifies + writes -> completed (with .docx)
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from app.config import settings
from app.models.schemas import (
    Language,
    Run,
    RunStatus,
    Scope,
    TaskType,
    TestConfirmation,
)
from app.services import (
    integrity_checker,
    planner,
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
    """Step 1: validate + summarize the uploaded data."""
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


def propose_plan(run: Run) -> Run:
    """Step 2: AI proposes a statistical plan, then STOP for the human checkpoint."""
    if run.status != RunStatus.uploaded or run.data_summary is None:
        raise PipelineError("Upload valid data before requesting a plan.")

    run.proposed_test = planner.propose_plan(
        protocol=run.protocol_text or "",
        data_summary=run.data_summary,
        scope=run.scope,
    )
    run.status = RunStatus.awaiting_approval
    return _touch(run)


def approve_plan(run: Run, confirmation: TestConfirmation) -> Run:
    """Human checkpoint: confirm or edit the plan. Nothing runs until this passes."""
    if run.status != RunStatus.awaiting_approval:
        raise PipelineError("There is no plan awaiting approval on this run.")
    if not confirmation.confirmed and confirmation.edited_plan is None:
        raise PipelineError(
            "Plan not approved and no edited plan supplied — cannot proceed."
        )

    run.approved_test = confirmation.edited_plan or run.proposed_test
    run.status = RunStatus.approved
    return _touch(run)


def generate_script(run: Run, language: Language) -> Run:
    """Step 3: AI writes the script. Returned for mandatory preview before running."""
    if run.status != RunStatus.approved or run.approved_test is None:
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
    """Step 4: execute the previewed script in the sandbox."""
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
    """Step 5: AI verifies output, writes the Results section, exports .docx."""
    if run.status != RunStatus.executed or run.execution is None or run.approved_test is None:
        raise PipelineError("Run the script before writing results.")

    run.status = RunStatus.writing
    _touch(run)

    markdown = results_writer.write_results(
        test=run.approved_test,
        execution=run.execution,
        scope=run.scope,
    )
    run.results_markdown = markdown

    docx_path = Path(settings.data_dir) / "outputs" / f"results_{run.id}.docx"
    report_writer.markdown_to_docx(markdown, run.execution.artifacts, docx_path)
    run.docx_path = str(docx_path)

    run.status = RunStatus.completed
    return _touch(run)
