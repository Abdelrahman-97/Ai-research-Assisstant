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
    Artifact,
    FormatSpec,
    Language,
    PriceQuote,
    Run,
    RunStatus,
    Scope,
    TaskType,
    TestConfirmation,
)
from app.services import (
    analysis_router,
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
from app.services.stat_engines import registry as engine_registry
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
    # Meta-analysis is written up as a thesis/paper Results section: capture the
    # write-up scope, language, and reference/format style chosen by the user.
    if run.task == TaskType.meta_analysis:
        scope = (inputs or {}).get("scope")
        if scope in ("thesis", "studies"):
            run.scope = Scope(scope)
        lang = (inputs or {}).get("output_language")
        if lang in ("en", "ar"):
            run.output_language = lang
        preset = (inputs or {}).get("preset")
        if preset in ("standard", "apa", "vancouver", "two_column"):
            run.format_spec = FormatSpec(preset=preset)
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
            if inp.get("pairs"):
                result = diagnostic.roc_auc(
                    inp["pairs"], bool(inp.get("higher_is_positive", True))
                )
            else:
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
    fmt = formatting.resolve(run.format_spec)
    out_dir = Path(settings.data_dir) / "outputs"
    docx_path = out_dir / f"results_{run.id}.docx"
    pdf_path = out_dir / f"results_{run.id}.pdf"

    # Meta-analysis: add forest + funnel plots as figures in the report.
    artifacts: list[Artifact] = []
    if run.task == TaskType.meta_analysis:
        try:
            art_dir = out_dir / "artifacts" / run.id
            art_dir.mkdir(parents=True, exist_ok=True)
            fp = art_dir / "forest.png"
            fn = art_dir / "funnel.png"
            meta_analysis.forest_plot(result, str(fp))
            meta_analysis.funnel_plot(result, str(fn))
            artifacts = [
                Artifact(kind="figure", path=str(fp), caption="Forest plot"),
                Artifact(kind="figure", path=str(fn), caption="Funnel plot"),
            ]
        except Exception:  # noqa: BLE001 - a plotting failure must not fail the report
            artifacts = []
    elif run.task == TaskType.diagnostic and isinstance(result, dict) and result.get("roc_points"):
        try:
            art_dir = out_dir / "artifacts" / run.id
            art_dir.mkdir(parents=True, exist_ok=True)
            rp = art_dir / "roc.png"
            diagnostic.roc_plot(result, str(rp))
            artifacts = [Artifact(kind="figure", path=str(rp), caption="ROC curve")]
        except Exception:  # noqa: BLE001
            artifacts = []
    elif run.task == TaskType.sample_size:
        try:
            art_dir = out_dir / "artifacts" / run.id
            art_dir.mkdir(parents=True, exist_ok=True)
            pc = art_dir / "power_curve.png"
            if sample_size.power_curve(result, str(pc)):
                artifacts = [Artifact(kind="figure", path=str(pc), caption="Power curve")]
        except Exception:  # noqa: BLE001
            artifacts = []

    # Build the report body. Meta-analysis is written up as a thesis/paper Results
    # section: an AI narrative grounded strictly in the deterministic numbers,
    # followed by the exact tables/figures/references. Everything else uses the
    # explained tool report directly.
    is_rtl = run.output_language == "ar"
    if run.task == TaskType.meta_analysis:
        facts = tool_report.render("meta_analysis", inp, result)  # ground-truth numbers
        markdown = facts  # deterministic full report (also the safe fallback)
        if settings.llm_api_key:  # only attempt the AI narrative when an LLM is configured
            try:
                narrative = results_writer.write_meta_narrative(
                    facts=facts, scope=run.scope, language=run.output_language,
                ).strip()
                if narrative:
                    markdown = narrative + "\n\n" + tool_report.meta_detail(inp, result)
            except Exception:  # noqa: BLE001 - never fail a paid job on the writer (incl. LLMError)
                markdown = facts
    else:
        markdown = tool_report.render(run.task.value, inp, result)

    report_writer.markdown_to_docx(markdown, artifacts, docx_path, fmt=fmt, rtl=is_rtl)
    report_writer.markdown_to_pdf(markdown, artifacts, pdf_path, fmt=fmt, rtl=is_rtl)
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


def _engine_plan_summary_test(plan) -> "ProposedTest":
    """Synthesize a ProposedTest so the existing plan UI/fields work in engine mode."""
    from app.models.schemas import ProposedTest
    names = "; ".join(i.label or i.engine for i in plan.items)
    reasoning = " ".join(f"{i.label}: {i.reasoning}".strip() for i in plan.items) or \
        "Audited engines selected for your data and protocol."
    variables = sorted({v for i in plan.items for v in _plan_item_columns(i)})
    return ProposedTest(name=names or "Selected analyses", reasoning=reasoning, variables=variables)


def _plan_item_columns(item) -> list[str]:
    cols: list[str] = []
    for v in (item.params or {}).values():
        if isinstance(v, str):
            cols.append(v)
        elif isinstance(v, list):
            cols.extend(str(x) for x in v)
    return cols


def propose_plan(run: Run) -> Run:
    """Step 3: AI proposes a plan, then STOP for the human checkpoint.

    Engine-first: the router picks audited engines. If it can't cover the request
    (or no LLM is configured), we fall back to the AI-generated-script planner.
    """
    _require_paid(run)
    if run.status != RunStatus.paid or run.data_summary is None:
        raise PipelineError("Pay for the run before requesting a plan.")

    plan = None
    if settings.llm_api_key:
        try:
            plan = analysis_router.propose(
                protocol=run.protocol_text or "",
                data_summary=run.data_summary,
                scope=run.scope,
            )
        except Exception:  # noqa: BLE001 - fall back to the script planner
            plan = None

    if plan is not None and not plan.fallback_to_script and plan.items:
        run.analysis_mode = "engine"
        run.engine_plan = plan
        run.proposed_test = _engine_plan_summary_test(plan)
    else:
        run.analysis_mode = "script"
        run.engine_plan = plan  # keep the note (why fallback) if present
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
    # Re-attach curated evidence in case the user edited the test choice. In engine
    # mode each engine carries its own citation, so we skip this step.
    if run.approved_test is not None and run.analysis_mode != "engine":
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

    # Engine mode: there is no code to generate. Show a readable description of
    # the audited engines that will run, and advance to the "ready to run" state.
    if run.analysis_mode == "engine" and run.engine_plan and run.engine_plan.items:
        lines = ["# Audited analyses that will run (no code is generated)\n"]
        for i, it in enumerate(run.engine_plan.items, 1):
            cols = ", ".join(f"{k}={v}" for k, v in (it.params or {}).items())
            lines.append(f"{i}. **{it.label or it.engine}** — {cols}")
        run.script = "\n".join(lines)
        run.language = language
        run.status = RunStatus.script_ready
        return _touch(run)

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


def _run_engine_plan(run: Run, data_path: str) -> list[dict]:
    """Run every engine in the plan deterministically; collect their results.

    One engine failing doesn't fail the run — its error is recorded and it's simply
    omitted from the write-up.
    """
    df = integrity_checker.read_dataframe(data_path)
    art_dir = Path(settings.data_dir) / "outputs" / "artifacts" / run.id
    art_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict] = []
    for item in run.engine_plan.items:
        try:
            r = engine_registry.run_engine(item.engine, df, item.params, fig_dir=art_dir)
            results.append({
                "engine": r["key"], "title": r["title"], "markdown": r["markdown"],
                "values": r["values"], "references": r["references"],
                "figure_path": r.get("figure_path"),
            })
        except Exception as exc:  # noqa: BLE001 - record and skip a bad engine
            results.append({"engine": item.engine, "title": item.label or item.engine,
                            "error": str(exc)})
    return results


def run_script(run: Run) -> Run:
    """Step 5: run the analysis — audited engines (engine mode) or the sandbox script."""
    _require_paid(run)
    retryable = {RunStatus.script_ready, RunStatus.queued, RunStatus.executing, RunStatus.failed}
    if run.status not in retryable or not run.script or not run.language:
        raise PipelineError("Generate a script before running it.")

    data_path = _ensure_local_data(run)

    # Engine mode: run the audited engines instead of a sandboxed script.
    if run.analysis_mode == "engine" and run.engine_plan and run.engine_plan.items:
        run.status = RunStatus.executing
        _touch(run)
        try:
            results = _run_engine_plan(run, data_path)
        except Exception as exc:  # noqa: BLE001
            run.status = RunStatus.failed
            run.error = f"Analysis error: {exc}"
            _touch(run)
            raise PipelineError(run.error) from exc
        run.engine_results = results
        if not any("error" not in r for r in results):
            run.status = RunStatus.failed
            run.error = "; ".join(r.get("error", "") for r in results) or "All analyses failed."
            return _touch(run)
        run.status = RunStatus.executed
        run.error = None
        return _touch(run)

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


def _strip_refs(md: str) -> str:
    """Drop a trailing '## References' block so we can append one combined list."""
    return md.split("\n## References")[0].rstrip()


def _resolve_fmt_template(run: Run, out_dir: Path):
    fmt = formatting.resolve(run.format_spec)
    template_path = None
    if fmt.use_template and fmt.template_blob_id:
        got = blobs.get(fmt.template_blob_id)
        if got:
            tdir = out_dir / "templates"
            tdir.mkdir(parents=True, exist_ok=True)
            template_path = tdir / f"tpl_{run.id}.docx"
            template_path.write_bytes(got[1])
    return fmt, template_path


def _write_engine_results(run: Run) -> Run:
    """Step 6 (engine mode): write the Results narrative from the audited engines."""
    if run.status != RunStatus.executed or not run.engine_results:
        raise PipelineError("Run the analysis before writing results.")
    run.status = RunStatus.writing
    _touch(run)

    lang = run.output_language if run.output_language in ("en", "ar") else "en"
    is_rtl = lang == "ar"
    ok = [r for r in run.engine_results if "error" not in r]
    if not ok:
        run.status = RunStatus.failed
        run.error = "No analysis produced a usable result."
        return _touch(run)

    facts = "\n\n".join(_strip_refs(r["markdown"]) for r in ok)
    markdown = facts
    if settings.llm_api_key:
        try:
            narrative = results_writer.write_engine_results(
                facts=facts, scope=run.scope, language=lang).strip()
            if narrative:
                markdown = narrative + "\n\n## Detailed statistical output\n\n" + facts
        except Exception:  # noqa: BLE001 - never fail a paid job on the writer
            markdown = facts

    # one combined References section (curated, from the engines)
    refs: list[str] = []
    for r in ok:
        for ref in r.get("references", []):
            if ref and ref not in refs:
                refs.append(ref)
    if refs:
        markdown += "\n\n## References\n\n" + "\n".join(f"{i + 1}. {x}" for i, x in enumerate(refs))

    artifacts = [Artifact(kind="figure", path=r["figure_path"], caption=r.get("title"))
                 for r in ok if r.get("figure_path")]

    out_dir = Path(settings.data_dir) / "outputs"
    out_dir.mkdir(parents=True, exist_ok=True)
    docx_path = out_dir / f"results_{run.id}.docx"
    pdf_path = out_dir / f"results_{run.id}.pdf"
    fmt, template_path = _resolve_fmt_template(run, out_dir)
    report_writer.markdown_to_docx(markdown, artifacts, docx_path, fmt=fmt,
                                   template_path=template_path, rtl=is_rtl)
    report_writer.markdown_to_pdf(markdown, artifacts, pdf_path, fmt=fmt, rtl=is_rtl)
    run.docx_blob_id = blobs.put(run.id, kind="docx", filename=docx_path.name,
                                 content=docx_path.read_bytes())
    run.pdf_blob_id = blobs.put(run.id, kind="pdf", filename=pdf_path.name,
                                content=pdf_path.read_bytes())
    run.results_markdown = markdown
    run.docx_path = str(docx_path)
    run.pdf_path = str(pdf_path)
    run.status = RunStatus.completed
    return _touch(run)


def write_results(run: Run) -> Run:
    """Step 6: AI verifies output, writes the Results section, exports docx + pdf."""
    _require_paid(run)
    if run.analysis_mode == "engine" and run.engine_results is not None:
        return _write_engine_results(run)
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
