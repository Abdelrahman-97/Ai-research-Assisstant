"""Agreement / reliability engines: Cohen's kappa, ICC, and Bland-Altman."""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd

from app.services import citations
from app.services.stat_engines import plots
from app.services.stat_engines.base import EngineError, get_col, pstr, refs_block, round4


def _kappa_word(k):
    if k is None:
        return "—"
    return ("poor" if k < 0 else "slight" if k < 0.20 else "fair" if k < 0.40 else
            "moderate" if k < 0.60 else "substantial" if k < 0.80 else "almost perfect")


def cohens_kappa(df: pd.DataFrame, params: dict, fig_dir: str | Path | None = None) -> dict:
    r1, r2 = params.get("rater1") or params.get("var1"), params.get("rater2") or params.get("var2")
    a = get_col(df, r1, "first rater").astype(str)
    b = get_col(df, r2, "second rater").astype(str)
    sub = pd.DataFrame({"a": a, "b": b}).replace({"nan": np.nan}).dropna()
    if len(sub) < 2:
        raise EngineError("Cohen's kappa needs at least 2 complete rated pairs.")
    cats = sorted(set(sub["a"]) | set(sub["b"]))
    table = pd.crosstab(sub["a"], sub["b"]).reindex(index=cats, columns=cats, fill_value=0)
    n = table.values.sum()
    po = np.trace(table.values) / n
    row_marg = table.sum(axis=1).values / n
    col_marg = table.sum(axis=0).values / n
    pe = float(np.sum(row_marg * col_marg))
    kappa = (po - pe) / (1 - pe) if (1 - pe) else None
    # approximate SE (Cohen 1960) for a 95% CI
    ci = None
    if kappa is not None and (1 - pe) > 0:
        se = math.sqrt(po * (1 - po) / (n * (1 - pe) ** 2))
        ci = (kappa - 1.96 * se, kappa + 1.96 * se)
    values = {
        "n": int(n), "categories": cats, "observed_agreement": round4(po),
        "expected_agreement": round4(pe), "kappa": round4(kappa),
        "ci95": [round4(ci[0]), round4(ci[1])] if ci else None,
        "interpretation": _kappa_word(kappa),
    }
    md = [
        "## Cohen's kappa (inter-rater agreement)\n",
        f"We assessed agreement between **{r1}** and **{r2}** across {int(n)} cases "
        f"and {len(cats)} categories.\n",
        f"Observed agreement was {round(po * 100, 1)}% (chance-expected {round(pe * 100, 1)}%). "
        f"**Cohen's κ = {round4(kappa)}**"
        + (f" (95% CI {round4(ci[0])} to {round4(ci[1])})" if ci else "")
        + f", indicating **{_kappa_word(kappa)}** agreement (Landis & Koch).",
    ]
    refs = citations.refs(["cohen1960"])
    return {"key": "cohens_kappa", "title": "Cohen's kappa", "values": values,
            "markdown": "\n".join(md) + refs_block(refs), "references": refs,
            "figure_path": None, "assumptions": ["Two raters", "Independent, categorical ratings"]}


def icc(df: pd.DataFrame, params: dict, fig_dir: str | Path | None = None) -> dict:
    """Intraclass correlation, two-way random effects, single rater — ICC(2,1)."""
    raters = params.get("raters") or params.get("columns") or []
    if len(raters) < 2:
        raise EngineError("ICC needs at least 2 rater/measurement columns.")
    for c in raters:
        get_col(df, c, "rater column")
    data = df[list(raters)].apply(pd.to_numeric, errors="coerce").dropna()
    n, k = data.shape
    if n < 2:
        raise EngineError("ICC needs at least 2 complete subjects.")
    grand = data.values.mean()
    ss_total = float(((data.values - grand) ** 2).sum())
    ss_rows = float((k * ((data.mean(axis=1) - grand) ** 2)).sum())          # between subjects
    ss_cols = float((n * ((data.mean(axis=0) - grand) ** 2)).sum())          # between raters
    ss_err = ss_total - ss_rows - ss_cols
    df_rows, df_cols, df_err = n - 1, k - 1, (n - 1) * (k - 1)
    msr = ss_rows / df_rows
    msc = ss_cols / df_cols if df_cols else float("nan")
    mse = ss_err / df_err if df_err else float("nan")
    denom = msr + (k - 1) * mse + k * (msc - mse) / n
    icc21 = (msr - mse) / denom if denom else None
    values = {
        "n_subjects": int(n), "n_raters": int(k), "type": "ICC(2,1) two-way random, single measures",
        "icc": round4(icc21), "ms_between_subjects": round4(msr),
        "ms_between_raters": round4(msc), "ms_error": round4(mse),
    }
    q = ("poor" if (icc21 or 0) < 0.5 else "moderate" if icc21 < 0.75 else
         "good" if icc21 < 0.9 else "excellent")
    md = [
        "## Intraclass correlation coefficient (ICC)\n",
        f"We assessed the reliability of {k} raters/measurements across {n} subjects "
        "using a two-way random-effects model, single measures — ICC(2,1).\n",
        f"**ICC = {round4(icc21)}**, indicating **{q}** reliability (Koo & Li guidance: "
        "< 0.5 poor, 0.5–0.75 moderate, 0.75–0.9 good, > 0.9 excellent).",
    ]
    refs = citations.refs(["shrout1979"])
    return {"key": "icc", "title": "Intraclass correlation (ICC)", "values": values,
            "markdown": "\n".join(md) + refs_block(refs), "references": refs,
            "figure_path": None,
            "assumptions": ["Subjects are a random sample", "Raters are a random sample",
                            "Approximately normal measurements"]}


def bland_altman(df: pd.DataFrame, params: dict, fig_dir: str | Path | None = None) -> dict:
    m1, m2 = params.get("method1") or params.get("var1"), params.get("method2") or params.get("var2")
    x = pd.to_numeric(get_col(df, m1, "first method"), errors="coerce")
    y = pd.to_numeric(get_col(df, m2, "second method"), errors="coerce")
    sub = pd.DataFrame({"x": x, "y": y}).dropna()
    if len(sub) < 2:
        raise EngineError("Bland-Altman needs at least 2 complete paired measurements.")
    diffs = (sub["x"] - sub["y"])
    means = (sub["x"] + sub["y"]) / 2
    bias = float(diffs.mean())
    sd = float(diffs.std(ddof=1))
    loa_low, loa_high = bias - 1.96 * sd, bias + 1.96 * sd
    se_bias = sd / math.sqrt(len(sub))
    values = {
        "n": int(len(sub)), "bias": round4(bias), "sd_of_differences": round4(sd),
        "loa_lower": round4(loa_low), "loa_upper": round4(loa_high),
        "bias_ci95": [round4(bias - 1.96 * se_bias), round4(bias + 1.96 * se_bias)],
    }
    md = [
        "## Bland-Altman agreement analysis\n",
        f"We assessed agreement between **{m1}** and **{m2}** across {len(sub)} paired "
        "measurements.\n",
        f"The mean difference (bias) was **{round4(bias)}** (95% CI "
        f"{values['bias_ci95'][0]} to {values['bias_ci95'][1]}), with 95% limits of agreement "
        f"from **{round4(loa_low)}** to **{round4(loa_high)}**. "
        "Most differences should fall within these limits; whether that range is acceptable "
        "is a clinical judgement. See the Bland-Altman plot.",
    ]
    refs = citations.refs(["bland1986"])
    fig = None
    if fig_dir:
        fig = plots.bland_altman(means.tolist(), diffs.tolist(), bias=bias,
                                 loa_low=loa_low, loa_high=loa_high,
                                 path=Path(fig_dir) / "bland_altman.png")
    return {"key": "bland_altman", "title": "Bland-Altman agreement", "values": values,
            "markdown": "\n".join(md) + refs_block(refs), "references": refs,
            "figure_path": fig,
            "assumptions": ["Paired measurements of the same quantity",
                            "Differences approximately normal and constant across the range"]}
