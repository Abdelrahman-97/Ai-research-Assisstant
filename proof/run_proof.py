"""Proof-of-concept runner.

Takes ONE real protocol + ONE known-answer dataset all the way through the core
pipeline using the REAL LLM — bypassing auth, payments, and the database — so you
can verify by hand that:

  1. the model proposes the CORRECT statistical test,
  2. the generated script runs and produces the RIGHT numbers,
  3. the Results section cites ONLY those numbers and invents nothing.

It also computes the expected t-test independently (with scipy) and prints it next
to the pipeline's output, so the comparison is spelled out for you.

Usage (from the project root, with your key in .env):
    pip install -r requirements.txt scipy matplotlib statsmodels
    python proof/run_proof.py

The one risky step (statistical test choice) is printed and auto-approved here —
that's the human checkpoint; in the app a person clicks Approve.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Make the app importable when run as `python proof/run_proof.py`.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import settings  # noqa: E402
from app.models.schemas import Language, Scope  # noqa: E402

HERE = Path(__file__).resolve().parent
DATA = HERE / "bp_study.csv"
PROTOCOL = (HERE / "protocol.txt").read_text(encoding="utf-8")


def rule(title: str) -> None:
    print("\n" + "=" * 70 + f"\n{title}\n" + "=" * 70)


def expected_answer() -> None:
    """Independent ground truth so you can check the pipeline by hand."""
    import pandas as pd
    from scipy import stats

    df = pd.read_csv(DATA)
    c = df[df["group"] == "control"]["systolic_bp"]
    t_ = df[df["group"] == "treatment"]["systolic_bp"]
    t_stat, p = stats.ttest_ind(c, t_)
    rule("GROUND TRUTH (computed independently with scipy)")
    print(f"control  n={len(c)}  mean={c.mean():.2f}  sd={c.std(ddof=1):.2f}")
    print(f"treatment n={len(t_)}  mean={t_.mean():.2f}  sd={t_.std(ddof=1):.2f}")
    print(f"Independent-samples t-test:  t = {t_stat:.4f},  p = {p:.6g}")
    print("Expected: the tool should propose an independent-samples t-test and")
    print("report numbers matching the above.")


def main() -> int:
    # Force local subprocess execution (no Docker image needed) and write outputs here.
    settings.sandbox_force_subprocess = True
    settings.data_dir = str(HERE / "output")
    Path(settings.data_dir).mkdir(parents=True, exist_ok=True)

    if not settings.llm_api_key:
        print("LLM_API_KEY is not set. Put it in your .env file, e.g.:\n")
        print("  LLM_API_KEY=<your Google AI Studio key>")
        print("  LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/")
        print("  LLM_MODEL=gemini-2.5-flash\n")
        return 1

    from app.services import (  # imported here so a missing key fails first
        integrity_checker,
        planner,
        report_writer,
        results_writer,
        stats_executor,
    )

    print(f"Provider: {settings.llm_base_url}  |  model: {settings.llm_model}")

    # 1) Validate + summarize the data (free step in the real app).
    rule("STEP 1 — data integrity + summary")
    report = integrity_checker.check_data_file(DATA)
    if not report.ok:
        print("Data failed validation:", report.issues)
        return 1
    s = report.summary
    print(f"rows={s.n_rows}, cols={s.n_cols}")
    for col in s.columns:
        print(f"  - {col.name} ({col.dtype}), e.g. {', '.join(col.sample_values[:4])}")

    # 2) AI proposes the plan.
    rule("STEP 2 — AI proposes a statistical plan  [real LLM call]")
    plan = planner.propose_plan(protocol=PROTOCOL, data_summary=s, scope=Scope.studies)
    print(f"Proposed test : {plan.name}")
    print(f"Variables     : {', '.join(plan.variables)}")
    print(f"Reasoning     : {plan.reasoning}")
    if plan.assumptions:
        print(f"Assumptions   : {'; '.join(plan.assumptions)}")

    # 3) Human checkpoint (auto-approved here for the proof).
    rule("STEP 3 — HUMAN CHECKPOINT")
    print(">>> Auto-approving the plan for this proof run.")
    print(">>> (In the app, a person reviews this and clicks Approve or edits it.)")

    # 4) AI writes the analysis script.
    rule("STEP 4 — AI writes the analysis script  [real LLM call]")
    script = stats_executor.generate_script(plan, "data.csv", Language.python)
    print(script)

    # 5) Execute the script in the sandbox (subprocess here).
    rule("STEP 5 — execute the script")
    execution = stats_executor.execute(script, Language.python, str(DATA))
    print("status:", execution.status.value, "| exit:", execution.exit_code)
    print("--- stdout ---")
    print(execution.stdout or "(none)")
    if execution.stderr:
        print("--- stderr ---")
        print(execution.stderr)
    print("artifacts:", [a.caption for a in execution.artifacts] or "(none)")
    if execution.status.value == "failed":
        print("\nExecution failed. If it's a missing package, run:")
        print("  pip install scipy matplotlib statsmodels")
        return 1

    # 6) AI writes the Results section, grounded in the output.
    rule("STEP 6 — AI writes the Results section  [real LLM call]")
    md = results_writer.write_results(test=plan, execution=execution, scope=Scope.studies)
    print(md)

    # 7) Export to .docx and .pdf.
    rule("STEP 7 — export")
    out_dir = Path(settings.data_dir)
    docx = report_writer.markdown_to_docx(md, execution.artifacts, out_dir / "proof_results.docx")
    pdf = report_writer.markdown_to_pdf(md, execution.artifacts, out_dir / "proof_results.pdf")
    print("Word:", docx)
    print("PDF :", pdf)

    # 8) Ground truth for hand comparison.
    expected_answer()

    rule("HAND-CHECK CHECKLIST")
    print("[ ] Did it propose an INDEPENDENT-SAMPLES t-test?")
    print("[ ] Do the t and p in the script output match the ground truth above?")
    print("[ ] Does the Results section state those same numbers (no invented values)?")
    print("[ ] Open the .docx — are the right numbers and prose there?")
    print("\nIf all four are yes, the core concept is proven.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
