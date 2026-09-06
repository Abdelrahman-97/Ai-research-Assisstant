"""Data preview + descriptive statistics for an uploaded dataset.

Powers the "review your data before you pay" step: a peek at the first rows plus a
per-column descriptive summary (means, SDs, ranges, missingness for numeric
columns; counts and top categories for categorical ones). Read-only — it never
changes the data or runs the paid analysis.
"""

from __future__ import annotations

import math
from pathlib import Path

import pandas as pd

from app.services.integrity_checker import read_dataframe

_PREVIEW_ROWS = 15
_MAX_COLS = 60


def _num(x) -> float | None:
    try:
        f = float(x)
        return None if math.isnan(f) or math.isinf(f) else round(f, 4)
    except (TypeError, ValueError):
        return None


def describe_dataframe(df: pd.DataFrame) -> dict:
    """Return preview rows + per-column descriptives as JSON-safe dicts."""
    df = df.iloc[:, :_MAX_COLS]
    n = int(len(df))
    columns: list[dict] = []

    for name in df.columns:
        s = df[name]
        non_null = int(s.notna().sum())
        col: dict = {
            "name": str(name),
            "dtype": str(s.dtype),
            "count": non_null,
            "missing": int(n - non_null),
        }
        if pd.api.types.is_numeric_dtype(s):
            d = s.dropna()
            col["kind"] = "numeric"
            col.update(
                mean=_num(d.mean()),
                sd=_num(d.std()),
                min=_num(d.min()),
                q1=_num(d.quantile(0.25)),
                median=_num(d.median()),
                q3=_num(d.quantile(0.75)),
                max=_num(d.max()),
            )
        else:
            col["kind"] = "categorical"
            col["n_unique"] = int(s.nunique(dropna=True))
            vc = s.dropna().astype(str).value_counts().head(5)
            col["top"] = [{"value": k, "count": int(v)} for k, v in vc.items()]
        columns.append(col)

    head = df.head(_PREVIEW_ROWS).fillna("").astype(str)
    rows = head.to_dict(orient="records")
    return {
        "n_rows": n,
        "n_cols": int(df.shape[1]),
        "preview_columns": [str(c) for c in df.columns],
        "rows": rows,
        "columns": columns,
    }


def preview_file(path: str | Path) -> dict:
    """Load a data file and return its preview + descriptives."""
    return describe_dataframe(read_dataframe(path))
