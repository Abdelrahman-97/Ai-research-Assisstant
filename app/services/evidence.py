"""Methodological evidence for proposed statistical tests.

A fixed, curated reference base mapping each common test to its CANONICAL
citation (the original/defining publication), its family (parametric vs.
non-parametric), when it's appropriate, and its key assumptions.

Everything here is hard-coded and human-verified, so the evidence Neura attaches
to a proposed test is always real — never generated (and never hallucinated) by
the LLM. If a proposed test isn't in the base, we return an unmatched result so
the UI can say "no curated reference — verify manually" rather than invent one.
"""

from __future__ import annotations

import re

from app.models.schemas import TestEvidence

PARAMETRIC = "parametric"
NONPARAMETRIC = "non-parametric"
OTHER = "other"

# canonical_key -> evidence record
_BASE: dict[str, dict] = {
    # ---------------- Parametric ----------------
    "independent_t_test": {
        "family": PARAMETRIC,
        "when_to_use": "Compare the means of a continuous outcome between two independent groups.",
        "assumptions": ["Independence of observations", "Approximate normality within each group", "Homogeneity of variances (else use Welch's correction)"],
        "citation": "Student (1908). The probable error of a mean. Biometrika, 6(1), 1–25.",
    },
    "paired_t_test": {
        "family": PARAMETRIC,
        "when_to_use": "Compare means of a continuous outcome measured twice on the same subjects (paired/repeated).",
        "assumptions": ["Paired observations", "Approximate normality of the differences"],
        "citation": "Student (1908). The probable error of a mean. Biometrika, 6(1), 1–25.",
    },
    "one_way_anova": {
        "family": PARAMETRIC,
        "when_to_use": "Compare the means of a continuous outcome across three or more independent groups.",
        "assumptions": ["Independence", "Normality of residuals", "Homogeneity of variances"],
        "citation": "Fisher, R. A. (1925). Statistical Methods for Research Workers. Oliver & Boyd.",
    },
    "two_way_anova": {
        "family": PARAMETRIC,
        "when_to_use": "Assess the effect of two categorical factors (and their interaction) on a continuous outcome.",
        "assumptions": ["Independence", "Normality of residuals", "Homogeneity of variances"],
        "citation": "Fisher, R. A. (1925). Statistical Methods for Research Workers. Oliver & Boyd.",
    },
    "ancova": {
        "family": PARAMETRIC,
        "when_to_use": "Compare group means on a continuous outcome while adjusting for a continuous covariate.",
        "assumptions": ["Independence", "Normality of residuals", "Homogeneity of variances", "Homogeneity of regression slopes"],
        "citation": "Fisher, R. A. (1932). Statistical Methods for Research Workers (4th ed.). Oliver & Boyd.",
    },
    "repeated_measures_anova": {
        "family": PARAMETRIC,
        "when_to_use": "Compare means of a continuous outcome across three or more repeated measurements on the same subjects.",
        "assumptions": ["Normality", "Sphericity (else apply Greenhouse–Geisser correction)"],
        "citation": "Fisher, R. A. (1925). Statistical Methods for Research Workers. Oliver & Boyd.",
    },
    "pearson_correlation": {
        "family": PARAMETRIC,
        "when_to_use": "Measure the linear association between two continuous variables.",
        "assumptions": ["Linear relationship", "Bivariate normality", "Homoscedasticity"],
        "citation": "Pearson, K. (1896). Mathematical contributions to the theory of evolution. III. Philosophical Transactions of the Royal Society A, 187, 253–318.",
    },
    "linear_regression": {
        "family": PARAMETRIC,
        "when_to_use": "Model a continuous outcome as a linear function of one or more predictors.",
        "assumptions": ["Linearity", "Independence of residuals", "Homoscedasticity", "Normality of residuals"],
        "citation": "Galton, F. (1886). Regression towards mediocrity in hereditary stature. Journal of the Anthropological Institute, 15, 246–263.",
    },
    "logistic_regression": {
        "family": PARAMETRIC,
        "when_to_use": "Model a binary outcome as a function of one or more predictors.",
        "assumptions": ["Independence", "Linearity of the logit", "No severe multicollinearity"],
        "citation": "Cox, D. R. (1958). The regression analysis of binary sequences. Journal of the Royal Statistical Society B, 20(2), 215–242.",
    },
    # ---------------- Non-parametric ----------------
    "mann_whitney_u": {
        "family": NONPARAMETRIC,
        "when_to_use": "Compare a continuous/ordinal outcome between two independent groups when normality is not met.",
        "assumptions": ["Independence", "Ordinal or continuous outcome", "Similarly shaped distributions (for a median interpretation)"],
        "citation": "Mann, H. B., & Whitney, D. R. (1947). On a test of whether one of two random variables is stochastically larger than the other. Annals of Mathematical Statistics, 18(1), 50–60.",
    },
    "wilcoxon_signed_rank": {
        "family": NONPARAMETRIC,
        "when_to_use": "Compare paired/repeated measurements of an ordinal or continuous outcome when normality is not met.",
        "assumptions": ["Paired observations", "Symmetry of the differences"],
        "citation": "Wilcoxon, F. (1945). Individual comparisons by ranking methods. Biometrics Bulletin, 1(6), 80–83.",
    },
    "kruskal_wallis": {
        "family": NONPARAMETRIC,
        "when_to_use": "Compare a continuous/ordinal outcome across three or more independent groups when normality is not met.",
        "assumptions": ["Independence", "Ordinal or continuous outcome"],
        "citation": "Kruskal, W. H., & Wallis, W. A. (1952). Use of ranks in one-criterion variance analysis. Journal of the American Statistical Association, 47(260), 583–621.",
    },
    "friedman": {
        "family": NONPARAMETRIC,
        "when_to_use": "Compare three or more repeated measurements on the same subjects when normality is not met.",
        "assumptions": ["Repeated measures on the same subjects", "Ordinal or continuous outcome"],
        "citation": "Friedman, M. (1937). The use of ranks to avoid the assumption of normality implicit in the analysis of variance. JASA, 32(200), 675–701.",
    },
    "spearman_correlation": {
        "family": NONPARAMETRIC,
        "when_to_use": "Measure the monotonic association between two ordinal/continuous variables (rank-based).",
        "assumptions": ["Monotonic relationship", "Ordinal or continuous variables"],
        "citation": "Spearman, C. (1904). The proof and measurement of association between two things. American Journal of Psychology, 15(1), 72–101.",
    },
    "chi_square": {
        "family": NONPARAMETRIC,
        "when_to_use": "Test association between two categorical variables in a contingency table.",
        "assumptions": ["Independence", "Expected cell counts ≥ 5 (else use Fisher's exact)"],
        "citation": "Pearson, K. (1900). On the criterion that a given system of deviations... Philosophical Magazine, 50(302), 157–175.",
    },
    "fisher_exact": {
        "family": NONPARAMETRIC,
        "when_to_use": "Test association between two categorical variables with small expected counts.",
        "assumptions": ["Independence", "Fixed margins (classical form)"],
        "citation": "Fisher, R. A. (1922). On the interpretation of χ² from contingency tables. JRSS, 85(1), 87–94.",
    },
    # ---------------- Assumption checks / survival / reliability ----------------
    "shapiro_wilk": {
        "family": OTHER,
        "when_to_use": "Test whether a sample departs from a normal distribution (assumption check).",
        "assumptions": ["Independent observations"],
        "citation": "Shapiro, S. S., & Wilk, M. B. (1965). An analysis of variance test for normality. Biometrika, 52(3/4), 591–611.",
    },
    "levene": {
        "family": OTHER,
        "when_to_use": "Test equality of variances across groups (assumption check for t-test/ANOVA).",
        "assumptions": ["Independent observations"],
        "citation": "Levene, H. (1960). Robust tests for equality of variances. In Contributions to Probability and Statistics (pp. 278–292). Stanford University Press.",
    },
    "kaplan_meier": {
        "family": OTHER,
        "when_to_use": "Estimate survival probability over time from censored time-to-event data.",
        "assumptions": ["Non-informative censoring"],
        "citation": "Kaplan, E. L., & Meier, P. (1958). Nonparametric estimation from incomplete observations. JASA, 53(282), 457–481.",
    },
    "cox_regression": {
        "family": OTHER,
        "when_to_use": "Model the effect of covariates on time-to-event (hazard) data.",
        "assumptions": ["Proportional hazards", "Non-informative censoring"],
        "citation": "Cox, D. R. (1972). Regression models and life-tables. JRSS B, 34(2), 187–220.",
    },
    "cronbach_alpha": {
        "family": OTHER,
        "when_to_use": "Assess internal-consistency reliability of a multi-item scale.",
        "assumptions": ["Unidimensional scale", "Tau-equivalent items"],
        "citation": "Cronbach, L. J. (1951). Coefficient alpha and the internal structure of tests. Psychometrika, 16(3), 297–334.",
    },
}

# Alias phrases (lowercased, non-alphanumeric stripped) -> canonical key.
# Ordered longest/most-specific first where it matters.
_ALIASES: list[tuple[str, str]] = [
    ("independent samples t", "independent_t_test"),
    ("independent t", "independent_t_test"),
    ("unpaired t", "independent_t_test"),
    ("two sample t", "independent_t_test"),
    ("student t", "independent_t_test"),
    ("welch", "independent_t_test"),
    ("paired t", "paired_t_test"),
    ("dependent t", "paired_t_test"),
    ("one way anova", "one_way_anova"),
    ("two way anova", "two_way_anova"),
    ("repeated measures anova", "repeated_measures_anova"),
    ("ancova", "ancova"),
    ("analysis of covariance", "ancova"),
    ("anova", "one_way_anova"),
    ("pearson", "pearson_correlation"),
    ("spearman", "spearman_correlation"),
    ("logistic regression", "logistic_regression"),
    ("linear regression", "linear_regression"),
    ("simple regression", "linear_regression"),
    ("multiple regression", "linear_regression"),
    ("mann whitney", "mann_whitney_u"),
    ("wilcoxon rank sum", "mann_whitney_u"),
    ("wilcoxon signed rank", "wilcoxon_signed_rank"),
    ("wilcoxon", "wilcoxon_signed_rank"),
    ("kruskal", "kruskal_wallis"),
    ("friedman", "friedman"),
    ("fisher exact", "fisher_exact"),
    ("fishers exact", "fisher_exact"),
    ("chi square", "chi_square"),
    ("chi squared", "chi_square"),
    ("chisquare", "chi_square"),
    ("shapiro", "shapiro_wilk"),
    ("levene", "levene"),
    ("kaplan", "kaplan_meier"),
    ("cox", "cox_regression"),
    ("cronbach", "cronbach_alpha"),
]


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]", " ", text.lower())


def lookup(test_name: str) -> TestEvidence:
    """Return curated evidence for a test name (alias-matched), or an unmatched record."""
    norm = _normalize(test_name)
    key = None
    for alias, canonical in _ALIASES:
        if alias in norm:
            key = canonical
            break
    if key is None:
        return TestEvidence(
            matched=False,
            note="No curated reference for this test — please verify the method and citation manually.",
        )
    rec = _BASE[key]
    return TestEvidence(
        matched=True,
        canonical_name=key.replace("_", " "),
        family=rec["family"],
        when_to_use=rec["when_to_use"],
        assumptions=list(rec["assumptions"]),
        citation=rec["citation"],
    )


def attach(test) -> None:
    """Attach curated evidence to a ProposedTest in place (based on its name)."""
    test.evidence = lookup(test.name)


def to_markdown(ev: TestEvidence, test_name: str) -> str:
    """Render an evidence block as Markdown for inclusion in the results document."""
    if not ev or not ev.matched:
        return ""
    lines = [
        "## Statistical method",
        "",
        f"**Test:** {test_name}"
        + (f" ({ev.family})" if ev.family else ""),
    ]
    if ev.when_to_use:
        lines += ["", f"**When appropriate:** {ev.when_to_use}"]
    if ev.assumptions:
        lines += ["", "**Assumptions:**"] + [f"- {a}" for a in ev.assumptions]
    if ev.citation:
        lines += ["", f"**Reference:** {ev.citation}"]
    return "\n".join(lines)
