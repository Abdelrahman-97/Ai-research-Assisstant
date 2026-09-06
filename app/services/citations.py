"""Curated methodological citations.

Every statistical method the app uses cites a real, canonical reference from this
fixed registry — never an LLM-generated one. Look up by a stable key and attach
the reference to the result so the user can trust and reproduce the method.
"""

from __future__ import annotations

# key -> full reference string (author, year, title, source).
_REFS: dict[str, str] = {
    # --- General power / sample size ---
    "cohen1988": "Cohen, J. (1988). Statistical Power Analysis for the Behavioral Sciences (2nd ed.). Lawrence Erlbaum Associates.",
    "fleiss2003": "Fleiss, J. L., Levin, B., & Paik, M. C. (2003). Statistical Methods for Rates and Proportions (3rd ed.). Wiley.",
    "schoenfeld1983": "Schoenfeld, D. A. (1983). Sample-size formula for the proportional-hazards regression model. Biometrics, 39(2), 499–503.",
    "donner2000": "Donner, A., & Klar, N. (2000). Design and Analysis of Cluster Randomization Trials in Health Research. Arnold.",
    "fisher1921": "Fisher, R. A. (1921). On the 'probable error' of a coefficient of correlation deduced from a small sample. Metron, 1, 3–32.",

    # --- Meta-analysis: models ---
    "borenstein2009": "Borenstein, M., Hedges, L. V., Higgins, J. P. T., & Rothstein, H. R. (2009). Introduction to Meta-Analysis. Wiley.",
    "dersimonian1986": "DerSimonian, R., & Laird, N. (1986). Meta-analysis in clinical trials. Controlled Clinical Trials, 7(3), 177–188.",
    "paule1982": "Paule, R. C., & Mandel, J. (1982). Consensus values and weighting factors. Journal of Research of the National Bureau of Standards, 87(5), 377–385.",
    "viechtbauer2005": "Viechtbauer, W. (2005). Bias and efficiency of meta-analytic variance estimators in the random-effects model. Journal of Educational and Behavioral Statistics, 30(3), 261–293.",

    # --- Meta-analysis: heterogeneity & intervals ---
    "higgins2002": "Higgins, J. P. T., & Thompson, S. G. (2002). Quantifying heterogeneity in a meta-analysis. Statistics in Medicine, 21(11), 1539–1558.",
    "higgins2009pi": "Higgins, J. P. T., Thompson, S. G., & Spiegelhalter, D. J. (2009). A re-evaluation of random-effects meta-analysis. Journal of the Royal Statistical Society A, 172(1), 137–159.",
    "hartung2001": "Hartung, J., & Knapp, G. (2001). A refined method for the meta-analysis of controlled clinical trials with a binary outcome. Statistics in Medicine, 20(24), 3875–3889.",
    "sidik2002": "Sidik, K., & Jonkman, J. N. (2002). A simple confidence interval for meta-analysis. Statistics in Medicine, 21(21), 3153–3159.",

    # --- Meta-analysis: effect measures ---
    "hedges1981": "Hedges, L. V. (1981). Distribution theory for Glass's estimator of effect size and related estimators. Journal of Educational Statistics, 6(2), 107–128.",
    "yusuf1985": "Yusuf, S., Peto, R., Lewis, J., Collins, R., & Sleight, P. (1985). Beta blockade during and after myocardial infarction: an overview of the randomized trials. Progress in Cardiovascular Diseases, 27(5), 335–371.",

    # --- Meta-analysis: publication bias ---
    "egger1997": "Egger, M., Davey Smith, G., Schneider, M., & Minder, C. (1997). Bias in meta-analysis detected by a simple, graphical test. BMJ, 315(7109), 629–634.",
    "begg1994": "Begg, C. B., & Mazumdar, M. (1994). Operating characteristics of a rank correlation test for publication bias. Biometrics, 50(4), 1088–1101.",
    "duval2000": "Duval, S., & Tweedie, R. (2000). Trim and fill: a simple funnel-plot-based method of testing and adjusting for publication bias in meta-analysis. Biometrics, 56(2), 455–463.",

    # --- Meta-analysis: extensions ---
    "thompson2002": "Thompson, S. G., & Higgins, J. P. T. (2002). How should meta-regression analyses be undertaken and interpreted? Statistics in Medicine, 21(11), 1559–1573.",
    "lau1992": "Lau, J., Antman, E. M., Jimenez-Silva, J., et al. (1992). Cumulative meta-analysis of therapeutic trials for myocardial infarction. New England Journal of Medicine, 327(4), 248–254.",

    # --- Diagnostic accuracy ---
    "altman1994": "Altman, D. G., & Bland, J. M. (1994). Diagnostic tests 1: sensitivity and specificity. BMJ, 308(6943), 1552.",
    "deeks2004": "Deeks, J. J., & Altman, D. G. (2004). Diagnostic tests 4: likelihood ratios. BMJ, 329(7458), 168–169.",
    "wilson1927": "Wilson, E. B. (1927). Probable inference, the law of succession, and statistical inference. Journal of the American Statistical Association, 22(158), 209–212.",
}


def ref(key: str) -> str | None:
    """Return the full reference for a method key, or None if unknown."""
    return _REFS.get(key)


def refs(keys: list[str]) -> list[str]:
    """Return the references for a list of keys (unknown keys skipped, de-duped)."""
    out: list[str] = []
    for k in keys:
        r = _REFS.get(k)
        if r and r not in out:
            out.append(r)
    return out
