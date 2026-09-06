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
    TOOL_TASKS,
    Language,
    PriceQuote,
    Run,
    RunStatus,
    Scope,
    TaskType,
    TestConfirmation,
)
from app.services import (
    diagnostic,
    evidence,
    formatting,
    integrity_checker,
    meta_analysis,
    planner,
    pricing,
    report_writer,
    results_writer,
    sample_size,
    stats_executor,
    tool_report,
)
from app.store import blobs, repository


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


def estimate(
    run: Run,
    word_count: int,
    assistant_tier: str = "basic",
    consultation: str = "none",
) -> Run:
    """Step 2 (free): estimate the price from scope, data, tests, words, tier."""
    if run.status not in (RunStatus.uploaded, RunStatus.awaiting_payment):
        raise PipelineError("Upload valid data before requesting a price estimate.")

    n_tests = pricing.estimate_test_count(run.protocol_text or "", run.data_summary)
    quote: PriceQuote = pricing.quote(
        scope=run.scope,
        data_summary=run.data_summary,
        n_tests=n_tests,
        word_count=word_count,
        assistant_tier=assistant_tier,
        consultation=consultation,
    )
    run.quote = quote
    # Lock in the interaction allowance for this run from the chosen tier.
    run.assistant_tier = quote.assistant_tier
    run.assistant_allowance = quote.assistant_allowance
    run.consultation = quote.consultation
    run.status = RunStatus.awaiting_payment
    return _touch(run)


_TOOL_PRICE = {
    TaskType.meta_analysis: "price_meta_analysis_egp",
    TaskType.sample_size: "price_sample_size_egp",
    TaskType.diagnostic: "price_diagnostic_egp",
}
_TOOL_LABEL = {
    TaskType.meta_analysis: "meta-analysis",
    TaskType.sample_size: "sample-size calculation",
    TaskType.diagnostic: "diagnostic accuracy",
}


def estimate_tool(run: Run, inputs: dict) -> Run:
    """Price a tool job (flat per type) and store the user's structured inputs."""
    if run.task not in TOOL_TASKS:
        raise PipelineError("This job is not a tool job.")
    run.tool_inputs = inputs or {}
    price = int(getattr(settings, _TOOL_PRICE[run.task]))
    customer = (
        pricing.gross_up_for_fees(price)
        if settings.easykash_pass_fees_to_customer else price
    )
    run.quote = PriceQuote(
        amount_egp=price, customer_total_egp=customer,
        breakdown={_TOOL_LABEL[run.task]: price},
    )
    run.status = RunStatus.awaiting_payment
    return _touch(run)


def compute_tool(run: Run) -> Run:
    """After payment: run the engine, render an explained report, export docx+pdf."""
    _require_paid(run)
    if run.task not in TOOL_TASKS:
        raise PipelineError("This job is not a tool job.")
    inp = run.tool_inputs or {}
    run.status = RunStatus.writing
    _touch(run)
    try:
        if run.task == TaskType.sample_size:
            result = sample_size.calculate(inp.get("design", ""), inp.get("params", {}))
        elif run.task == TaskType.diagnostic:
            result = diagnostic.accuracy_2x2(
                int(inp.get("tp", 0)), int(inp.get("fp", 0)),
                int(inp.get("fn", 0)), int(inp.get("tn", 0)),
            )
        elif run.task == TaskType.meta_analysis:
            opts = {k: inp[k] for k in (
                "measure", "model", "tau2_method", "hksj", "subgroups",
                "meta_regression", "cumulative", "bias_tests") if k in inp}
            result = meta_analysis.analyze(inp.get("studies", []), **opts)
        else:
            raise PipelineError("Unsupported tool.")
    except (sample_size.SampleSizeError, diagnostic.DiagnosticError,
            meta_analysis.MetaAnalysisError, KeyError, ValueError, TypeError) as exc:
        run.status = RunStatus.failed
        run.error = f"Could not compute: {exc}"
        return _touch(run)

    run.tool_result = result
    markdown = tool_report.render(run.task.value, inp, result)
    fmt = formatting.resolve(run.format_spec)
    out_dir = Path(settings.data_dir) / "outputs"
    docx_path = out_dir / f"results_{run.id}.docx"
    pdf_path = out_dir / f"results_{run.id}.pdf"
    report_writer.markdown_to_docx(markdown, [], docx_path, fmt=fmt)
    report_writer.markdown_to_pdf(markdown, [], pdf_path, fmt=fmt)
    run.docx_blob_id = blobs.put(run.id, kind="docx", filename=docx_path.name, content=docx_path.read_bytes())
    run.pdf_blob_id = blobs.put(run.id, kind="pdf", filename=pdf_path.name, content=pdf_path.read_bytes())
    run.results_markdown = markdown
    run.docx_path = str(docx_path)
    run.pdf_path = str(pdf_path)
    run.status = RunStatus.completed
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
    # Also (re)generate scripts for any extra analyses added via the assistant.
    for analysis in run.additional_analyses:
        analysis.language = language
        analysis.script = stats_executor.generate_script(
            test=analysis.test,
            data_filename=data_filename,
            language=language,
        )
    run.status = RunStatus.script_ready
    return _touch(run)


def enqueue_execution(run: Run) -> Run:
    """Step 5 (worker mode): hand the previewed script to the background worker.

    Returns immediately with status `queued`; the worker runs the script and then
    writes the results, so the client polls the run until it reaches `completed`
    (or `failed`).
    """
    _require_paid(run)
    if run.status not in (RunStatus.script_ready, RunStatus.queued) or not run.script or not run.language:
        raise PipelineError("Generate a script before running it.")
    run.status = RunStatus.queued
    run.error = None
    return _touch(run)


def _ensure_local_data(run: Run) -> str:
    """Guarantee the dataset exists on this machine, returning its path.

    Local disk is ephemeral (wiped on redeploy) and not shared between services,
    so if the uploaded file is gone we rehydrate it from the durable blob store.
    """
    if run.data_path and Path(run.data_path).exists():
        return run.data_path
    if run.data_blob_id:
        got = blobs.get(run.data_blob_id)
        if got:
            dest_dir = Path(settings.data_dir) / "uploads" / run.id
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / got[0]
            dest.write_bytes(got[1])
            run.data_path = str(dest)
            return run.data_path
    raise PipelineError("The uploaded dataset is no longer available for this run.")


def run_script(run: Run) -> Run:
    """Step 5: execute the previewed script in the sandbox."""
    _require_paid(run)
    retryable = {RunStatus.script_ready, RunStatus.queued, RunStatus.executing, RunStatus.failed}
    if run.status not in retryable or not run.script or not run.language:
        raise PipelineError("Generate a script before running it.")

    data_path = _ensure_local_data(run)

    run.status = RunStatus.executing
    _touch(run)

    try:
        execution = stats_executor.execute(run.script, run.language, data_path)
    except Exception as exc:
        # Never leave the run stuck in `executing` on an unexpected error.
        run.status = RunStatus.failed
        run.error = f"Execution error: {exc}"
        _touch(run)
        raise PipelineError(run.error) from exc
    run.execution = execution
    if execution.status == RunStatus.failed:
        run.status = RunStatus.failed
        run.error = execution.stderr or "Script execution failed."
        return _touch(run)

    # Run any additional analyses too. One failing extra test doesn't fail the run
    # — its failure is recorded and simply omitted from the Results.
    for analysis in run.additional_analyses:
        if analysis.script:
            analysis.execution = stats_executor.execute(
                analysis.script, analysis.language, data_path
            )

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

    lang = run.output_language if run.output_language in ("en", "ar") else "en"
    is_rtl = lang == "ar"
    add_label = "تحليل إضافي" if is_rtl else "Additional analysis"

    try:
        markdown = results_writer.write_results(
            test=run.approved_test,
            execution=run.execution,
            scope=run.scope,
            language=lang,
        )
        # Append the reliable, curated methodological evidence (real citation).
        ev_md = evidence.to_markdown(run.approved_test.evidence, run.approved_test.name)
        if ev_md:
            markdown = f"{markdown}\n\n{ev_md}"

        # Collect artifacts from every analysis for the documents.
        all_artifacts = list(run.execution.artifacts)

        # Append a section per additional analysis that ran successfully.
        for analysis in run.additional_analyses:
            ex = analysis.execution
            if not ex or ex.status != RunStatus.executed:
                continue
            section = results_writer.write_results(
                test=analysis.test, execution=ex, scope=run.scope, language=lang
            )
            ev2 = evidence.to_markdown(analysis.test.evidence, analysis.test.name)
            markdown = f"{markdown}\n\n---\n\n## {add_label} — {analysis.test.name}\n\n{section}"
            if ev2:
                markdown = f"{markdown}\n\n{ev2}"
            all_artifacts.extend(ex.artifacts)

        out_dir = Path(settings.data_dir) / "outputs"
        docx_path = out_dir / f"results_{run.id}.docx"
        pdf_path = out_dir / f"results_{run.id}.pdf"

        # Resolve the chosen output format; rehydrate the style template if the
        # user chose "match my document".
        fmt = formatting.resolve(run.format_spec)
        template_path = None
        if fmt.use_template and fmt.template_blob_id:
            got = blobs.get(fmt.template_blob_id)
            if got:
                tdir = out_dir / "templates"
                tdir.mkdir(parents=True, exist_ok=True)
                template_path = tdir / f"tpl_{run.id}.docx"
                template_path.write_bytes(got[1])

        report_writer.markdown_to_docx(
            markdown, all_artifacts, docx_path, fmt=fmt, template_path=template_path, rtl=is_rtl
        )
        report_writer.markdown_to_pdf(markdown, all_artifacts, pdf_path, fmt=fmt, rtl=is_rtl)
        # Persist outputs to the shared blob store: durable across redeploys and
        # reachable by the API when the worker is what generated them.
        run.docx_blob_id = blobs.put(
            run.id, kind="docx", filename=docx_path.name, content=docx_path.read_bytes()
        )
        run.pdf_blob_id = blobs.put(
            run.id, kind="pdf", filename=pdf_path.name, content=pdf_path.read_bytes()
        )
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
