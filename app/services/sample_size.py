"""Sample-size / power calculations for the common study designs.

A self-contained calculator (no data upload, no AI) used by the free tool. Each
function solves for the required sample size given effect size, alpha, and power.
Uses statsmodels where available; correlation uses the standard Fisher-z formula.
"""

from __future__ import annotations

import math

import numpy as np
from scipy import stats
from statsmodels.stats.power import FTestAnovaPower, NormalIndPower, TTestIndPower
from statsmodels.stats.proportion import proportion_effectsize


class SampleSizeError(ValueError):
    """Invalid inputs for a sample-size calculation."""


def _check(alpha: float, power: float) -> None:
    if not (0 < alpha < 1):
        raise SampleSizeError("alpha must be between 0 and 1 (e.g. 0.05).")
    if not (0 < power < 1):
        raise SampleSizeError("power must be between 0 and 1 (e.g. 0.80).")


def two_means(effect_size: float, alpha: float = 0.05, power: float = 0.80,
              ratio: float = 1.0, alternative: str = "two-sided") -> dict:
    """Two-sample t-test: n per group for a given Cohen's d."""
    _check(alpha, power)
    if effect_size == 0:
        raise SampleSizeError("Effect size (Cohen's d) cannot be 0.")
    n1 = TTestIndPower().solve_power(
        effect_size=abs(effect_size), alpha=alpha, power=power, ratio=ratio,
        alternative=alternative,
    )
    n1 = int(math.ceil(n1))
    n2 = int(math.ceil(n1 * ratio))
    return {"design": "two_means", "n_group1": n1, "n_group2": n2, "total": n1 + n2,
            "inputs": {"effect_size": effect_size, "alpha": alpha, "power": power,
                       "ratio": ratio, "alternative": alternative}}


def two_proportions(p1: float, p2: float, alpha: float = 0.05, power: float = 0.80,
                    ratio: float = 1.0, alternative: str = "two-sided") -> dict:
    """Two independent proportions: n per group."""
    _check(alpha, power)
    for p in (p1, p2):
        if not (0 <= p <= 1):
            raise SampleSizeError("Proportions must be between 0 and 1.")
    if p1 == p2:
        raise SampleSizeError("The two proportions must differ.")
    es = proportion_effectsize(p1, p2)
    n1 = NormalIndPower().solve_power(
        effect_size=abs(es), alpha=alpha, power=power, ratio=ratio, alternative=alternative
    )
    n1 = int(math.ceil(n1))
    n2 = int(math.ceil(n1 * ratio))
    return {"design": "two_proportions", "n_group1": n1, "n_group2": n2, "total": n1 + n2,
            "inputs": {"p1": p1, "p2": p2, "alpha": alpha, "power": power,
                       "ratio": ratio, "alternative": alternative}}


def anova(effect_size: float, k_groups: int, alpha: float = 0.05, power: float = 0.80) -> dict:
    """One-way ANOVA: total N and per-group n for Cohen's f."""
    _check(alpha, power)
    if k_groups < 2:
        raise SampleSizeError("ANOVA needs at least 2 groups.")
    if effect_size <= 0:
        raise SampleSizeError("Effect size (Cohen's f) must be > 0.")
    n_total = FTestAnovaPower().solve_power(
        effect_size=effect_size, k_groups=k_groups, alpha=alpha, power=power
    )
    per = int(math.ceil(n_total / k_groups))
    return {"design": "anova", "k_groups": k_groups, "n_per_group": per,
            "total": per * k_groups,
            "inputs": {"effect_size": effect_size, "alpha": alpha, "power": power}}


def correlation(r: float, alpha: float = 0.05, power: float = 0.80,
                alternative: str = "two-sided") -> dict:
    """Pearson correlation: total N for a given r (Fisher-z approximation)."""
    _check(alpha, power)
    if not (-1 < r < 1) or r == 0:
        raise SampleSizeError("Correlation r must be between -1 and 1 and not 0.")
    z_a = stats.norm.ppf(1 - alpha / 2) if alternative == "two-sided" else stats.norm.ppf(1 - alpha)
    z_b = stats.norm.ppf(power)
    c = 0.5 * math.log((1 + abs(r)) / (1 - abs(r)))
    n = ((z_a + z_b) / c) ** 2 + 3
    n = int(math.ceil(n))
    return {"design": "correlation", "total": n,
            "inputs": {"r": r, "alpha": alpha, "power": power, "alternative": alternative}}


def calculate(design: str, params: dict) -> dict:
    """Dispatch a calculation by design name."""
    try:
        if design == "two_means":
            return two_means(**params)
        if design == "two_proportions":
            return two_proportions(**params)
        if design == "anova":
            return anova(**params)
        if design == "correlation":
            return correlation(**params)
    except TypeError as exc:
        raise SampleSizeError(f"Missing or invalid parameters: {exc}") from exc
    raise SampleSizeError(f"Unknown design: {design}")
