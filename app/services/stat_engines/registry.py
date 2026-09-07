"""Registry of statistical-test engines.

The registry is the single catalogue the AI router chooses from: each entry
carries a human title, the engine function, the parameters it needs, and a
plain-language 'when to use' note. `run_engine` dispatches by key.

Adding a new test = add its function and one entry here; the router, pricing,
and reporting all read from this catalogue.
"""

from __future__ import annotations

from pathlib import Path

from app.services.stat_engines import associations, comparisons, descriptives
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
