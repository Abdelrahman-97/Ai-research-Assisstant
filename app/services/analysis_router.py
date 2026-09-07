"""Analysis router (engine-first planning).

Instead of asking the model to WRITE analysis code, we ask it to CHOOSE from the
audited engine library: which engine(s) to run and which columns map to each
engine's parameters. The choice is a *proposal* — the researcher approves it at
the human checkpoint, and only audited engine code ever runs.

If the model can't cover the request with the available engines, it sets
`fallback` so the pipeline uses the AI-generated-script path instead.
"""

from __future__ import annotations

import json

from app.models.schemas import DataSummary, EnginePlan, EnginePlanItem, Scope
from app.services.llm_client import LLMClient
from app.services.stat_engines import registry

_SYSTEM = (
    "You are a biostatistics assistant. You do NOT write code. You choose the "
    "correct audited statistical engine(s) for the researcher's data and protocol "
    "and map the data columns to each engine's parameters. You propose; the "
    "researcher always confirms. Use only the engines and columns provided."
)


def _catalogue_text() -> str:
    lines = []
    for e in registry.catalogue():
        params = ", ".join(f"{k} ({v})" for k, v in e["params"].items())
        lines.append(f"- {e['key']}: {e['when']} Params: {params}")
    return "\n".join(lines)


def _columns_text(summary: DataSummary) -> str:
    lines = [f"rows={summary.n_rows}, cols={summary.n_cols}"]
    for c in summary.columns:
        lines.append(f"- {c.name} | {c.dtype} | non_null={c.non_null} | "
                     f"unique={c.n_unique} | e.g. {', '.join(c.sample_values)}")
    return "\n".join(lines)


_INSTRUCTIONS = """\
Choose the audited engine(s) that answer the research question. Return ONLY a JSON
object (no prose, no code fence) with exactly these keys:
{{
  "analyses": [
    {{
      "engine": "one engine key from the list below",
      "params": {{ "paramName": "an exact column name from the data" }},
      "reasoning": "why this engine fits, 1-3 sentences"
    }}
  ],
  "fallback": false,
  "note": "if fallback is true, briefly say what analysis is needed that no engine covers"
}}

Rules:
- Use ONLY engine keys from the catalogue and ONLY column names from the data.
- Map every parameter each chosen engine needs (see its Params).
- You may choose several engines (e.g. descriptives + a comparison).
- If the required analysis is not covered by any engine, return "analyses": [] and
  "fallback": true with a short "note".

Available engines:
{catalogue}

Study scope: {scope}
Research protocol / methods:
---
{protocol}
---
Data (columns with dtype, non-null counts, sample values):
---
{columns}
---
"""


def _valid_columns(summary: DataSummary) -> set[str]:
    return {c.name for c in summary.columns}


def _validate_item(raw: dict, valid_cols: set[str]) -> EnginePlanItem | None:
    key = (raw or {}).get("engine")
    spec = registry.REGISTRY.get(key)
    if not spec:
        return None
    params = raw.get("params") or {}
    if not isinstance(params, dict):
        return None
    # every column-valued param must reference a real column (lists allowed for
    # predictors/variables). Non-column params (e.g. method) pass through.
    for k, v in params.items():
        if isinstance(v, str) and k in ("outcome", "group", "pre", "post", "var1", "var2",
                                        "predictor") and v not in valid_cols:
            return None
        if isinstance(v, list):
            bad = [c for c in v if c not in valid_cols]
            if bad:
                params[k] = [c for c in v if c in valid_cols]
                if not params[k]:
                    return None
    return EnginePlanItem(engine=key, label=spec["title"], params=params,
                          reasoning=str(raw.get("reasoning") or ""))


def propose(
    *,
    protocol: str,
    data_summary: DataSummary,
    scope: Scope,
    client: LLMClient | None = None,
) -> EnginePlan:
    """Ask the model to pick engines + column mappings. Returns an EnginePlan.

    On any failure (LLM error, unparseable output, no valid engine) the plan is
    returned with fallback_to_script=True so the pipeline uses the script path.
    """
    client = client or LLMClient()
    prompt = _INSTRUCTIONS.format(
        catalogue=_catalogue_text(),
        scope=scope.value,
        protocol=(protocol or "").strip(),
        columns=_columns_text(data_summary),
    )
    try:
        payload = client.chat_json(
            [{"role": "system", "content": _SYSTEM},
             {"role": "user", "content": prompt}]
        )
    except Exception:  # noqa: BLE001 - any router failure -> script fallback
        return EnginePlan(items=[], fallback_to_script=True,
                          note="Automatic engine selection was unavailable.")

    if payload.get("fallback"):
        return EnginePlan(items=[], fallback_to_script=True, note=str(payload.get("note") or ""))

    valid_cols = _valid_columns(data_summary)
    items: list[EnginePlanItem] = []
    for raw in (payload.get("analyses") or []):
        item = _validate_item(raw, valid_cols)
        if item:
            items.append(item)
    if not items:
        return EnginePlan(items=[], fallback_to_script=True,
                          note=str(payload.get("note") or "No suitable engine was found."))
    return EnginePlan(items=items, fallback_to_script=False, note=str(payload.get("note") or ""))
