"""Results writer (pipeline step 6: verify output, then write the Results section).

Takes the executed run's output (stdout + any table artifacts) and asks the model to
(a) sanity-check that the numbers are internally consistent, then (b) write a
Results section in Markdown grounded strictly in those numbers.

Hard rule enforced in the prompt: the model may only state values that appear in
the provided output. If something needed is missing, it must say so rather than
invent it — nothing is treated as fact unless the sandbox produced it.
"""

from __future__ import annotations

from pathlib import Path

from app.models.schemas import (
    Artifact,
    ExecutionResult,
    ProposedTest,
    Scope,
)
from app.services.llm_client import LLMClient

_SYSTEM = (
    "You are an academic writing assistant producing the Results section of a "
    "research paper. You write only what the analysis output supports. You never "
    "invent numbers. If a value is not present in the output, you explicitly note "
    "it is missing instead of guessing."
)

_INSTRUCTIONS = """\
Write the Results section for a {scope} using ONLY the analysis output below.

Requirements:
- Report the test that was run: {test_name}.
- State the key statistics from the output (test statistic, degrees of freedom,
  p-value, effect size, confidence intervals, group descriptives). You must not
  introduce any number that is not in the output.
- Round to journal convention: statistics and descriptives to 2 decimal places;
  report p-values in APA style (e.g. "p < .001", otherwise 3 decimals like
  "p = .032"). Round only for presentation — never change or invent a value.
- Write in formal, past-tense academic English as PLAIN TEXT. Do NOT use LaTeX or
  math notation: no "$", no "\\text{{}}", no "\\times". Write "mmHg", "×", "95% CI"
  as plain characters.
- Reference tables/figures by their file names in backticks, e.g.
  `descriptive_statistics.csv`, so underscores are preserved: {artifact_names}.
- If a standard value the reader would expect is absent from the output, add a
  short "[missing: ...]" note rather than fabricating it.
- Output Markdown using only headings, paragraphs, and **bold**/*italic*. Do not
  include anything except the Results section itself.

Approved plan:
- Test: {test_name}
- Reasoning: {reasoning}

Analysis output (stdout):
---
{stdout}
---

Table contents (CSV artifacts):
---
{tables}
---
"""


def _read_tables(artifacts: list[Artifact], max_chars: int = 4000) -> str:
    chunks: list[str] = []
    for art in artifacts:
        if art.kind != "table":
            continue
        p = Path(art.path)
        try:
            text = p.read_text(encoding="utf-8")
        except Exception:  # noqa: BLE001
            continue
        chunks.append(f"# {p.name}\n{text}")
    joined = "\n\n".join(chunks)
    return joined[:max_chars] if joined else "(no table artifacts)"


def write_results(
    *,
    test: ProposedTest,
    execution: ExecutionResult,
    scope: Scope,
    client: LLMClient | None = None,
) -> str:
    """Verify the output and return the Results section as Markdown."""
    client = client or LLMClient()
    artifact_names = ", ".join(a.caption or Path(a.path).name for a in execution.artifacts) or "(none)"
    prompt = _INSTRUCTIONS.format(
        scope=scope.value,
        test_name=test.name,
        reasoning=test.reasoning,
        artifact_names=artifact_names,
        stdout=execution.stdout.strip() or "(no stdout captured)",
        tables=_read_tables(execution.artifacts),
    )
    return client.chat(
        [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": prompt},
        ]
    )
