"""Statistics executor (pipeline steps 3 + 4: write the script, then run it).

Two responsibilities, kept separate on purpose:

  generate_script()  — ask the model to write the analysis script from the APPROVED
                       plan. The script is returned for a mandatory human preview
                       before anything runs.

  execute()          — hand the (already previewed) script to the sandbox and
                       collect artifacts. Contains no AI.

The script is written to read its input from `data.<ext>` in the working dir and
to write any tables/figures into an `artifacts/` subdirectory, which is how the
sandbox knows where to collect outputs from.
"""

from __future__ import annotations

from pathlib import Path

from app.models.schemas import ExecutionResult, Language, ProposedTest
from app.sandbox.docker_runner import run_in_sandbox
from app.services.llm_client import LLMClient

_SYSTEM = (
    "You are a careful data analyst. You write a single, self-contained "
    "{lang} script that performs exactly the approved statistical test and "
    "nothing else. The script must be runnable as-is."
)

_INSTRUCTIONS = """\
Write a complete {lang} script that runs the following approved analysis.

Rules:
- Read the dataset from the file named "{data_filename}" in the current directory.
- Perform ONLY this test: {test_name}
- Use these variables/columns: {variables}
- Check the stated assumptions where feasible and print the results.
- Print all numeric results (test statistic, p-value, effect size, CIs, group
  descriptives) clearly to standard output.
- Save any tables as CSV and any figures as PNG into an "artifacts/" directory
  (create it if needed).
- Do NOT access the network. Do NOT install packages. Use only the standard
  scientific stack (for Python: pandas, numpy, scipy, statsmodels, matplotlib;
  for R: base + stats).
- ROBUSTNESS (important): compute and print/save ALL statistics BEFORE creating any
  figures, and wrap the entire figure/plotting section in a try/except (Python) or
  tryCatch (R) that prints a warning and continues on error. A plotting failure
  must NEVER prevent the statistical results from being printed and saved.
- Use only CURRENT, non-deprecated library APIs. For matplotlib boxplots use
  `tick_labels=` (NOT the removed `labels=`). Assume recent library versions.
- Output ONLY the script. No explanation, no markdown code fence.

Approved plan reasoning (for context): {reasoning}
"""

_LANG_NAMES = {Language.python: "Python", Language.r: "R"}


def generate_script(
    test: ProposedTest,
    data_filename: str,
    language: Language,
    *,
    client: LLMClient | None = None,
) -> str:
    """Ask the model to write the analysis script. Returned for mandatory preview."""
    client = client or LLMClient()
    lang = _LANG_NAMES[language]
    messages = [
        {"role": "system", "content": _SYSTEM.format(lang=lang)},
        {
            "role": "user",
            "content": _INSTRUCTIONS.format(
                lang=lang,
                data_filename=data_filename,
                test_name=test.name,
                variables=", ".join(test.variables) or "(infer from the data)",
                reasoning=test.reasoning,
            ),
        },
    ]
    script = client.chat(messages)
    return _strip_code_fence(script)


def execute(
    script: str,
    language: Language,
    data_path: str | Path,
) -> ExecutionResult:
    """Run the (already previewed) script in the sandbox and collect artifacts."""
    return run_in_sandbox(script=script, language=language, data_path=str(data_path))


def _strip_code_fence(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t
        if t.rstrip().endswith("```"):
            t = t.rstrip()[:-3]
    return t.strip()
