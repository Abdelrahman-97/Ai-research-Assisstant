"""Planner (pipeline step 2: propose a statistical plan).

Sends the data summary + the study protocol to Kimi and asks for a proposed
statistical test with reasoning, in strict JSON. The result is a *proposal* —
it does not run and is not trusted until the human approves it at the checkpoint.
"""

from __future__ import annotations

import json

from app.models.schemas import DataSummary, ProposedTest, Scope
from app.services.llm_client import KimiClient

_SYSTEM = (
    "You are a biostatistics assistant helping a researcher choose the correct "
    "statistical test for their study. You propose; the researcher always confirms. "
    "Base your choice only on the provided data summary and protocol. Prefer "
    "widely accepted, citable methods. If the correct test is ambiguous, say so "
    "in the reasoning and pick the most defensible option."
)

_INSTRUCTIONS = """\
Return ONLY a JSON object (no prose, no code fence) with exactly these keys:
{{
  "name": "the statistical test, e.g. 'Independent samples t-test'",
  "reasoning": "why this test fits the data and protocol, 2-4 sentences",
  "variables": ["the column names the test uses"],
  "assumptions": ["assumptions that must hold, e.g. 'normality of residuals'"],
  "citations": ["short methodological references if applicable"]
}}

Study scope: {scope}
Research protocol / methods:
---
{protocol}
---
Data summary (columns with dtype, non-null counts, sample values):
---
{data_summary}
---
"""


def _format_data_summary(summary: DataSummary) -> str:
    lines = [f"rows={summary.n_rows}, cols={summary.n_cols}"]
    for c in summary.columns:
        lines.append(
            f"- {c.name} | {c.dtype} | non_null={c.non_null} | "
            f"unique={c.n_unique} | e.g. {', '.join(c.sample_values)}"
        )
    return "\n".join(lines)


def propose_plan(
    *,
    protocol: str,
    data_summary: DataSummary,
    scope: Scope,
    client: KimiClient | None = None,
) -> ProposedTest:
    """Ask Kimi to propose a statistical test. Returns a ProposedTest."""
    client = client or KimiClient()
    user_prompt = _INSTRUCTIONS.format(
        scope=scope.value,
        protocol=protocol.strip(),
        data_summary=_format_data_summary(data_summary),
    )
    payload = client.chat_json(
        [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": user_prompt},
        ]
    )
    return ProposedTest(**payload)
