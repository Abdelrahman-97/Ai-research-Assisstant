"""Association engines: correlation, chi-square, and linear regression."""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

from app.services import citations
from app.services.stat_engines import plots
from app.services.stat_engines.base import (
    EngineError, fmt_p, get_col, pstr, refs_block, round4,
)


def correlation(df: pd.DataFrame, params: dict, fig_dir: str | Path | None = None) -> dict:
    v1, v2 = params.get("var1"), params.get("var2")
    method = (params.get("method") or "pearson").lower()
    x = pd.to_numeric(get_col(df, v1, "first variable"), errors="coerce")
    y = pd.to_numeric(get_col(df, v2, "second variable"), errors="coerce")
    sub = pd.DataFrame({"x": x, "y": y}).dropna()
    n = len(sub)
    if n < 3:
        raise EngineError("Correlation needs at least 3 complete pairs.")
    if method == "spearman":
        r, p = stats.spearmanr(sub["x"], sub["y"])
        ref_keys = ["spearman1904"]
        label = "Spearman's rank correlation (ρ)"
    else:
        method = "pearson"
        r, p = stats.pearsonr(sub["x"], sub["y"])
        ref_keys = ["pearson1895", "fisher1921"]
        label = "Pearson correlation (r)"
    # Fisher z 95% CI (valid for Pearson; a reasonable approximation for Spearman)
    ci = None
    if abs(r) < 1 and n > 3:
        z = 0.5 * math.log((1 + r) / (1 - r))
        se = 1 / math.sqrt(n - 3)
        lo, hi = z - 1.96 * se, z + 1.96 * se
        ci = (math.tanh(lo), math.tanh(hi))
    values = {
        "method": method, "n": n, "r": round4(r), "p_value": float(p),
        "ci95": [round4(ci[0]), round4(ci[1])] if ci else None, "r_squared": round4(r ** 2),
    }
    strength = _r_word(r)
    md = [
        f"## {label}\n",
        f"We examined the association between **{v1}** and **{v2}** (n = {n}).\n",
        f"The correlation was **{round4(r)}**"
        + (f" (95% CI {round4(ci[0])} to {round4(ci[1])})" if ci else "")
        + f", {pstr(p)} — a {strength} "
        + ("positive" if r >= 0 else "negative") + " association"
        + (f"; it explained {round(r ** 2 * 100, 1)}% of the variance (r² = {round4(r ** 2)})."
           if method == "pearson" else "."),
    ]
    refs = citations.refs(ref_keys)
    fig = None
    if fig_dir:
        fig = plots.scatter_fit(sub["x"].tolist(), sub["y"].tolist(),
                                xlabel=str(v1), ylabel=str(v2), path=Path(fig_dir) / "scatter.png")
    return {"key": "correlation", "title": label, "values": values,
            "markdown": "\n".join(md) + refs_block(refs), "references": refs,
            "figure_path": fig,
            "assumptions": (["Linear relationship", "Approximately bivariate normal"]
                            if method == "pearson" else ["Monotonic relationship"])}


def chi_square(df: pd.DataFrame, params: dict, fig_dir: str | Path | None = None) -> dict:
    v1, v2 = params.get("var1"), params.get("var2")
    a = get_col(df, v1, "first variable").astype(str)
    b = get_col(df, v2, "second variable").astype(str)
    sub = pd.DataFrame({"a": a, "b": b}).replace({"nan": np.nan}).dropna()
    table = pd.crosstab(sub["a"], sub["b"])
    if table.shape[0] < 2 or table.shape[1] < 2:
        raise EngineError("Chi-square needs at least a 2×2 table (two categories in each variable).")
    chi2, p, dof, expected = stats.chi2_contingency(table)
    n = int(table.values.sum())
    k = min(table.shape) - 1
    cramers_v = math.sqrt(chi2 / (n * k)) if (n * k) else None
    min_expected = float(expected.min())
    values = {
        "table": {str(i): {str(c): int(table.loc[i, c]) for c in table.columns} for i in table.index},
        "chi2": round4(chi2), "df": int(dof), "p_value": float(p),
        "cramers_v": round4(cramers_v), "n": n, "min_expected": round4(min_expected),
    }
    md = [
        "## Chi-square test of independence\n",
        f"We tested the association between **{v1}** and **{v2}** "
        f"({table.shape[0]}×{table.shape[1]} table, n = {n}).\n",
        f"There was "
        + ("a statistically significant" if p < 0.05 else "no statistically significant")
        + f" association, **χ²({int(dof)}) = {round4(chi2)}**, {pstr(p)}, "
        f"Cramér's V = **{round4(cramers_v)}**.",
    ]
    if min_expected < 5:
        md.append(f"\n*Note:* the smallest expected count was {round4(min_expected)} (< 5); "
                  "Fisher's exact test may be preferable for this table.")
    refs = citations.refs(["pearson1900", "cramer1946"])
    fig = None
    if fig_dir:
        fig = plots.grouped_bar(list(map(str, table.index)), list(map(str, table.columns)),
                                table.values.tolist(), path=Path(fig_dir) / "chi2_bar.png")
    return {"key": "chi_square", "title": "Chi-square test of independence",
            "values": values, "markdown": "\n".join(md) + refs_block(refs),
            "references": refs, "figure_path": fig,
            "assumptions": ["Independent observations", "Expected counts ≥ 5 in most cells"]}


def linear_regression(df: pd.DataFrame, params: dict, fig_dir: str | Path | None = None) -> dict:
    import statsmodels.api as sm

    outcome = params.get("outcome")
    predictors = params.get("predictors") or ([params["predictor"]] if params.get("predictor") else [])
    if not outcome or not predictors:
        raise EngineError("Linear regression needs an 'outcome' and one or more 'predictors'.")
    cols = [outcome] + list(predictors)
    for c in cols:
        get_col(df, c, "column")
    data = df[cols].apply(pd.to_numeric, errors="coerce").dropna()
    if len(data) <= len(predictors) + 1:
        raise EngineError("Not enough complete rows for the number of predictors.")
    y = data[outcome]
    X = sm.add_constant(data[list(predictors)])
    model = sm.OLS(y, X).fit()
    coefs = []
    for name in X.columns:
        coefs.append({
            "term": "Intercept" if name == "const" else str(name),
            "beta": round4(model.params[name]),
            "se": round4(model.bse[name]),
            "t": round4(model.tvalues[name]),
            "p_value": float(model.pvalues[name]),
            "ci_low": round4(model.conf_int().loc[name, 0]),
            "ci_high": round4(model.conf_int().loc[name, 1]),
        })
    values = {
        "n": int(len(data)), "outcome": outcome, "predictors": list(predictors),
        "r_squared": round4(model.rsquared), "adj_r_squared": round4(model.rsquared_adj),
        "f": round4(model.fvalue), "f_p_value": float(model.f_pvalue),
        "df_model": int(model.df_model), "df_resid": int(model.df_resid),
        "coefficients": coefs,
    }
    md = [
        "## Multiple linear regression\n" if len(predictors) > 1 else "## Linear regression\n",
        f"We regressed **{outcome}** on {', '.join('**' + str(p) + '**' for p in predictors)} "
        f"(n = {len(data)}).\n",
        f"The model explained **{round(model.rsquared * 100, 1)}%** of the variance "
        f"(R² = {round4(model.rsquared)}, adjusted R² = {round4(model.rsquared_adj)}), "
        f"**F({int(model.df_model)}, {int(model.df_resid)}) = {round4(model.fvalue)}**, "
        f"{pstr(model.f_pvalue)}.\n",
        "| Term | B | 95% CI | SE | t | p |",
        "|---|---|---|---|---|---|",
    ]
    for c in coefs:
        md.append(f"| {c['term']} | {c['beta']} | {c['ci_low']} to {c['ci_high']} | "
                  f"{c['se']} | {c['t']} | {fmt_p(c['p_value'])} |")
    refs = citations.refs(["montgomery2012"])
    fig = None
    if fig_dir and len(predictors) == 1:
        b0 = model.params["const"]
        b1 = model.params[predictors[0]]
        fig = plots.scatter_fit(data[predictors[0]].tolist(), y.tolist(),
                                xlabel=str(predictors[0]), ylabel=str(outcome),
                                path=Path(fig_dir) / "regression.png", slope=b1, intercept=b0)
    return {"key": "linear_regression", "title": "Linear regression",
            "values": values, "markdown": "\n".join(md) + refs_block(refs),
            "references": refs, "figure_path": fig,
            "assumptions": ["Linearity", "Independent errors", "Homoscedasticity",
                            "Approximately normal residuals"]}


def _r_word(r):
    a = abs(r)
    return ("negligible" if a < 0.1 else "weak" if a < 0.3 else
            "moderate" if a < 0.5 else "strong" if a < 0.7 else "very strong")
