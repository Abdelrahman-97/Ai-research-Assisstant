"""Regression engines: logistic regression, ANCOVA, and Cox proportional hazards."""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd

from app.services import citations
from app.services.stat_engines.base import EngineError, fmt_p, get_col, pstr, refs_block, round4


def _encode_predictors(data: pd.DataFrame, predictors: list) -> pd.DataFrame:
    """Numeric predictors pass through; 2-level categoricals are encoded 0/1.
    Categoricals with 3+ levels raise a clear error (ask the user to encode them)."""
    out = data.copy()
    for c in predictors:
        s = out[c]
        num = pd.to_numeric(s, errors="coerce")
        if num.notna().sum() >= s.notna().sum():   # essentially numeric already
            out[c] = num
            continue
        levels = list(pd.Series(s.dropna().astype(str).unique()))
        if len(levels) == 2:
            out[c] = s.astype(str).map({levels[0]: 0, levels[1]: 1})
        else:
            raise EngineError(
                f"Predictor '{c}' is categorical with {len(levels)} levels; please encode it "
                "numerically (or use a 2-level version) before modelling."
            )
    return out


def logistic_regression(df: pd.DataFrame, params: dict, fig_dir: str | Path | None = None) -> dict:
    import statsmodels.api as sm

    outcome = params.get("outcome")
    predictors = params.get("predictors") or ([params["predictor"]] if params.get("predictor") else [])
    if not outcome or not predictors:
        raise EngineError("Logistic regression needs a binary 'outcome' and 'predictors'.")
    cols = [outcome] + list(predictors)
    for c in cols:
        get_col(df, c, "column")
    data = df[cols].copy()
    # coerce outcome to 0/1
    y_raw = data[outcome]
    levels = list(pd.Series(y_raw.dropna().unique()))
    if len(levels) != 2:
        raise EngineError(f"Logistic regression needs a binary outcome; '{outcome}' has "
                          f"{len(levels)} levels.")
    mapping = {levels[0]: 0, levels[1]: 1}
    data[outcome] = y_raw.map(mapping)
    data = _encode_predictors(data, list(predictors))
    data = data.dropna()
    if len(data) <= len(predictors) + 1:
        raise EngineError("Not enough complete rows for logistic regression.")
    X = sm.add_constant(data[list(predictors)])
    try:
        model = sm.Logit(data[outcome], X).fit(disp=0)
    except Exception as exc:  # noqa: BLE001 - separation etc.
        raise EngineError(f"Logistic model did not converge: {exc}") from exc

    ci = model.conf_int()
    coefs = []
    for name in X.columns:
        b = model.params[name]
        coefs.append({
            "term": "Intercept" if name == "const" else str(name),
            "beta": round4(b), "odds_ratio": round4(math.exp(b)),
            "or_ci_low": round4(math.exp(ci.loc[name, 0])),
            "or_ci_high": round4(math.exp(ci.loc[name, 1])),
            "p_value": float(model.pvalues[name]),
        })
    values = {
        "n": int(len(data)), "outcome": outcome, "positive_class": str(levels[1]),
        "predictors": list(predictors), "pseudo_r2": round4(model.prsquared),
        "llr_p_value": float(model.llr_pvalue), "coefficients": coefs,
    }
    md = [
        "## Logistic regression\n",
        f"We modelled the odds of **{outcome} = {levels[1]}** from "
        f"{', '.join('**' + str(p) + '**' for p in predictors)} (n = {len(data)}). "
        f"Model fit: McFadden pseudo-R² = {round4(model.prsquared)}, likelihood-ratio "
        f"{pstr(model.llr_pvalue)}.\n",
        "| Term | Odds ratio | 95% CI | B | p |",
        "|---|---|---|---|---|",
    ]
    for c in coefs:
        md.append(f"| {c['term']} | {c['odds_ratio']} | {c['or_ci_low']} to {c['or_ci_high']} "
                  f"| {c['beta']} | {fmt_p(c['p_value'])} |")
    md.append("\nAn odds ratio above 1 indicates higher odds of the outcome as the predictor "
              "increases; below 1, lower odds.")
    refs = citations.refs(["hosmer2013"])
    return {"key": "logistic_regression", "title": "Logistic regression",
            "values": values, "markdown": "\n".join(md) + refs_block(refs),
            "references": refs, "figure_path": None,
            "assumptions": ["Binary outcome", "Independent observations",
                            "Linearity of the logit for continuous predictors",
                            "No severe multicollinearity"]}


def ancova(df: pd.DataFrame, params: dict, fig_dir: str | Path | None = None) -> dict:
    import statsmodels.formula.api as smf
    from statsmodels.stats.anova import anova_lm

    outcome = params.get("outcome")
    group = params.get("group")
    covariates = params.get("covariates") or ([params["covariate"]] if params.get("covariate") else [])
    if not outcome or not group or not covariates:
        raise EngineError("ANCOVA needs 'outcome', 'group', and one or more 'covariates'.")
    cols = [outcome, group] + list(covariates)
    for c in cols:
        get_col(df, c, "column")
    data = df[cols].copy()
    data[outcome] = pd.to_numeric(data[outcome], errors="coerce")
    for cov in covariates:
        data[cov] = pd.to_numeric(data[cov], errors="coerce")
    data = data.dropna()
    if data[group].nunique() < 2:
        raise EngineError("ANCOVA needs at least 2 groups.")
    # safe names for the formula
    data = data.rename(columns={outcome: "_y", group: "_g"})
    cov_terms = " + ".join(f"Q('{c}')" for c in covariates)
    model = smf.ols(f"_y ~ C(_g) + {cov_terms}", data=data).fit()
    table = anova_lm(model, typ=2)
    ss_total = table["sum_sq"].sum()

    def row(term):
        r = table.loc[term]
        pe = float(r["sum_sq"] / (r["sum_sq"] + table.loc["Residual", "sum_sq"]))
        return {"F": round4(r["F"]), "df": int(r["df"]), "p_value": float(r["PR(>F)"]),
                "partial_eta_sq": round4(pe)}

    group_eff = row("C(_g)")
    cov_effects = {c: row(f"Q('{c}')") for c in covariates}
    adj = data.groupby("_g")["_y"].mean().round(4).to_dict()
    values = {
        "n": int(len(data)), "outcome": outcome, "group": group, "covariates": list(covariates),
        "group_effect": group_eff, "covariate_effects": cov_effects,
        "unadjusted_group_means": {str(k): round4(v) for k, v in adj.items()},
    }
    md = [
        "## ANCOVA (analysis of covariance)\n",
        f"We compared **{outcome}** across **{group}** while adjusting for "
        f"{', '.join('**' + str(c) + '**' for c in covariates)} (n = {len(data)}).\n",
        f"After adjustment, the effect of **{group}** was "
        + ("statistically significant" if group_eff["p_value"] < 0.05 else "not statistically significant")
        + f", **F({group_eff['df']}, {int(table.loc['Residual', 'df'])}) = {group_eff['F']}**, "
        f"{pstr(group_eff['p_value'])}, partial η² = {group_eff['partial_eta_sq']}.",
    ]
    for c, e in cov_effects.items():
        md.append(f"- Covariate **{c}**: F({e['df']}, {int(table.loc['Residual', 'df'])}) = "
                  f"{e['F']}, {pstr(e['p_value'])}.")
    refs = citations.refs(["fisher1925", "cohen1988"])
    return {"key": "ancova", "title": "ANCOVA", "values": values,
            "markdown": "\n".join(md) + refs_block(refs), "references": refs,
            "figure_path": None,
            "assumptions": ["Linearity between covariate and outcome", "Homogeneity of regression slopes",
                            "Normality of residuals", "Homogeneity of variance"]}


def cox_regression(df: pd.DataFrame, params: dict, fig_dir: str | Path | None = None) -> dict:
    from statsmodels.duration.hazard_regression import PHReg

    time = params.get("time")
    event = params.get("event")
    predictors = params.get("predictors") or ([params["predictor"]] if params.get("predictor") else [])
    if not time or not event or not predictors:
        raise EngineError("Cox regression needs 'time', 'event' (1=event/0=censored), and 'predictors'.")
    cols = [time, event] + list(predictors)
    for c in cols:
        get_col(df, c, "column")
    data = df[cols].copy()
    data[time] = pd.to_numeric(data[time], errors="coerce")
    data[event] = pd.to_numeric(data[event], errors="coerce")
    data = _encode_predictors(data, list(predictors))
    data = data.dropna()
    if len(data) <= len(predictors) + 1:
        raise EngineError("Not enough complete rows for Cox regression.")
    model = PHReg(data[time], data[list(predictors)], status=data[event]).fit()
    params_ = np.asarray(model.params)
    se = np.asarray(model.bse)
    pvals = np.asarray(model.pvalues)
    rows = []
    for i, name in enumerate(predictors):
        b = params_[i]
        rows.append({"term": str(name), "hr": round4(math.exp(b)),
                     "hr_ci_low": round4(math.exp(b - 1.96 * se[i])),
                     "hr_ci_high": round4(math.exp(b + 1.96 * se[i])),
                     "beta": round4(b), "p_value": float(pvals[i])})
    values = {"n": int(len(data)), "events": int(data[event].sum()),
              "time": time, "event": event, "coefficients": rows}
    md = [
        "## Cox proportional-hazards regression\n",
        f"We modelled the hazard of the event (**{event}**) over **{time}** from "
        f"{', '.join('**' + str(p) + '**' for p in predictors)} "
        f"(n = {len(data)}, events = {int(data[event].sum())}).\n",
        "| Predictor | Hazard ratio | 95% CI | B | p |",
        "|---|---|---|---|---|",
    ]
    for c in rows:
        md.append(f"| {c['term']} | {c['hr']} | {c['hr_ci_low']} to {c['hr_ci_high']} | "
                  f"{c['beta']} | {fmt_p(c['p_value'])} |")
    md.append("\nA hazard ratio above 1 indicates a higher event rate as the predictor increases; "
              "below 1, a lower (protective) rate.")
    refs = citations.refs(["cox1972"])
    return {"key": "cox_regression", "title": "Cox proportional-hazards regression",
            "values": values, "markdown": "\n".join(md) + refs_block(refs),
            "references": refs, "figure_path": None,
            "assumptions": ["Proportional hazards over time", "Independent observations",
                            "Correctly specified, log-linear predictors"]}
