"""Shared helpers for the statistical-test engines.

Each engine is an audited, deterministic function: it takes a pandas DataFrame
plus a small `params` dict (which columns to use), computes the test with
scipy/statsmodels, and returns a standard result dict:

    {
      "key":        engine id,
      "title":      human-readable test name,
      "values":     structured numbers (JSON-safe),
      "markdown":   an explained, cited factual report (deterministic),
      "references": curated citation strings,
      "figure_path": path to a PNG (if fig_dir was given), else None,
      "assumptions": list of plain-language assumption notes,
    }

No LLM is involved in the numbers — only the formulas here. The AI later writes
the Results narrative from `markdown`/`values`; it can never change a value.
"""

from __future__ import annotations

import math

import pandas as pd

TEAL = "#0a6b63"
TEAL_SOFT = "#7fb5ad"


class EngineError(Exception):
    """Raised when the data/params can't support the requested test."""


def fmt_p(p) -> str:
    if p is None or (isinstance(p, float) and math.isnan(p)):
        return "—"
    return "< .001" if p < 0.001 else f"{p:.3f}"


def pstr(p) -> str:
    if p is None or (isinstance(p, float) and math.isnan(p)):
        return "p = —"
    return "p < .001" if p < 0.001 else f"p = {p:.3f}"


def round4(x):
    try:
        f = float(x)
        return None if math.isnan(f) or math.isinf(f) else round(f, 4)
    except (TypeError, ValueError):
        return None


def get_col(df: pd.DataFrame, name, what: str = "column") -> pd.Series:
    if not name or name not in df.columns:
        raise EngineError(
            f"{what.capitalize()} '{name}' was not found in the data. "
            f"Available columns: {', '.join(map(str, df.columns))}."
        )
    return df[name]


def numeric(series: pd.Series, name: str = "") -> pd.Series:
    s = pd.to_numeric(series, errors="coerce").dropna()
    if len(s) == 0:
        raise EngineError(f"Column '{name or series.name}' has no usable numeric values.")
    return s


def describe(series: pd.Series) -> dict:
    """Descriptive summary of a numeric column."""
    s = pd.to_numeric(series, errors="coerce").dropna()
    n = int(len(s))
    return {
        "n": n,
        "mean": round4(s.mean()) if n else None,
        "sd": round4(s.std(ddof=1)) if n > 1 else None,
        "min": round4(s.min()) if n else None,
        "median": round4(s.median()) if n else None,
        "max": round4(s.max()) if n else None,
    }


def refs_block(refs: list[str]) -> str:
    if not refs:
        return ""
    lines = "\n".join(f"{i + 1}. {r}" for i, r in enumerate(refs))
    return f"\n\n## References\n\n{lines}\n"
