"""Repeated-measures ANOVA (within-subjects), via statsmodels AnovaRM.

Expects long-format data: one row per (subject, condition) with the outcome value.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from scipy import stats

from app.services import citations
from app.services.stat_engines.base import EngineError, get_col, pstr, refs_block, round4


def repeated_measures_anova(df: pd.DataFrame, params: dict, fig_dir: str | Path | None = None) -> dict:
    from statsmodels.stats.anova import AnovaRM

    subject = params.get("subject")
    within = params.get("within") or params.get("condition")
    outcome = params.get("outcome")
    if not subject or not within or not outcome:
        raise EngineError(
            "Repeated-measures ANOVA needs 'subject', 'within' (the condition/time "
            "column), and 'outcome' — in long format (one row per subject × condition)."
        )
    for c in (subject, within, outcome):
        get_col(df, c, "column")
    data = df[[subject, within, outcome]].copy()
    data[outcome] = pd.to_numeric(data[outcome], errors="coerce")
    data = data.dropna()
    if data[within].nunique() < 2:
        raise EngineError("The within-subject factor needs at least 2 levels.")
    try:
        res = AnovaRM(data, depvar=outcome, subject=subject, within=[within]).fit()
    except Exception as exc:  # noqa: BLE001 - unbalanced design etc.
        raise EngineError(
            f"Repeated-measures ANOVA could not be fit ({exc}). Each subject must have "
            "exactly one value per condition (a balanced design)."
        ) from exc
    tbl = res.anova_table
    row = tbl.loc[within]
    f = float(row["F Value"])
    df1 = float(row["Num DF"])
    df2 = float(row["Den DF"])
    p = float(row["Pr > F"])
    means = data.groupby(within)[outcome].mean().round(4).to_dict()
    values = {
        "within_factor": within, "outcome": outcome,
        "n_subjects": int(data[subject].nunique()), "levels": list(map(str, means.keys())),
        "f": round4(f), "df_num": df1, "df_den": df2, "p_value": p,
        "condition_means": {str(k): round4(v) for k, v in means.items()},
    }
    md = [
        "## Repeated-measures ANOVA\n",
        f"We compared **{outcome}** across levels of **{within}** within the same "
        f"{data[subject].nunique()} subjects.\n",
        f"There was "
        + ("a statistically significant" if p < 0.05 else "no statistically significant")
        + f" within-subjects effect of **{within}**, **F({df1:.0f}, {df2:.0f}) = {round4(f)}**, "
        f"{pstr(p)}.",
    ]
    refs = citations.refs(["fisher1925"])
    return {"key": "repeated_measures_anova", "title": "Repeated-measures ANOVA",
            "values": values, "markdown": "\n".join(md) + refs_block(refs),
            "references": refs, "figure_path": None,
            "assumptions": ["Within-subjects design (balanced)", "Sphericity",
                            "Approximately normal residuals"]}


def friedman(df: pd.DataFrame, params: dict, fig_dir: str | Path | None = None) -> dict:
    """Friedman test — non-parametric repeated measures (long format)."""
    subject = params.get("subject")
    within = params.get("within") or params.get("condition")
    outcome = params.get("outcome")
    if not subject or not within or not outcome:
        raise EngineError("Friedman test needs 'subject', 'within' (condition), and 'outcome' "
                          "in long format (one row per subject × condition).")
    for c in (subject, within, outcome):
        get_col(df, c, "column")
    data = df[[subject, within, outcome]].copy()
    data[outcome] = pd.to_numeric(data[outcome], errors="coerce")
    data = data.dropna()
    wide = data.pivot_table(index=subject, columns=within, values=outcome).dropna()
    if wide.shape[1] < 3:
        raise EngineError("Friedman test needs at least 3 conditions.")
    if wide.shape[0] < 2:
        raise EngineError("Not enough complete subjects (each must have all conditions).")
    cols = [wide[c].values for c in wide.columns]
    chi2, p = stats.friedmanchisquare(*cols)
    k = wide.shape[1]
    n = wide.shape[0]
    kendall_w = chi2 / (n * (k - 1)) if (n * (k - 1)) else None   # effect size
    medians = {str(c): round4(wide[c].median()) for c in wide.columns}
    values = {
        "within_factor": within, "outcome": outcome, "n_subjects": int(n),
        "levels": list(map(str, wide.columns)), "chi2": round4(chi2), "df": k - 1,
        "p_value": float(p), "kendalls_w": round4(kendall_w), "condition_medians": medians,
    }
    md = [
        "## Friedman test (non-parametric repeated measures)\n",
        f"We compared **{outcome}** across {k} conditions of **{within}** within "
        f"{n} subjects (ranks; no normality assumed).\n",
        f"There was "
        + ("a statistically significant" if p < 0.05 else "no statistically significant")
        + f" difference, **χ²({k - 1}) = {round4(chi2)}**, {pstr(p)}, "
        f"Kendall's W = **{round4(kendall_w)}**.",
    ]
    refs = citations.refs(["friedman1937"])
    return {"key": "friedman", "title": "Friedman test", "values": values,
            "markdown": "\n".join(md) + refs_block(refs), "references": refs,
            "figure_path": None,
            "assumptions": ["Within-subjects design", "Ordinal or continuous outcome"]}
