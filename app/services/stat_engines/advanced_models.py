"""Advanced engines: MANOVA and linear mixed-effects (multilevel) models."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from app.services import citations
from app.services.stat_engines.base import EngineError, fmt_p, get_col, pstr, refs_block, round4


def manova(df: pd.DataFrame, params: dict, fig_dir: str | Path | None = None) -> dict:
    """One-way MANOVA: several numeric outcomes across one grouping factor."""
    from statsmodels.multivariate.manova import MANOVA

    outcomes = params.get("outcomes") or []
    group = params.get("group")
    if len(outcomes) < 2 or not group:
        raise EngineError("MANOVA needs 2+ numeric 'outcomes' and one 'group' factor.")
    cols = list(outcomes) + [group]
    for c in cols:
        get_col(df, c, "column")
    data = df[cols].copy()
    for o in outcomes:
        data[o] = pd.to_numeric(data[o], errors="coerce")
    data = data.dropna()
    if data[group].nunique() < 2:
        raise EngineError("MANOVA needs at least 2 groups.")
    # safe names
    ren = {o: f"y{i}" for i, o in enumerate(outcomes)}
    data = data.rename(columns={**ren, group: "_g"})
    lhs = " + ".join(ren.values())
    mv = MANOVA.from_formula(f"{lhs} ~ C(_g)", data=data)
    test = mv.mv_test()
    stat = test.results["C(_g)"]["stat"]

    def _row(name):
        r = stat.loc[name]
        return {"value": round4(r["Value"]), "F": round4(r["F Value"]),
                "num_df": round4(r["Num DF"]), "den_df": round4(r["Den DF"]),
                "p_value": float(r["Pr > F"])}

    wilks = _row("Wilks' lambda")
    pillai = _row("Pillai's trace")
    values = {"n": int(len(data)), "outcomes": list(outcomes), "group": group,
              "wilks_lambda": wilks, "pillai_trace": pillai}
    md = [
        "## One-way MANOVA\n",
        f"We tested whether **{group}** affects the set of outcomes "
        f"({', '.join('**' + str(o) + '**' for o in outcomes)}) jointly (n = {len(data)}).\n",
        f"Wilks' Λ = {wilks['value']}, F({wilks['num_df']}, {wilks['den_df']}) = {wilks['F']}, "
        f"{pstr(wilks['p_value'])}. Pillai's trace = {pillai['value']}, {pstr(pillai['p_value'])}.",
        "\nA significant multivariate test indicates the groups differ on the outcomes taken "
        "together; follow up with per-outcome ANOVAs to see which differ.",
    ]
    refs = citations.refs(["rencher2002"])
    return {"key": "manova", "title": "One-way MANOVA", "values": values,
            "markdown": "\n".join(md) + refs_block(refs), "references": refs,
            "figure_path": None,
            "assumptions": ["Multivariate normality", "Homogeneity of covariance matrices",
                            "Independent observations"]}


def mixed_effects(df: pd.DataFrame, params: dict, fig_dir: str | Path | None = None) -> dict:
    """Linear mixed-effects model with a random intercept per group (multilevel)."""
    import statsmodels.formula.api as smf

    outcome = params.get("outcome")
    predictors = params.get("predictors") or ([params["predictor"]] if params.get("predictor") else [])
    group = params.get("group")   # the random-effect grouping (e.g. subject, clinic)
    if not outcome or not predictors or not group:
        raise EngineError("Mixed-effects model needs 'outcome', 'predictors' (fixed effects), "
                          "and 'group' (the random-intercept grouping, e.g. subject or site).")
    cols = [outcome, group] + list(predictors)
    for c in cols:
        get_col(df, c, "column")
    data = df[cols].copy()
    data[outcome] = pd.to_numeric(data[outcome], errors="coerce")
    for p in predictors:
        data[p] = pd.to_numeric(data[p], errors="coerce")
    data = data.dropna()
    if data[group].nunique() < 2:
        raise EngineError("Need at least 2 groups for the random effect.")
    data = data.rename(columns={outcome: "_y", group: "_g"})
    formula = "_y ~ " + " + ".join(predictors)
    try:
        model = smf.mixedlm(formula, data, groups=data["_g"]).fit()
    except Exception as exc:  # noqa: BLE001
        raise EngineError(f"Mixed model did not converge: {exc}") from exc
    ci = model.conf_int()
    rows = []
    for name in model.fe_params.index:
        rows.append({"term": "Intercept" if name == "Intercept" else str(name),
                     "beta": round4(model.fe_params[name]),
                     "ci_low": round4(ci.loc[name, 0]), "ci_high": round4(ci.loc[name, 1]),
                     "p_value": float(model.pvalues[name])})
    group_var = float(model.cov_re.iloc[0, 0]) if model.cov_re.size else None
    values = {"n": int(len(data)), "outcome": outcome, "group": group,
              "n_groups": int(data["_g"].nunique()), "predictors": list(predictors),
              "fixed_effects": rows, "group_variance": round4(group_var)}
    md = [
        "## Linear mixed-effects model\n",
        f"We modelled **{outcome}** from "
        f"{', '.join('**' + str(p) + '**' for p in predictors)} with a random intercept for "
        f"**{group}** ({data['_g'].nunique()} groups, n = {len(data)}). This accounts for "
        "the clustering/repeated structure in the data.\n",
        "| Fixed effect | B | 95% CI | p |",
        "|---|---|---|---|",
    ]
    for c in rows:
        md.append(f"| {c['term']} | {c['beta']} | {c['ci_low']} to {c['ci_high']} | "
                  f"{fmt_p(c['p_value'])} |")
    md.append(f"\nRandom-intercept variance ({group}) = {round4(group_var)}.")
    refs = citations.refs(["laird1982"])
    return {"key": "mixed_effects", "title": "Linear mixed-effects model", "values": values,
            "markdown": "\n".join(md) + refs_block(refs), "references": refs,
            "figure_path": None,
            "assumptions": ["Random effects and residuals approximately normal",
                            "Correctly specified grouping structure", "Linearity of fixed effects"]}
