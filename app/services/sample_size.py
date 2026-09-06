"""Comprehensive sample-size / power calculations.

Each design can solve for the required sample size (given effect, alpha, power)
or for the achieved power (given n). Optional drop-out inflation adjusts the final
enrolment. Every result carries a real methodological citation.

Self-contained: no data upload, no AI. Used by the free tool and (later) the paid
pipeline.
"""

from __future__ import annotations

import math

from scipy import stats
from statsmodels.stats.power import (
    FTestAnovaPower,
    GofChisquarePower,
    NormalIndPower,
    TTestIndPower,
    TTestPower,
)
from statsmodels.stats.proportion import proportion_effectsize

from app.services import citations


class SampleSizeError(ValueError):
    """Invalid inputs for a sample-size calculation."""


def _check(alpha: float, power: float | None, need_power: bool = True) -> None:
    if not (0 < alpha < 1):
        raise SampleSizeError("alpha must be between 0 and 1 (e.g. 0.05).")
    if need_power and (power is None or not (0 < power < 1)):
        raise SampleSizeError("power must be between 0 and 1 (e.g. 0.80).")


def _ceil(x: float) -> int:
    return int(math.ceil(x))


def _dropout(n: int, dropout: float) -> int:
    if dropout and 0 < dropout < 1:
        return _ceil(n / (1 - dropout))
    return n


def _z(alpha: float, alternative: str) -> float:
    return stats.norm.ppf(1 - alpha / 2) if alternative == "two-sided" else stats.norm.ppf(1 - alpha)


# --------------------------------------------------------------------------- #
# Designs. Each returns a dict; when solve="power", `power` is computed from n.
# --------------------------------------------------------------------------- #
def two_means(effect_size=None, alpha=0.05, power=0.80, ratio=1.0,
              alternative="two-sided", solve="n", nobs1=None, dropout=0.0) -> dict:
    """Independent two-sample t-test (Cohen's d)."""
    if not effect_size:
        raise SampleSizeError("Effect size (Cohen's d) is required and cannot be 0.")
    eng = TTestIndPower()
    if solve == "power":
        if not nobs1:
            raise SampleSizeError("Provide nobs1 (group-1 size) to solve for power.")
        _check(alpha, None, need_power=False)
        pw = eng.power(effect_size=abs(effect_size), nobs1=nobs1, alpha=alpha,
                       ratio=ratio, alternative=alternative)
        return {"design": "two_means", "solve": "power", "power": round(float(pw), 4),
                "inputs": {"effect_size": effect_size, "alpha": alpha, "nobs1": nobs1,
                           "ratio": ratio, "alternative": alternative},
                "references": citations.refs(["cohen1988"])}
    _check(alpha, power)
    n1 = _ceil(eng.solve_power(effect_size=abs(effect_size), alpha=alpha, power=power,
                               ratio=ratio, alternative=alternative))
    n2 = _ceil(n1 * ratio)
    return {"design": "two_means", "solve": "n", "n_group1": _dropout(n1, dropout),
            "n_group2": _dropout(n2, dropout), "total": _dropout(n1, dropout) + _dropout(n2, dropout),
            "inputs": {"effect_size": effect_size, "alpha": alpha, "power": power,
                       "ratio": ratio, "alternative": alternative, "dropout": dropout},
            "references": citations.refs(["cohen1988"])}


def paired_means(effect_size=None, alpha=0.05, power=0.80, alternative="two-sided",
                 solve="n", nobs=None, dropout=0.0) -> dict:
    """Paired / one-sample t-test on the differences (Cohen's dz)."""
    if not effect_size:
        raise SampleSizeError("Effect size (dz) is required and cannot be 0.")
    eng = TTestPower()
    if solve == "power":
        if not nobs:
            raise SampleSizeError("Provide nobs to solve for power.")
        _check(alpha, None, need_power=False)
        pw = eng.power(effect_size=abs(effect_size), nobs=nobs, alpha=alpha, alternative=alternative)
        return {"design": "paired_means", "solve": "power", "power": round(float(pw), 4),
                "inputs": {"effect_size": effect_size, "alpha": alpha, "nobs": nobs,
                           "alternative": alternative}, "references": citations.refs(["cohen1988"])}
    _check(alpha, power)
    n = _ceil(eng.solve_power(effect_size=abs(effect_size), alpha=alpha, power=power,
                              alternative=alternative))
    return {"design": "paired_means", "solve": "n", "n_pairs": _dropout(n, dropout),
            "total": _dropout(n, dropout),
            "inputs": {"effect_size": effect_size, "alpha": alpha, "power": power,
                       "alternative": alternative, "dropout": dropout},
            "references": citations.refs(["cohen1988"])}


def one_mean(effect_size=None, alpha=0.05, power=0.80, alternative="two-sided",
             solve="n", nobs=None, dropout=0.0) -> dict:
    """One-sample t-test vs a reference value (Cohen's d)."""
    r = paired_means(effect_size=effect_size, alpha=alpha, power=power,
                     alternative=alternative, solve=solve, nobs=nobs, dropout=dropout)
    r["design"] = "one_mean"
    if "n_pairs" in r:
        r["n"] = r.pop("n_pairs")
    return r


def two_proportions(p1=None, p2=None, alpha=0.05, power=0.80, ratio=1.0,
                    alternative="two-sided", solve="n", nobs1=None, dropout=0.0) -> dict:
    """Two independent proportions."""
    for p in (p1, p2):
        if p is None or not (0 <= p <= 1):
            raise SampleSizeError("Proportions must be between 0 and 1.")
    if p1 == p2:
        raise SampleSizeError("The two proportions must differ.")
    es = proportion_effectsize(p1, p2)
    eng = NormalIndPower()
    if solve == "power":
        if not nobs1:
            raise SampleSizeError("Provide nobs1 to solve for power.")
        _check(alpha, None, need_power=False)
        pw = eng.power(effect_size=abs(es), nobs1=nobs1, alpha=alpha, ratio=ratio,
                       alternative=alternative)
        return {"design": "two_proportions", "solve": "power", "power": round(float(pw), 4),
                "inputs": {"p1": p1, "p2": p2, "alpha": alpha, "nobs1": nobs1, "ratio": ratio},
                "references": citations.refs(["fleiss2003", "cohen1988"])}
    _check(alpha, power)
    n1 = _ceil(eng.solve_power(effect_size=abs(es), alpha=alpha, power=power, ratio=ratio,
                               alternative=alternative))
    n2 = _ceil(n1 * ratio)
    return {"design": "two_proportions", "solve": "n", "n_group1": _dropout(n1, dropout),
            "n_group2": _dropout(n2, dropout), "total": _dropout(n1, dropout) + _dropout(n2, dropout),
            "inputs": {"p1": p1, "p2": p2, "alpha": alpha, "power": power, "ratio": ratio,
                       "alternative": alternative, "dropout": dropout},
            "references": citations.refs(["fleiss2003", "cohen1988"])}


def one_proportion(p1=None, p0=None, alpha=0.05, power=0.80, alternative="two-sided",
                   dropout=0.0) -> dict:
    """One proportion vs a reference value (normal approximation)."""
    for p in (p1, p0):
        if p is None or not (0 < p < 1):
            raise SampleSizeError("Proportions must be strictly between 0 and 1.")
    if p1 == p0:
        raise SampleSizeError("The proportions must differ.")
    _check(alpha, power)
    za = _z(alpha, alternative)
    zb = stats.norm.ppf(power)
    num = za * math.sqrt(p0 * (1 - p0)) + zb * math.sqrt(p1 * (1 - p1))
    n = _ceil((num / (p1 - p0)) ** 2)
    return {"design": "one_proportion", "solve": "n", "n": _dropout(n, dropout),
            "total": _dropout(n, dropout),
            "inputs": {"p1": p1, "p0": p0, "alpha": alpha, "power": power,
                       "alternative": alternative, "dropout": dropout},
            "references": citations.refs(["fleiss2003"])}


def anova(effect_size=None, k_groups=None, alpha=0.05, power=0.80, solve="n",
          nobs=None, dropout=0.0) -> dict:
    """One-way ANOVA (Cohen's f)."""
    if not k_groups or k_groups < 2:
        raise SampleSizeError("ANOVA needs at least 2 groups.")
    if not effect_size or effect_size <= 0:
        raise SampleSizeError("Effect size (Cohen's f) must be > 0.")
    eng = FTestAnovaPower()
    if solve == "power":
        if not nobs:
            raise SampleSizeError("Provide total nobs to solve for power.")
        _check(alpha, None, need_power=False)
        pw = eng.power(effect_size=effect_size, nobs=nobs, alpha=alpha, k_groups=k_groups)
        return {"design": "anova", "solve": "power", "power": round(float(pw), 4),
                "inputs": {"effect_size": effect_size, "k_groups": k_groups, "alpha": alpha,
                           "nobs": nobs}, "references": citations.refs(["cohen1988"])}
    _check(alpha, power)
    n_total = eng.solve_power(effect_size=effect_size, k_groups=k_groups, alpha=alpha, power=power)
    per = _ceil(n_total / k_groups)
    return {"design": "anova", "solve": "n", "k_groups": k_groups,
            "n_per_group": _dropout(per, dropout), "total": _dropout(per, dropout) * k_groups,
            "inputs": {"effect_size": effect_size, "alpha": alpha, "power": power, "dropout": dropout},
            "references": citations.refs(["cohen1988"])}


def correlation(r=None, alpha=0.05, power=0.80, alternative="two-sided", dropout=0.0) -> dict:
    """Pearson correlation (Fisher-z)."""
    if r is None or not (-1 < r < 1) or r == 0:
        raise SampleSizeError("Correlation r must be between -1 and 1 and not 0.")
    _check(alpha, power)
    za = _z(alpha, alternative)
    zb = stats.norm.ppf(power)
    c = 0.5 * math.log((1 + abs(r)) / (1 - abs(r)))
    n = _ceil(((za + zb) / c) ** 2 + 3)
    return {"design": "correlation", "solve": "n", "n": _dropout(n, dropout),
            "total": _dropout(n, dropout),
            "inputs": {"r": r, "alpha": alpha, "power": power, "alternative": alternative,
                       "dropout": dropout},
            "references": citations.refs(["cohen1988", "fisher1921"])}


def chi_square(effect_size=None, df=None, alpha=0.05, power=0.80, solve="n",
               nobs=None, dropout=0.0) -> dict:
    """Chi-square goodness-of-fit / independence (Cohen's w)."""
    if not effect_size or effect_size <= 0:
        raise SampleSizeError("Effect size (Cohen's w) must be > 0.")
    if not df or df < 1:
        raise SampleSizeError("Degrees of freedom must be >= 1.")
    eng = GofChisquarePower()
    if solve == "power":
        if not nobs:
            raise SampleSizeError("Provide nobs to solve for power.")
        _check(alpha, None, need_power=False)
        pw = eng.power(effect_size=effect_size, nobs=nobs, alpha=alpha, n_bins=df + 1)
        return {"design": "chi_square", "solve": "power", "power": round(float(pw), 4),
                "inputs": {"effect_size": effect_size, "df": df, "alpha": alpha, "nobs": nobs},
                "references": citations.refs(["cohen1988"])}
    _check(alpha, power)
    n = _ceil(eng.solve_power(effect_size=effect_size, alpha=alpha, power=power, n_bins=df + 1))
    return {"design": "chi_square", "solve": "n", "n": _dropout(n, dropout),
            "total": _dropout(n, dropout),
            "inputs": {"effect_size": effect_size, "df": df, "alpha": alpha, "power": power,
                       "dropout": dropout},
            "references": citations.refs(["cohen1988"])}


def survival(hazard_ratio=None, alpha=0.05, power=0.80, allocation=0.5,
             event_probability=None, dropout=0.0) -> dict:
    """Survival / log-rank: required number of events (Schoenfeld), and total N
    if an overall event probability is given."""
    if not hazard_ratio or hazard_ratio <= 0 or hazard_ratio == 1:
        raise SampleSizeError("Hazard ratio must be > 0 and not equal to 1.")
    if not (0 < allocation < 1):
        raise SampleSizeError("Allocation proportion must be between 0 and 1.")
    _check(alpha, power)
    za = stats.norm.ppf(1 - alpha / 2)
    zb = stats.norm.ppf(power)
    lnhr = math.log(hazard_ratio)
    events = _ceil(((za + zb) ** 2) / (allocation * (1 - allocation) * lnhr ** 2))
    out = {"design": "survival", "solve": "n", "events_required": events,
           "inputs": {"hazard_ratio": hazard_ratio, "alpha": alpha, "power": power,
                      "allocation": allocation, "event_probability": event_probability,
                      "dropout": dropout},
           "references": citations.refs(["schoenfeld1983"])}
    if event_probability and 0 < event_probability <= 1:
        total = _ceil(events / event_probability)
        out["total"] = _dropout(total, dropout)
    return out


def regression(effect_size=None, n_predictors=None, alpha=0.05, power=0.80, dropout=0.0) -> dict:
    """Multiple linear regression: total N for a given Cohen's f² and #predictors."""
    if not effect_size or effect_size <= 0:
        raise SampleSizeError("Effect size (Cohen's f²) must be > 0.")
    if not n_predictors or n_predictors < 1:
        raise SampleSizeError("Number of predictors must be >= 1.")
    _check(alpha, power)
    k = int(n_predictors)
    n = k + 2
    while n < 1_000_000:
        df2 = n - k - 1
        if df2 > 0:
            fcrit = stats.f.ppf(1 - alpha, k, df2)
            pw = 1 - stats.ncf.cdf(fcrit, k, df2, effect_size * n)
            if pw >= power:
                break
        n += 1
    return {"design": "regression", "solve": "n", "n_predictors": k,
            "total": _dropout(n, dropout),
            "inputs": {"effect_size": effect_size, "alpha": alpha, "power": power,
                       "dropout": dropout},
            "references": citations.refs(["cohen1988"])}


_DISPATCH = {
    "two_means": two_means, "paired_means": paired_means, "one_mean": one_mean,
    "two_proportions": two_proportions, "one_proportion": one_proportion,
    "anova": anova, "correlation": correlation, "chi_square": chi_square,
    "survival": survival, "regression": regression,
}


def designs() -> list[str]:
    return list(_DISPATCH)


def calculate(design: str, params: dict) -> dict:
    """Dispatch a calculation by design name."""
    fn = _DISPATCH.get(design)
    if not fn:
        raise SampleSizeError(f"Unknown design: {design}")
    try:
        return fn(**params)
    except TypeError as exc:
        raise SampleSizeError(f"Missing or invalid parameters: {exc}") from exc
