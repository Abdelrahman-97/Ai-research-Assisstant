"""Categorical engines for 2×2 designs: Fisher's exact and McNemar's test."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

from app.services import citations
from app.services.stat_engines.base import EngineError, get_col, pstr, refs_block, round4


def _two_by_two(df, v1, v2):
    a = get_col(df, v1, "first variable").astype(str)
    b = get_col(df, v2, "second variable").astype(str)
    sub = pd.DataFrame({"a": a, "b": b}).replace({"nan": np.nan}).dropna()
    table = pd.crosstab(sub["a"], sub["b"])
    return sub, table


def fishers_exact(df: pd.DataFrame, params: dict, fig_dir: str | Path | None = None) -> dict:
    v1, v2 = params.get("var1"), params.get("var2")
    sub, table = _two_by_two(df, v1, v2)
    if table.shape != (2, 2):
        raise EngineError(f"Fisher's exact test needs a 2×2 table; got {table.shape[0]}×{table.shape[1]}. "
                          "Use chi-square for larger tables.")
    odds, p = stats.fisher_exact(table.values)
    n = int(table.values.sum())
    values = {
        "table": {str(i): {str(c): int(table.loc[i, c]) for c in table.columns} for i in table.index},
        "odds_ratio": round4(odds), "p_value": float(p), "n": n,
    }
    md = [
        "## Fisher's exact test\n",
        f"We tested the association between **{v1}** and **{v2}** in a 2×2 table "
        f"(n = {n}); Fisher's exact test is appropriate for small samples.\n",
        f"The association was "
        + ("statistically significant" if p < 0.05 else "not statistically significant")
        + f", odds ratio = **{round4(odds)}**, {pstr(p)}.",
    ]
    refs = citations.refs(["fisher1922"])
    return {"key": "fishers_exact", "title": "Fisher's exact test", "values": values,
            "markdown": "\n".join(md) + refs_block(refs), "references": refs,
            "figure_path": None, "assumptions": ["Independent observations", "Fixed 2×2 design"]}


def mcnemar(df: pd.DataFrame, params: dict, fig_dir: str | Path | None = None) -> dict:
    """McNemar's test for paired binary data (e.g. before/after on the same subjects)."""
    from statsmodels.stats.contingency_tables import mcnemar as sm_mcnemar

    v1 = params.get("var1") or params.get("before")
    v2 = params.get("var2") or params.get("after")
    sub, table = _two_by_two(df, v1, v2)
    if table.shape != (2, 2):
        raise EngineError("McNemar's test needs two paired binary variables (a 2×2 table).")
    res = sm_mcnemar(table.values, exact=True)
    b = int(table.values[0, 1])
    c = int(table.values[1, 0])
    values = {
        "table": {str(i): {str(cc): int(table.loc[i, cc]) for cc in table.columns} for i in table.index},
        "discordant_b": b, "discordant_c": c,
        "statistic": round4(res.statistic), "p_value": float(res.pvalue), "n": int(table.values.sum()),
    }
    md = [
        "## McNemar's test (paired proportions)\n",
        f"We compared paired binary measurements **{v1}** and **{v2}** on the same subjects "
        f"(discordant pairs: {b} and {c}).\n",
        f"The change in proportions was "
        + ("statistically significant" if res.pvalue < 0.05 else "not statistically significant")
        + f", {pstr(res.pvalue)}.",
    ]
    refs = citations.refs(["mcnemar1947"])
    return {"key": "mcnemar", "title": "McNemar's test", "values": values,
            "markdown": "\n".join(md) + refs_block(refs), "references": refs,
            "figure_path": None,
            "assumptions": ["Paired binary observations", "Same subjects measured twice"]}
