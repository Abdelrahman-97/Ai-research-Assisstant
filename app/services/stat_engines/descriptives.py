"""Descriptive-statistics engine: summarise variables (optionally by group)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from app.services.stat_engines.base import EngineError, describe, get_col, refs_block, round4


def descriptive_summary(df: pd.DataFrame, params: dict, fig_dir: str | Path | None = None) -> dict:
    variables = params.get("variables") or ([params["variable"]] if params.get("variable") else [])
    group = params.get("group")
    if not variables:
        # default: every numeric column
        variables = [c for c in df.columns if pd.api.types.is_numeric_dtype(pd.to_numeric(df[c], errors="coerce"))]
    if not variables:
        raise EngineError("No numeric variables to summarise.")

    rows = []
    if group:
        g = get_col(df, group, "grouping").astype(str)
        for var in variables:
            get_col(df, var, "variable")
            for lv in dict.fromkeys(g):
                s = df.loc[g == lv, var]
                d = describe(s)
                rows.append({"variable": str(var), "group": lv, **d})
    else:
        for var in variables:
            d = describe(get_col(df, var, "variable"))
            rows.append({"variable": str(var), **d})

    header = "| Variable | " + ("Group | " if group else "") + "n | Mean | SD | Min | Median | Max |"
    sep = "|---|" + ("---|" if group else "") + "---|---|---|---|---|---|"
    md = ["## Descriptive statistics\n",
          f"Summary of {len(variables)} variable(s)"
          + (f" by **{group}**" if group else "") + ".\n", header, sep]
    for r in rows:
        cells = [r["variable"]] + ([r["group"]] if group else []) + [
            str(r["n"]), str(r["mean"]), str(r["sd"]), str(r["min"]), str(r["median"]), str(r["max"])]
        md.append("| " + " | ".join(cells) + " |")

    values = {"group": group, "rows": rows}
    return {"key": "descriptive_summary", "title": "Descriptive statistics",
            "values": values, "markdown": "\n".join(md) + refs_block([]),
            "references": [], "figure_path": None,
            "assumptions": []}
