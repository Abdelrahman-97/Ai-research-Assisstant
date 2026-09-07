"""Group-comparison engines: t-tests, ANOVA, and their non-parametric analogues.

Every function returns the standard engine result dict (see base.py). Parametric
tests report an effect size and check assumptions (Levene for equal variance;
a normality note). Where variances differ, the independent t-test switches to
Welch's correction automatically and says so.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

from app.services import citations
from app.services.stat_engines import plots
from app.services.stat_engines.base import (
    EngineError, describe, fmt_p, get_col, pstr, refs_block, round4,
)


def _two_group_frame(df, outcome, group):
    y = get_col(df, outcome, "outcome")
    g = get_col(df, group, "grouping")
    sub = pd.DataFrame({"y": pd.to_numeric(y, errors="coerce"), "g": g.astype(str)}).dropna()
    if sub.empty:
        raise EngineError("No complete rows for the chosen outcome and group columns.")
    return sub


def _welch_df(s1, n1, s2, n2):
    num = (s1 ** 2 / n1 + s2 ** 2 / n2) ** 2
    den = (s1 ** 2 / n1) ** 2 / (n1 - 1) + (s2 ** 2 / n2) ** 2 / (n2 - 1)
    return num / den if den else float("nan")


# --------------------------------------------------------------------------- #
def independent_ttest(df: pd.DataFrame, params: dict, fig_dir: str | Path | None = None) -> dict:
    outcome, group = params.get("outcome"), params.get("group")
    sub = _two_group_frame(df, outcome, group)
    levels = list(dict.fromkeys(sub["g"]))
    if len(levels) != 2:
        raise EngineError(
            f"Independent t-test needs exactly 2 groups, but '{group}' has "
            f"{len(levels)} ({', '.join(levels[:5])}). Use one-way ANOVA for 3+ groups."
        )
    a = sub[sub.g == levels[0]]["y"]
    b = sub[sub.g == levels[1]]["y"]
    if len(a) < 2 or len(b) < 2:
        raise EngineError("Each group needs at least 2 observations.")
    n1, n2 = len(a), len(b)
    m1, m2 = a.mean(), b.mean()
    s1, s2 = a.std(ddof=1), b.std(ddof=1)

    lev_stat, lev_p = stats.levene(a, b, center="median")
    equal_var = bool(lev_p >= 0.05)
    t, p = stats.ttest_ind(a, b, equal_var=equal_var)

    sp = math.sqrt(((n1 - 1) * s1 ** 2 + (n2 - 1) * s2 ** 2) / (n1 + n2 - 2))
    d = (m1 - m2) / sp if sp else None
    if equal_var:
        dfree = n1 + n2 - 2
        se = sp * math.sqrt(1 / n1 + 1 / n2)
    else:
        dfree = _welch_df(s1, n1, s2, n2)
        se = math.sqrt(s1 ** 2 / n1 + s2 ** 2 / n2)
    tcrit = stats.t.ppf(0.975, dfree)
    diff = m1 - m2
    ci = (diff - tcrit * se, diff + tcrit * se)

    method = "Student's t-test" if equal_var else "Welch's t-test (unequal variances)"
    values = {
        "groups": {levels[0]: describe(a), levels[1]: describe(b)},
        "mean_difference": round4(diff), "ci95": [round4(ci[0]), round4(ci[1])],
        "t": round4(t), "df": round4(dfree), "p_value": float(p),
        "cohens_d": round4(d), "equal_variances": equal_var,
        "levene": {"statistic": round4(lev_stat), "p_value": float(lev_p)},
        "method": method,
    }
    md = [
        f"## Independent-samples t-test\n",
        f"We compared **{outcome}** between **{levels[0]}** (n = {n1}, "
        f"M = {round4(m1)}, SD = {round4(s1)}) and **{levels[1]}** (n = {n2}, "
        f"M = {round4(m2)}, SD = {round4(s2)}).\n",
        f"Levene's test for equal variances: F = {round4(lev_stat)}, {pstr(lev_p)} — "
        + ("variances were similar, so Student's t-test was used."
           if equal_var else "variances differed, so Welch's correction was applied."),
        f"\nThe difference in means was **{round4(diff)}** (95% CI {round4(ci[0])} to "
        f"{round4(ci[1])}), **t({round4(dfree)}) = {round4(t)}**, {pstr(p)}. "
        f"Cohen's d = **{round4(d)}** "
        f"({_d_word(d)} effect).",
    ]
    refs = citations.refs(["student1908"] + ([] if equal_var else ["welch1947"])
                          + ["levene1960", "cohen1988"])
    fig = None
    if fig_dir:
        fig = plots.box_by_group({levels[0]: a.tolist(), levels[1]: b.tolist()},
                                 ylabel=str(outcome), path=Path(fig_dir) / "ttest_box.png")
    return {"key": "independent_ttest", "title": "Independent-samples t-test",
            "values": values, "markdown": "\n".join(md) + refs_block(refs),
            "references": refs, "figure_path": fig,
            "assumptions": ["Independent observations", "Approximately normal outcome per group",
                            "Variance equality assessed by Levene's test"]}


def paired_ttest(df: pd.DataFrame, params: dict, fig_dir: str | Path | None = None) -> dict:
    pre_c, post_c = params.get("pre") or params.get("var1"), params.get("post") or params.get("var2")
    pre = get_col(df, pre_c, "pre/first column")
    post = get_col(df, post_c, "post/second column")
    sub = pd.DataFrame({"a": pd.to_numeric(pre, errors="coerce"),
                        "b": pd.to_numeric(post, errors="coerce")}).dropna()
    if len(sub) < 2:
        raise EngineError("Paired t-test needs at least 2 complete pairs.")
    a, b = sub["a"], sub["b"]
    diff = b - a
    n = len(sub)
    md_diff = diff.mean()
    sd_diff = diff.std(ddof=1)
    t, p = stats.ttest_rel(b, a)
    dz = md_diff / sd_diff if sd_diff else None
    se = sd_diff / math.sqrt(n)
    tcrit = stats.t.ppf(0.975, n - 1)
    ci = (md_diff - tcrit * se, md_diff + tcrit * se)
    values = {
        "n_pairs": n, "pre": describe(a), "post": describe(b),
        "mean_change": round4(md_diff), "ci95": [round4(ci[0]), round4(ci[1])],
        "t": round4(t), "df": n - 1, "p_value": float(p), "cohens_dz": round4(dz),
    }
    md = [
        "## Paired-samples t-test\n",
        f"We compared **{post_c}** with **{pre_c}** across **{n} paired observations** "
        f"(pre: M = {round4(a.mean())}, SD = {round4(a.std(ddof=1))}; "
        f"post: M = {round4(b.mean())}, SD = {round4(b.std(ddof=1))}).\n",
        f"The mean change was **{round4(md_diff)}** (95% CI {round4(ci[0])} to "
        f"{round4(ci[1])}), **t({n - 1}) = {round4(t)}**, {pstr(p)}. "
        f"Cohen's dz = **{round4(dz)}** ({_d_word(dz)} effect).",
    ]
    refs = citations.refs(["student1908", "cohen1988"])
    fig = None
    if fig_dir:
        fig = plots.paired_lines(a.tolist(), b.tolist(), labels=(str(pre_c), str(post_c)),
                                 ylabel="Value", path=Path(fig_dir) / "paired.png")
    return {"key": "paired_ttest", "title": "Paired-samples t-test",
            "values": values, "markdown": "\n".join(md) + refs_block(refs),
            "references": refs, "figure_path": fig,
            "assumptions": ["Paired/related observations", "Approximately normal differences"]}


def one_way_anova(df: pd.DataFrame, params: dict, fig_dir: str | Path | None = None) -> dict:
    outcome, group = params.get("outcome"), params.get("group")
    sub = _two_group_frame(df, outcome, group)
    levels = list(dict.fromkeys(sub["g"]))
    if len(levels) < 2:
        raise EngineError("ANOVA needs at least 2 groups.")
    arrays = [sub[sub.g == lv]["y"].values for lv in levels]
    if any(len(x) < 2 for x in arrays):
        raise EngineError("Each group needs at least 2 observations.")
    f, p = stats.f_oneway(*arrays)
    grand = sub["y"].mean()
    ss_between = sum(len(x) * (np.mean(x) - grand) ** 2 for x in arrays)
    ss_total = float(((sub["y"] - grand) ** 2).sum())
    eta2 = ss_between / ss_total if ss_total else None
    df_between = len(levels) - 1
    df_within = len(sub) - len(levels)
    lev_stat, lev_p = stats.levene(*arrays, center="median")
    values = {
        "groups": {lv: describe(sub[sub.g == lv]["y"]) for lv in levels},
        "f": round4(f), "df_between": df_between, "df_within": df_within,
        "p_value": float(p), "eta_squared": round4(eta2),
        "levene": {"statistic": round4(lev_stat), "p_value": float(lev_p)},
    }
    md = [
        "## One-way ANOVA\n",
        f"We compared **{outcome}** across **{len(levels)} groups** "
        f"({', '.join(levels[:8])}).\n",
        f"There was "
        + ("a statistically significant" if p < 0.05 else "no statistically significant")
        + f" difference between groups, **F({df_between}, {df_within}) = {round4(f)}**, "
        f"{pstr(p)}, η² = **{round4(eta2)}**.",
        f"\nLevene's test: F = {round4(lev_stat)}, {pstr(lev_p)}"
        + (" (variances similar)." if lev_p >= 0.05 else " (variances differ; consider Welch's ANOVA)."),
    ]
    refs = citations.refs(["fisher1925", "levene1960", "cohen1988"])
    fig = None
    if fig_dir:
        fig = plots.box_by_group({lv: sub[sub.g == lv]["y"].tolist() for lv in levels},
                                 ylabel=str(outcome), path=Path(fig_dir) / "anova_box.png")
    return {"key": "one_way_anova", "title": "One-way ANOVA",
            "values": values, "markdown": "\n".join(md) + refs_block(refs),
            "references": refs, "figure_path": fig,
            "assumptions": ["Independent observations", "Approximately normal outcome per group",
                            "Homogeneity of variance (Levene's test)"]}


def mann_whitney(df: pd.DataFrame, params: dict, fig_dir: str | Path | None = None) -> dict:
    outcome, group = params.get("outcome"), params.get("group")
    sub = _two_group_frame(df, outcome, group)
    levels = list(dict.fromkeys(sub["g"]))
    if len(levels) != 2:
        raise EngineError(f"Mann-Whitney U needs exactly 2 groups; '{group}' has {len(levels)}.")
    a = sub[sub.g == levels[0]]["y"]
    b = sub[sub.g == levels[1]]["y"]
    u, p = stats.mannwhitneyu(a, b, alternative="two-sided")
    n1, n2 = len(a), len(b)
    # rank-biserial correlation as effect size
    rbc = 1 - (2 * u) / (n1 * n2)
    mu = n1 * n2 / 2
    sigma = math.sqrt(n1 * n2 * (n1 + n2 + 1) / 12)
    z = (u - mu) / sigma if sigma else None
    values = {
        "groups": {levels[0]: describe(a), levels[1]: describe(b)},
        "medians": {levels[0]: round4(a.median()), levels[1]: round4(b.median())},
        "u": round4(u), "z": round4(z), "p_value": float(p),
        "rank_biserial_r": round4(rbc),
    }
    md = [
        "## Mann-Whitney U test\n",
        f"We compared the distribution of **{outcome}** between **{levels[0]}** "
        f"(n = {n1}, Mdn = {round4(a.median())}) and **{levels[1]}** "
        f"(n = {n2}, Mdn = {round4(b.median())}).\n",
        f"The difference was "
        + ("statistically significant" if p < 0.05 else "not statistically significant")
        + f", **U = {round4(u)}**, {pstr(p)}, rank-biserial r = **{round4(rbc)}**.",
    ]
    refs = citations.refs(["mann1947"])
    fig = None
    if fig_dir:
        fig = plots.box_by_group({levels[0]: a.tolist(), levels[1]: b.tolist()},
                                 ylabel=str(outcome), path=Path(fig_dir) / "mwu_box.png")
    return {"key": "mann_whitney", "title": "Mann-Whitney U test",
            "values": values, "markdown": "\n".join(md) + refs_block(refs),
            "references": refs, "figure_path": fig,
            "assumptions": ["Independent observations", "Ordinal or continuous outcome (no normality assumed)"]}


def wilcoxon(df: pd.DataFrame, params: dict, fig_dir: str | Path | None = None) -> dict:
    pre_c, post_c = params.get("pre") or params.get("var1"), params.get("post") or params.get("var2")
    pre = get_col(df, pre_c, "pre/first column")
    post = get_col(df, post_c, "post/second column")
    sub = pd.DataFrame({"a": pd.to_numeric(pre, errors="coerce"),
                        "b": pd.to_numeric(post, errors="coerce")}).dropna()
    if len(sub) < 2:
        raise EngineError("Wilcoxon signed-rank needs at least 2 complete pairs.")
    a, b = sub["a"], sub["b"]
    stat, p = stats.wilcoxon(b, a)
    n = len(sub)
    values = {
        "n_pairs": n, "pre_median": round4(a.median()), "post_median": round4(b.median()),
        "w": round4(stat), "p_value": float(p),
    }
    md = [
        "## Wilcoxon signed-rank test\n",
        f"We compared **{post_c}** with **{pre_c}** across **{n} pairs** "
        f"(pre Mdn = {round4(a.median())}, post Mdn = {round4(b.median())}).\n",
        f"The change was "
        + ("statistically significant" if p < 0.05 else "not statistically significant")
        + f", **W = {round4(stat)}**, {pstr(p)}.",
    ]
    refs = citations.refs(["wilcoxon1945"])
    fig = None
    if fig_dir:
        fig = plots.paired_lines(a.tolist(), b.tolist(), labels=(str(pre_c), str(post_c)),
                                 ylabel="Value", path=Path(fig_dir) / "wilcoxon.png")
    return {"key": "wilcoxon", "title": "Wilcoxon signed-rank test",
            "values": values, "markdown": "\n".join(md) + refs_block(refs),
            "references": refs, "figure_path": fig,
            "assumptions": ["Paired/related observations", "Ordinal or continuous differences"]}


def kruskal_wallis(df: pd.DataFrame, params: dict, fig_dir: str | Path | None = None) -> dict:
    outcome, group = params.get("outcome"), params.get("group")
    sub = _two_group_frame(df, outcome, group)
    levels = list(dict.fromkeys(sub["g"]))
    if len(levels) < 2:
        raise EngineError("Kruskal-Wallis needs at least 2 groups.")
    arrays = [sub[sub.g == lv]["y"].values for lv in levels]
    h, p = stats.kruskal(*arrays)
    n = len(sub)
    k = len(levels)
    eps2 = (h - k + 1) / (n - k) if (n - k) else None  # epsilon-squared
    values = {
        "groups": {lv: {**describe(sub[sub.g == lv]["y"]),
                        "median": round4(sub[sub.g == lv]["y"].median())} for lv in levels},
        "h": round4(h), "df": k - 1, "p_value": float(p), "epsilon_squared": round4(eps2),
    }
    md = [
        "## Kruskal-Wallis H test\n",
        f"We compared **{outcome}** across **{k} groups** ({', '.join(levels[:8])}).\n",
        f"There was "
        + ("a statistically significant" if p < 0.05 else "no statistically significant")
        + f" difference, **H({k - 1}) = {round4(h)}**, {pstr(p)}, ε² = **{round4(eps2)}**.",
    ]
    refs = citations.refs(["kruskal1952"])
    fig = None
    if fig_dir:
        fig = plots.box_by_group({lv: sub[sub.g == lv]["y"].tolist() for lv in levels},
                                 ylabel=str(outcome), path=Path(fig_dir) / "kw_box.png")
    return {"key": "kruskal_wallis", "title": "Kruskal-Wallis H test",
            "values": values, "markdown": "\n".join(md) + refs_block(refs),
            "references": refs, "figure_path": fig,
            "assumptions": ["Independent observations", "Ordinal or continuous outcome (no normality assumed)"]}


def _d_word(d):
    if d is None:
        return "—"
    a = abs(d)
    return "small" if a < 0.5 else "medium" if a < 0.8 else "large"
