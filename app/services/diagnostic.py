"""Diagnostic-test accuracy statistics from a 2x2 table.

Given true/false positives and negatives, computes sensitivity, specificity,
PPV, NPV, accuracy, likelihood ratios, the diagnostic odds ratio, and prevalence,
with Wilson 95% confidence intervals for the proportion measures. Self-contained
(no data upload, no AI) — used by the free diagnostic calculator.
"""

from __future__ import annotations

import math

import numpy as np
from scipy import stats


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


def roc_auc(pairs: list, higher_is_positive: bool = True) -> dict:
    """ROC curve + AUC (with 95% CI) from raw (score, outcome) pairs.

    `pairs` is a list of [score, label] where label is 1 (has the condition) or
    0 (does not). Returns AUC (Hanley-McNeil CI), the ROC points, and the
    Youden-optimal cutoff with the full 2x2 accuracy metrics at that cutoff.
    """
    scores, labels = [], []
    for row in pairs:
        try:
            s = float(row[0]); y = int(row[1])
        except (TypeError, ValueError, IndexError):
            continue
        if y in (0, 1):
            scores.append(s); labels.append(y)
    scores = np.array(scores, float)
    labels = np.array(labels, int)
    if not higher_is_positive:
        scores = -scores
    n_pos = int((labels == 1).sum())
    n_neg = int((labels == 0).sum())
    if n_pos == 0 or n_neg == 0:
        raise DiagnosticError("Need at least one positive and one negative outcome.")

    # AUC via the Mann-Whitney rank statistic (handles ties).
    ranks = stats.rankdata(scores)
    auc = (ranks[labels == 1].sum() - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg)
    # Hanley-McNeil standard error.
    q1 = auc / (2 - auc)
    q2 = 2 * auc * auc / (1 + auc)
    se = math.sqrt((auc * (1 - auc) + (n_pos - 1) * (q1 - auc * auc)
                    + (n_neg - 1) * (q2 - auc * auc)) / (n_pos * n_neg))
    lo, hi = max(0.0, auc - 1.96 * se), min(1.0, auc + 1.96 * se)

    # ROC points + Youden's J across candidate thresholds.
    thresholds = np.unique(scores)[::-1]
    points = [{"fpr": 0.0, "tpr": 0.0}]
    best = {"J": -1, "cutoff": None, "tp": 0, "fp": 0, "fn": 0, "tn": 0}
    for t in thresholds:
        pred = scores >= t
        tp = int(((pred) & (labels == 1)).sum())
        fp = int(((pred) & (labels == 0)).sum())
        fn = n_pos - tp
        tn = n_neg - fp
        tpr = tp / n_pos
        fpr = fp / n_neg
        points.append({"fpr": round(fpr, 4), "tpr": round(tpr, 4)})
        j = tpr - fpr
        if j > best["J"]:
            cut = t if higher_is_positive else -t
            best = {"J": j, "cutoff": round(float(cut), 4), "tp": tp, "fp": fp, "fn": fn, "tn": tn}
    points.append({"fpr": 1.0, "tpr": 1.0})

    at_cut = accuracy_2x2(best["tp"], best["fp"], best["fn"], best["tn"])
    return {
        "n": n_pos + n_neg, "n_positive": n_pos, "n_negative": n_neg,
        "auc": round(float(auc), 4), "auc_se": round(float(se), 4),
        "auc_ci_low": round(float(lo), 4), "auc_ci_high": round(float(hi), 4),
        "youden_cutoff": best["cutoff"], "at_optimal_cutoff": at_cut,
        "roc_points": points,
        "higher_is_positive": higher_is_positive,
    }


def roc_plot(result: dict, path: str) -> str:
    """Draw the ROC curve from a roc_auc() result."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    pts = result["roc_points"]
    fpr = [p["fpr"] for p in pts]
    tpr = [p["tpr"] for p in pts]
    fig, ax = plt.subplots(figsize=(5.4, 5))
    ax.plot(fpr, tpr, color="#0a6b63", lw=2, zorder=3)
    ax.plot([0, 1], [0, 1], color="#9aa7a9", ls="--", lw=1, zorder=1)
    ax.set_xlabel("1 − specificity (false-positive rate)")
    ax.set_ylabel("Sensitivity (true-positive rate)")
    ax.set_title(f"ROC curve (AUC = {result['auc']:.3f})")
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    plt.tight_layout()
    plt.savefig(path, dpi=130)
    plt.close()
    return path
