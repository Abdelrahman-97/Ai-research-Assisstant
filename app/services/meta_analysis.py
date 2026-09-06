"""Meta-analysis engine.

Pools study-level effect sizes with fixed-effect (inverse-variance) and
random-effects (DerSimonian-Laird) models, reports heterogeneity (Q, df, p, I2,
tau2), leave-one-out sensitivity analysis, and optional subgroup analysis.

Each study provides an effect size (`effect`) and its precision as either a
standard error (`se`) or a `variance`. For ratio measures (OR, RR, HR) pass the
effect on the log scale; the caller can exponentiate for display.
"""

from __future__ import annotations

import math

from scipy import stats


class MetaAnalysisError(ValueError):
    """Invalid meta-analysis inputs."""


def _prep(studies: list[dict]) -> list[dict]:
    out = []
    for i, s in enumerate(studies):
        name = str(s.get("name") or f"Study {i + 1}")
        if s.get("effect") is None:
            raise MetaAnalysisError(f"{name}: missing effect size.")
        yi = float(s["effect"])
        if s.get("se") is not None:
            se = float(s["se"])
            vi = se * se
        elif s.get("variance") is not None:
            vi = float(s["variance"])
            se = math.sqrt(vi) if vi >= 0 else float("nan")
        else:
            raise MetaAnalysisError(f"{name}: provide se or variance.")
        if vi <= 0:
            raise MetaAnalysisError(f"{name}: variance/se must be > 0.")
        out.append({"name": name, "yi": yi, "vi": vi, "se": se,
                    "group": s.get("group")})
    if len(out) < 2:
        raise MetaAnalysisError("Meta-analysis needs at least 2 studies.")
    return out


def _pool(items: list[dict]) -> dict:
    """Fixed + random effects pooling and heterogeneity for a set of studies."""
    k = len(items)
    w = [1.0 / it["vi"] for it in items]
    sw = sum(w)
    fixed = sum(wi * it["yi"] for wi, it in zip(w, items)) / sw
    q = sum(wi * (it["yi"] - fixed) ** 2 for wi, it in zip(w, items))
    df = k - 1
    c = sw - sum(wi ** 2 for wi in w) / sw
    tau2 = max(0.0, (q - df) / c) if c > 0 else 0.0
    i2 = max(0.0, (q - df) / q) * 100 if q > 0 else 0.0
    q_p = float(1 - stats.chi2.cdf(q, df)) if df > 0 else None

    wr = [1.0 / (it["vi"] + tau2) for it in items]
    swr = sum(wr)
    random = sum(wi * it["yi"] for wi, it in zip(wr, items)) / swr

    def _ci(est, var):
        se = math.sqrt(var)
        lo, hi = est - 1.96 * se, est + 1.96 * se
        z = est / se if se else None
        p = float(2 * (1 - stats.norm.cdf(abs(z)))) if z is not None else None
        return {"estimate": round(est, 4), "se": round(se, 4),
                "ci_low": round(lo, 4), "ci_high": round(hi, 4),
                "z": round(z, 4) if z is not None else None,
                "p_value": p}

    return {
        "k": k,
        "fixed": _ci(fixed, 1.0 / sw),
        "random": _ci(random, 1.0 / swr),
        "heterogeneity": {
            "Q": round(q, 4), "df": df,
            "p_value": q_p,
            "I2_percent": round(i2, 1),
            "tau2": round(tau2, 4),
        },
    }


def _leave_one_out(items: list[dict]) -> list[dict]:
    out = []
    for i in range(len(items)):
        subset = items[:i] + items[i + 1:]
        if len(subset) < 2:
            continue
        r = _pool(subset)["random"]
        out.append({"omitted": items[i]["name"], **r})
    return out


def analyze(studies: list[dict], *, model: str = "random",
            subgroups: bool = True) -> dict:
    """Run the full meta-analysis."""
    items = _prep(studies)
    result = _pool(items)

    result["studies"] = [
        {"name": it["name"], "effect": round(it["yi"], 4), "se": round(it["se"], 4),
         "ci_low": round(it["yi"] - 1.96 * it["se"], 4),
         "ci_high": round(it["yi"] + 1.96 * it["se"], 4),
         "weight_pct": None, "group": it["group"]}
        for it in items
    ]
    # inverse-variance weights (%) for the chosen model
    tau2 = result["heterogeneity"]["tau2"] if model == "random" else 0.0
    w = [1.0 / (it["vi"] + tau2) for it in items]
    sw = sum(w)
    for st, wi in zip(result["studies"], w):
        st["weight_pct"] = round(100 * wi / sw, 1)

    result["model"] = model
    result["leave_one_out"] = _leave_one_out(items)

    if subgroups and any(it["group"] for it in items):
        groups: dict[str, list[dict]] = {}
        for it in items:
            g = it["group"] or "(none)"
            groups.setdefault(g, []).append(it)
        result["subgroups"] = {
            g: _pool(gi) for g, gi in groups.items() if len(gi) >= 2
        }
    return result
