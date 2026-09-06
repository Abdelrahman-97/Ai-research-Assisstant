"""Diagnostic-test accuracy statistics from a 2x2 table.

Given true/false positives and negatives, computes sensitivity, specificity,
PPV, NPV, accuracy, likelihood ratios, the diagnostic odds ratio, and prevalence,
with Wilson 95% confidence intervals for the proportion measures. Self-contained
(no data upload, no AI) — used by the free diagnostic calculator.
"""

from __future__ import annotations

import math


class DiagnosticError(ValueError):
    """Invalid 2x2 inputs."""


def _wilson(k: int, n: int, z: float = 1.96) -> tuple[float | None, float | None]:
    """Wilson score interval for a proportion k/n."""
    if n == 0:
        return None, None
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def _prop(k: int, n: int) -> dict:
    val = (k / n) if n else None
    lo, hi = _wilson(k, n)
    return {
        "value": round(val, 4) if val is not None else None,
        "ci_low": round(lo, 4) if lo is not None else None,
        "ci_high": round(hi, 4) if hi is not None else None,
    }


def accuracy_2x2(tp: int, fp: int, fn: int, tn: int) -> dict:
    """Compute diagnostic accuracy metrics from a 2x2 table."""
    for name, v in (("TP", tp), ("FP", fp), ("FN", fn), ("TN", tn)):
        if v < 0:
            raise DiagnosticError(f"{name} cannot be negative.")
    n = tp + fp + fn + tn
    if n == 0:
        raise DiagnosticError("All counts are zero — nothing to compute.")

    sens = _prop(tp, tp + fn)
    spec = _prop(tn, tn + fp)
    ppv = _prop(tp, tp + fp)
    npv = _prop(tn, tn + fn)
    acc = _prop(tp + tn, n)
    prev = _prop(tp + fn, n)

    def _ratio(num, den):
        return round(num / den, 4) if den not in (0, None) else None

    se = sens["value"]
    sp = spec["value"]
    lr_pos = _ratio(se, (1 - sp)) if se is not None and sp is not None else None
    lr_neg = _ratio((1 - se), sp) if se is not None and sp is not None else None
    dor = _ratio(lr_pos, lr_neg) if lr_pos and lr_neg else None

    return {
        "counts": {"tp": tp, "fp": fp, "fn": fn, "tn": tn, "n": n},
        "sensitivity": sens,
        "specificity": spec,
        "ppv": ppv,
        "npv": npv,
        "accuracy": acc,
        "prevalence": prev,
        "lr_positive": lr_pos,
        "lr_negative": lr_neg,
        "diagnostic_or": dor,
    }
