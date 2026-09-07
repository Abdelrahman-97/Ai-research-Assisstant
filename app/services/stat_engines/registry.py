"""Registry of statistical-test engines.

The registry is the single catalogue the AI router chooses from: each entry
carries a human title, the engine function, the parameters it needs, and a
plain-language 'when to use' note. `run_engine` dispatches by key.

Adding a new test = add its function and one entry here; the router, pricing,
and reporting all read from this catalogue.
"""

from __future__ import annotations

from pathlib import Path

from app.services.stat_engines import (
    agreement, anova_models, associations, categorical, comparisons, descriptives,
    regression_models, survival,
)
from app.services.stat_engines.base import EngineError

# key -> spec. `params` documents the keys each engine expects (for the router
# and the UI); `outcome`/`group`/`variables`/etc. are column names in the data.
REGISTRY: dict[str, dict] = {
    "descriptive_summary": {
        "title": "Descriptive statistics",
        "fn": descriptives.descriptive_summary,
        "params": {"variables": "list of numeric columns", "group": "optional grouping column"},
        "when": "Summaries (mean, SD, range) of numeric variables, optionally split by a group.",
    },
    "independent_ttest": {
        "title": "Independent-samples t-test",
        "fn": comparisons.independent_ttest,
        "params": {"outcome": "numeric column", "group": "column with exactly 2 groups"},
        "when": "Compare the mean of one numeric outcome between TWO independent groups.",
    },
    "paired_ttest": {
        "title": "Paired-samples t-test",
        "fn": comparisons.paired_ttest,
        "params": {"pre": "numeric column (before)", "post": "numeric column (after)"},
        "when": "Compare two related/paired numeric measurements (e.g. pre vs post) on the same subjects.",
    },
    "one_way_anova": {
        "title": "One-way ANOVA",
        "fn": comparisons.one_way_anova,
        "params": {"outcome": "numeric column", "group": "column with 2+ groups"},
        "when": "Compare the mean of one numeric outcome across THREE or more independent groups.",
    },
    "mann_whitney": {
        "title": "Mann-Whitney U test",
        "fn": comparisons.mann_whitney,
        "params": {"outcome": "numeric/ordinal column", "group": "column with exactly 2 groups"},
        "when": "Non-parametric alternative to the independent t-test (skewed/ordinal outcome, 2 groups).",
    },
    "wilcoxon": {
        "title": "Wilcoxon signed-rank test",
        "fn": comparisons.wilcoxon,
        "params": {"pre": "numeric column (before)", "post": "numeric column (after)"},
        "when": "Non-parametric alternative to the paired t-test (skewed/ordinal paired data).",
    },
    "kruskal_wallis": {
        "title": "Kruskal-Wallis H test",
        "fn": comparisons.kruskal_wallis,
        "params": {"outcome": "numeric/ordinal column", "group": "column with 2+ groups"},
        "when": "Non-parametric alternative to one-way ANOVA (skewed/ordinal outcome, 3+ groups).",
    },
    "correlation": {
        "title": "Correlation",
        "fn": associations.correlation,
        "params": {"var1": "numeric column", "var2": "numeric column",
                   "method": "'pearson' (linear) or 'spearman' (ranks)"},
        "when": "Measure the association between TWO numeric variables.",
    },
    "chi_square": {
        "title": "Chi-square test of independence",
        "fn": associations.chi_square,
        "params": {"var1": "categorical column", "var2": "categorical column"},
        "when": "Test the association between TWO categorical variables.",
    },
    "linear_regression": {
        "title": "Linear regression",
        "fn": associations.linear_regression,
        "params": {"outcome": "numeric column", "predictors": "list of predictor columns"},
        "when": "Model a numeric outcome from one or more predictors; gives coefficients, R², CIs.",
    },
    "logistic_regression": {
        "title": "Logistic regression",
        "fn": regression_models.logistic_regression,
        "params": {"outcome": "binary column", "predictors": "list of predictor columns"},
        "when": "Model a BINARY outcome (yes/no) from predictors; gives odds ratios with CIs.",
    },
    "ancova": {
        "title": "ANCOVA",
        "fn": regression_models.ancova,
        "params": {"outcome": "numeric column", "group": "grouping column",
                   "covariates": "list of numeric covariates to adjust for"},
        "when": "Compare a numeric outcome across groups while adjusting for covariate(s).",
    },
    "repeated_measures_anova": {
        "title": "Repeated-measures ANOVA",
        "fn": anova_models.repeated_measures_anova,
        "params": {"subject": "subject id column", "within": "condition/time column",
                   "outcome": "numeric column"},
        "when": "Compare a numeric outcome across conditions/time measured on the SAME subjects "
                "(long format: one row per subject × condition).",
    },
    "survival_logrank": {
        "title": "Kaplan-Meier / log-rank",
        "fn": survival.survival_logrank,
        "params": {"time": "time-to-event column", "event": "event column (1=event, 0=censored)",
                   "group": "optional grouping column"},
        "when": "Time-to-event (survival) analysis: Kaplan-Meier curves and the log-rank test "
                "comparing groups.",
    },
    "cox_regression": {
        "title": "Cox proportional-hazards regression",
        "fn": regression_models.cox_regression,
        "params": {"time": "time-to-event column", "event": "event column (1=event, 0=censored)",
                   "predictors": "list of predictor columns"},
        "when": "Model time-to-event outcomes from predictors; gives hazard ratios with CIs.",
    },
    "cohens_kappa": {
        "title": "Cohen's kappa",
        "fn": agreement.cohens_kappa,
        "params": {"rater1": "first rater's categorical column", "rater2": "second rater's column"},
        "when": "Inter-rater agreement between TWO raters on a categorical rating.",
    },
    "icc": {
        "title": "Intraclass correlation (ICC)",
        "fn": agreement.icc,
        "params": {"raters": "list of 2+ numeric rater/measurement columns"},
        "when": "Reliability/agreement of numeric measurements across 2+ raters or repeats.",
    },
    "bland_altman": {
        "title": "Bland-Altman agreement",
        "fn": agreement.bland_altman,
        "params": {"method1": "numeric column (method A)", "method2": "numeric column (method B)"},
        "when": "Agreement between TWO measurement methods (bias + limits of agreement).",
    },
    "friedman": {
        "title": "Friedman test",
        "fn": anova_models.friedman,
        "params": {"subject": "subject id column", "within": "condition/time column",
                   "outcome": "numeric column"},
        "when": "Non-parametric alternative to repeated-measures ANOVA (3+ conditions on the "
                "same subjects; long format).",
    },
    "fishers_exact": {
        "title": "Fisher's exact test",
        "fn": categorical.fishers_exact,
        "params": {"var1": "binary categorical column", "var2": "binary categorical column"},
        "when": "Association between two binary variables in a 2×2 table with a SMALL sample "
                "(preferred over chi-square when expected counts are low).",
    },
    "mcnemar": {
        "title": "McNemar's test",
        "fn": categorical.mcnemar,
        "params": {"var1": "binary before column", "var2": "binary after column"},
        "when": "Paired binary data — change in a yes/no outcome measured twice on the same "
                "subjects (e.g. before vs after).",
    },
}


def catalogue() -> list[dict]:
    """List of {key, title, when, params} for the router/UI (no functions)."""
    return [{"key": k, "title": v["title"], "when": v["when"], "params": v["params"]}
            for k, v in REGISTRY.items()]


def run_engine(key: str, df, params: dict, fig_dir: str | Path | None = None) -> dict:
    """Dispatch to an engine by key. Raises EngineError for an unknown key."""
    spec = REGISTRY.get(key)
    if not spec:
        raise EngineError(f"Unknown analysis engine: '{key}'.")
    return spec["fn"](df, params or {}, fig_dir=fig_dir)
