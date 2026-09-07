"""Generalized-linear / specialized regression engines:
Poisson, negative-binomial, and ordinal (proportional-odds) logistic regression.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd

from app.services import citations
from app.services.stat_engines.base import EngineError, fmt_p, get_col, pstr, refs_block, round4
from app.services.stat_engines.regression_models import _encode_predictors


def _prep(df, outcome, predictors, *, integer_outcome=False):
    cols = [outcome] + list(predictors)
    for c in cols:
        get_col(df, c, "column")
    data = df[cols].copy()
    data[outcome] = pd.to_numeric(data[outcome], errors="coerce")
    data = _encode_predictors(data, list(predictors))
    data = data.dropna()
    if len(data) <= len(predictors) + 1:
        raise EngineError("Not enough complete rows for this model.")
    if integer_outcome and (data[outcome] < 0).any():
        raise EngineError("Count outcomes must be non-negative integers.")
    return data


def _count_report(title, key, ratio_name, outcome, predictors, data, model, extra_refs):
    ci = model.conf_int()
    rows = []
    for name in model.params.index:
        b = model.params[name]
        rows.append({"term": "Intercept" if name == "const" else str(name),
                     "beta": round4(b), "ratio": round4(math.exp(b)),
                     "ci_low": round4(math.exp(ci.loc[name, 0])),
                     "ci_high": round4(math.exp(ci.loc[name, 1])),
                     "p_value": float(model.pvalues[name])})
    values = {"n": int(len(data)), "outcome": outcome, "predictors": list(predictors),
              "coefficients": rows}
    md = [
        f"## {title}\n",
        f"We modelled counts of **{outcome}** from "
        f"{', '.join('**' + str(p) + '**' for p in predictors)} (n = {len(data)}).\n",
        f"| Term | {ratio_name} | 95% CI | B | p |",
        "|---|---|---|---|---|",
    ]
    for c in rows:
        md.append(f"| {c['term']} | {c['ratio']} | {c['ci_low']} to {c['ci_high']} | "
                  f"{c['beta']} | {fmt_p(c['p_value'])} |")
    md.append(f"\n{ratio_name} above 1 means a higher expected count as the predictor increases; "
              "below 1, a lower count.")
    refs = citations.refs(extra_refs)
    return {"key": key, "title": title, "values": values,
            "markdown": "\n".join(md) + refs_block(refs), "references": refs,
            "figure_path": None,
            "assumptions": ["Count outcome", "Independent observations"]}


def poisson_regression(df: pd.DataFrame, params: dict, fig_dir: str | Path | None = None) -> dict:
    import statsmodels.api as sm

    outcome = params.get("outcome")
    predictors = params.get("predictors") or ([params["predictor"]] if params.get("predictor") else [])
    if not outcome or not predictors:
        raise EngineError("Poisson regression needs a count 'outcome' and 'predictors'.")
    data = _prep(df, outcome, predictors, integer_outcome=True)
    X = sm.add_constant(data[list(predictors)])
    model = sm.GLM(data[outcome], X, family=sm.families.Poisson()).fit()
    res = _count_report("Poisson regression", "poisson_regression", "Rate ratio (IRR)",
                        outcome, predictors, data, model, ["mccullagh1989"])
    # dispersion warning
    disp = float(model.pearson_chi2 / model.df_resid) if model.df_resid else None
    res["values"]["dispersion"] = round4(disp)
    if disp and disp > 1.5:
        res["markdown"] += ("\n\n*Note:* the data appear over-dispersed (dispersion ≈ "
                            f"{round4(disp)} > 1); negative-binomial regression may fit better.")
    return res


def negative_binomial_regression(df: pd.DataFrame, params: dict, fig_dir: str | Path | None = None) -> dict:
    import statsmodels.api as sm

    outcome = params.get("outcome")
    predictors = params.get("predictors") or ([params["predictor"]] if params.get("predictor") else [])
    if not outcome or not predictors:
        raise EngineError("Negative-binomial regression needs a count 'outcome' and 'predictors'.")
    data = _prep(df, outcome, predictors, integer_outcome=True)
    X = sm.add_constant(data[list(predictors)])
    model = sm.GLM(data[outcome], X, family=sm.families.NegativeBinomial()).fit()
    return _count_report("Negative-binomial regression", "negative_binomial_regression",
                         "Rate ratio (IRR)", outcome, predictors, data, model,
                         ["hilbe2011", "mccullagh1989"])


def ordinal_logistic_regression(df: pd.DataFrame, params: dict, fig_dir: str | Path | None = None) -> dict:
    from statsmodels.miscmodels.ordinal_model import OrderedModel

    outcome = params.get("outcome")
    predictors = params.get("predictors") or ([params["predictor"]] if params.get("predictor") else [])
    if not outcome or not predictors:
        raise EngineError("Ordinal logistic regression needs an ordinal 'outcome' and 'predictors'.")
    cols = [outcome] + list(predictors)
    for c in cols:
        get_col(df, c, "column")
    data = df[cols].copy()
    data = _encode_predictors(data, list(predictors))
    # ordered outcome: keep numeric ordering if numeric, else category order of appearance
    y = data[outcome]
    y_num = pd.to_numeric(y, errors="coerce")
    if y_num.notna().sum() >= y.notna().sum():
        data[outcome] = y_num
    data = data.dropna()
    n_levels = data[outcome].nunique()
    if n_levels < 3:
        raise EngineError("Ordinal regression needs an outcome with at least 3 ordered levels "
                          "(use logistic regression for a binary outcome).")
    yc = pd.Categorical(data[outcome], ordered=True)
    try:
        model = OrderedModel(yc.codes, data[list(predictors)], distr="logit").fit(method="bfgs", disp=0)
    except Exception as exc:  # noqa: BLE001
        raise EngineError(f"Ordinal model did not converge: {exc}") from exc
    ci = model.conf_int()
    rows = []
    for name in list(predictors):
        if name not in model.params.index:
            continue
        b = model.params[name]
        rows.append({"term": str(name), "odds_ratio": round4(math.exp(b)),
                     "or_ci_low": round4(math.exp(ci.loc[name, 0])),
                     "or_ci_high": round4(math.exp(ci.loc[name, 1])),
                     "beta": round4(b), "p_value": float(model.pvalues[name])})
    values = {"n": int(len(data)), "outcome": outcome, "n_levels": int(n_levels),
              "predictors": list(predictors), "coefficients": rows}
    md = [
        "## Ordinal logistic regression (proportional odds)\n",
        f"We modelled the ordered outcome **{outcome}** ({n_levels} levels) from "
        f"{', '.join('**' + str(p) + '**' for p in predictors)} (n = {len(data)}).\n",
        "| Predictor | Odds ratio | 95% CI | B | p |",
        "|---|---|---|---|---|",
    ]
    for c in rows:
        md.append(f"| {c['term']} | {c['odds_ratio']} | {c['or_ci_low']} to {c['or_ci_high']} | "
                  f"{c['beta']} | {fmt_p(c['p_value'])} |")
    md.append("\nEach odds ratio is the change in odds of being in a higher outcome category, "
              "assumed constant across the thresholds (proportional-odds assumption).")
    refs = citations.refs(["mccullagh1980"])
    return {"key": "ordinal_logistic_regression", "title": "Ordinal logistic regression",
            "values": values, "markdown": "\n".join(md) + refs_block(refs),
            "references": refs, "figure_path": None,
            "assumptions": ["Ordered categorical outcome", "Proportional odds",
                            "Independent observations"]}
