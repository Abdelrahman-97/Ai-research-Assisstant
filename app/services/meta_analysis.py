"""Comprehensive meta-analysis engine.

Effect measures (computed from raw data or supplied generically):
  generic (effect + SE), md, smd (Hedges g), or, rr, rd, peto, fisher_z (r),
  proportion (logit), hr (log-HR + SE).

Models: fixed (common) effect and random effects with DerSimonian-Laird (DL),
Paule-Mandel (PM), or REML tau^2 estimators; optional Hartung-Knapp (HKSJ)
confidence intervals; prediction intervals.

Also: heterogeneity (Q, df, p, I2, H2, tau2), subgroup analysis with a test for
subgroup differences, meta-regression, cumulative meta-analysis, leave-one-out
sensitivity, and publication-bias assessment (Egger's test, Begg's test,
trim-and-fill). Every method carries a real citation.

Ratio measures (or, rr, peto, hr) and fisher_z / proportion are pooled on their
transform scale; back-transformed estimates are added for display.
"""

from __future__ import annotations

import math

import numpy as np
from scipy import stats

from app.services import citations

Z = 1.959963984540054  # qnorm(0.975)


class MetaAnalysisError(ValueError):
    """Invalid meta-analysis inputs."""


# --------------------------------------------------------------------------- #
# Effect-size computation
# --------------------------------------------------------------------------- #
_LOG_MEASURES = {"or", "rr", "peto", "hr"}
_TRANSFORM = {
    "or": ("exp", "OR"), "rr": ("exp", "RR"), "peto": ("exp", "Peto OR"),
    "hr": ("exp", "HR"), "fisher_z": ("tanh", "r"), "proportion": ("expit", "proportion"),
    "md": (None, "MD"), "smd": (None, "SMD (Hedges g)"), "rd": (None, "RD"),
    "generic": (None, "effect"),
}


def _cc(a, b, c, d):
    """Continuity correction: add 0.5 to all cells if any is zero."""
    if 0 in (a, b, c, d):
        return a + 0.5, b + 0.5, c + 0.5, d + 0.5
    return a, b, c, d


def _effect(measure: str, s: dict) -> tuple[float, float]:
    """Return (yi, vi) for one study under the chosen measure."""
    g = s.get
    if measure == "generic":
        if g("effect") is None:
            raise MetaAnalysisError("Missing effect size.")
        yi = float(s["effect"])
        if g("se") is not None:
            vi = float(s["se"]) ** 2
        elif g("variance") is not None:
            vi = float(s["variance"])
        else:
            raise MetaAnalysisError("Provide se or variance.")
        return yi, vi
    if measure == "hr":
        # log-HR supplied as effect (already log) + se, or hr + ci
        if g("effect") is not None and g("se") is not None:
            return float(s["effect"]), float(s["se"]) ** 2
        raise MetaAnalysisError("For HR provide log-HR as 'effect' and its 'se'.")
    if measure in ("md", "smd"):
        n1, m1, sd1 = float(s["n1"]), float(s["m1"]), float(s["sd1"])
        n2, m2, sd2 = float(s["n2"]), float(s["m2"]), float(s["sd2"])
        if measure == "md":
            return m1 - m2, sd1 ** 2 / n1 + sd2 ** 2 / n2
        sp = math.sqrt(((n1 - 1) * sd1 ** 2 + (n2 - 1) * sd2 ** 2) / (n1 + n2 - 2))
        d = (m1 - m2) / sp
        J = 1 - 3 / (4 * (n1 + n2) - 9)
        gg = J * d
        vi = (n1 + n2) / (n1 * n2) + gg ** 2 / (2 * (n1 + n2 - 2))
        return gg, vi
    if measure in ("or", "rr", "rd", "peto"):
        e1, n1, e2, n2 = float(s["e1"]), float(s["n1"]), float(s["e2"]), float(s["n2"])
        a, b, c, d = e1, n1 - e1, e2, n2 - e2
        if measure == "peto":
            # Peto one-step OR (log scale)
            N = n1 + n2
            O = a
            E = n1 * (a + c) / N
            V = (n1 * n2 * (a + c) * (b + d)) / (N * N * (N - 1)) if N > 1 else float("nan")
            if V <= 0:
                raise MetaAnalysisError("Peto OR undefined (zero variance).")
            return (O - E) / V, 1.0 / V
        a, b, c, d = _cc(a, b, c, d)
        if measure == "or":
            return math.log((a * d) / (b * c)), 1 / a + 1 / b + 1 / c + 1 / d
        if measure == "rr":
            return math.log((a / (a + b)) / (c / (c + d))), 1 / a - 1 / (a + b) + 1 / c - 1 / (c + d)
        # rd
        r1, r2 = a / (a + b), c / (c + d)
        return r1 - r2, r1 * (1 - r1) / (a + b) + r2 * (1 - r2) / (c + d)
    if measure == "fisher_z":
        r, n = float(s["r"]), float(s["n"])
        if not (-1 < r < 1):
            raise MetaAnalysisError("r must be between -1 and 1.")
        return 0.5 * math.log((1 + r) / (1 - r)), 1 / (n - 3)
    if measure == "proportion":
        e, n = float(s["events"]), float(s["total"])
        a, b = e, n - e
        if a == 0 or b == 0:
            a, b = a + 0.5, b + 0.5
        return math.log(a / b), 1 / a + 1 / b
    raise MetaAnalysisError(f"Unknown effect measure: {measure}")


def _prepare(studies: list[dict], measure: str) -> list[dict]:
    items = []
    for i, s in enumerate(studies):
        name = str(s.get("name") or f"Study {i + 1}")
        yi, vi = _effect(measure, s)
        if vi <= 0 or math.isnan(vi):
            raise MetaAnalysisError(f"{name}: non-positive/invalid variance.")
        items.append({"name": name, "yi": yi, "vi": vi, "se": math.sqrt(vi),
                      "group": s.get("group"), "moderator": s.get("moderator"),
                      "sort_key": s.get("year") or s.get("sort_key")})
    if len(items) < 2:
        raise MetaAnalysisError("Meta-analysis needs at least 2 studies.")
    return items


# --------------------------------------------------------------------------- #
# tau^2 estimators
# --------------------------------------------------------------------------- #
def _wmean(yi, w):
    sw = sum(w)
    return sum(wi * y for wi, y in zip(w, yi)) / sw, sw


def _tau2(yi, vi, method="DL"):
    k = len(yi)
    wf = [1 / v for v in vi]
    mu_f, sw = _wmean(yi, wf)
    q = sum(wfi * (y - mu_f) ** 2 for wfi, y in zip(wf, yi))
    df = k - 1
    method = (method or "DL").upper()
    if method == "DL":
        c = sw - sum(w * w for w in wf) / sw
        return max(0.0, (q - df) / c) if c > 0 else 0.0, q, df
    if method in ("PM", "REML"):
        # iterate
        t2 = max(0.0, (q - df) / (sw - sum(w * w for w in wf) / sw))  # DL start
        for _ in range(200):
            w = [1 / (v + t2) for v in vi]
            mu, sW = _wmean(yi, w)
            if method == "PM":
                qgen = sum(wi * (y - mu) ** 2 for wi, y in zip(w, yi))
                num = qgen - (k - 1)
                deriv = sum((wi ** 2) * (y - mu) ** 2 for wi, y in zip(w, yi))
                if deriv == 0:
                    break
                step = num / deriv
                new = max(0.0, t2 + step)
            else:  # REML
                sW2 = sum(wi * wi for wi in w)
                num = sum((wi ** 2) * ((y - mu) ** 2 - v) for wi, y, v in zip(w, yi, vi)) + 1 / sW
                new = max(0.0, num / sW2)
            if abs(new - t2) < 1e-8:
                t2 = new
                break
            t2 = new
        return t2, q, df
    raise MetaAnalysisError(f"Unknown tau2 method: {method}")


def _ci_from(est, var, z=Z):
    se = math.sqrt(var)
    lo, hi = est - z * se, est + z * se
    zval = est / se if se else None
    p = float(2 * (1 - stats.norm.cdf(abs(zval)))) if zval is not None else None
    return {"estimate": round(est, 4), "se": round(se, 4), "ci_low": round(lo, 4),
            "ci_high": round(hi, 4), "z": round(zval, 4) if zval is not None else None,
            "p_value": p}


def _pool(items, tau2_method="DL", hksj=False):
    yi = [it["yi"] for it in items]
    vi = [it["vi"] for it in items]
    k = len(items)
    wf = [1 / v for v in vi]
    mu_f, swf = _wmean(yi, wf)
    fixed = _ci_from(mu_f, 1 / swf)

    tau2, q, df = _tau2(yi, vi, tau2_method)
    i2 = max(0.0, (q - df) / q) * 100 if q > 0 else 0.0
    h2 = q / df if df > 0 else None
    q_p = float(1 - stats.chi2.cdf(q, df)) if df > 0 else None

    wr = [1 / (v + tau2) for v in vi]
    mu_r, swr = _wmean(yi, wr)
    if hksj and k >= 2:
        qgen = sum(wi * (y - mu_r) ** 2 for wi, y in zip(wr, yi)) / (k - 1)
        se_r = math.sqrt(qgen / swr)
        tcrit = stats.t.ppf(0.975, k - 1)
        tval = mu_r / se_r if se_r else None
        p = float(2 * (1 - stats.t.cdf(abs(tval), k - 1))) if tval is not None else None
        random = {"estimate": round(mu_r, 4), "se": round(se_r, 4),
                  "ci_low": round(mu_r - tcrit * se_r, 4), "ci_high": round(mu_r + tcrit * se_r, 4),
                  "z": round(tval, 4) if tval is not None else None, "p_value": p,
                  "method": "Hartung-Knapp"}
    else:
        random = _ci_from(mu_r, 1 / swr)
        random["method"] = "Wald"

    # prediction interval (needs k>=3)
    pred = None
    if k >= 3:
        t = stats.t.ppf(0.975, k - 2)
        spread = math.sqrt(tau2 + 1 / swr)
        pred = {"low": round(mu_r - t * spread, 4), "high": round(mu_r + t * spread, 4)}

    return {
        "k": k, "fixed": fixed, "random": random,
        "heterogeneity": {"Q": round(q, 4), "df": df, "p_value": q_p,
                          "I2_percent": round(i2, 1), "H2": round(h2, 3) if h2 else None,
                          "tau2": round(tau2, 4), "tau2_method": tau2_method},
        "prediction_interval": pred,
        "_tau2": tau2,
    }


# --------------------------------------------------------------------------- #
# Publication bias
# --------------------------------------------------------------------------- #
def _egger(items):
    if len(items) < 3:
        return None
    y = np.array([it["yi"] for it in items])
    s = np.array([it["se"] for it in items])
    snd = y / s          # standard normal deviate
    prec = 1 / s
    X = np.column_stack([np.ones_like(prec), prec])
    beta, *_ = np.linalg.lstsq(X, snd, rcond=None)
    resid = snd - X @ beta
    dof = len(y) - 2
    mse = (resid @ resid) / dof
    cov = mse * np.linalg.inv(X.T @ X)
    se_int = math.sqrt(cov[0, 0])
    t = beta[0] / se_int if se_int else None
    p = float(2 * (1 - stats.t.cdf(abs(t), dof))) if t is not None else None
    return {"intercept": round(float(beta[0]), 4), "se": round(se_int, 4),
            "t": round(float(t), 4) if t is not None else None, "p_value": p,
            "reference": citations.ref("egger1997")}


def _begg(items):
    if len(items) < 3:
        return None
    y = np.array([it["yi"] for it in items])
    v = np.array([it["vi"] for it in items])
    mu = np.sum(y / v) / np.sum(1 / v)
    var_star = v - 1 / np.sum(1 / v)
    std = (y - mu) / np.sqrt(np.abs(var_star) + 1e-12)
    tau, p = stats.kendalltau(v, std)
    return {"kendall_tau": round(float(tau), 4), "p_value": round(float(p), 4),
            "reference": citations.ref("begg1994")}


def _trim_fill(items):
    """Duval & Tweedie L0 trim-and-fill (random-ordering L0 estimator)."""
    if len(items) < 3:
        return None
    y = np.array([it["yi"] for it in items], float)
    v = np.array([it["vi"] for it in items], float)

    def pooled(mask):
        w = 1 / v[mask]
        return np.sum(w * y[mask]) / np.sum(w)

    n = len(y)
    L0_prev = -1
    trimmed = 0
    for _ in range(100):
        mu = pooled(np.ones(n, bool))
        centered = y - mu
        order = np.argsort(np.abs(centered))
        ranks = np.empty(n)
        signs = np.sign(centered[order])
        ranks[order] = np.arange(1, n + 1)
        signed_ranks = np.sign(centered) * ranks
        Tn = signed_ranks[centered > 0].sum()
        L0 = (4 * Tn - n * (n + 1)) / (2 * n - 1)
        L0 = max(0, int(round(L0)))
        if L0 == L0_prev:
            break
        L0_prev = L0
        trimmed = L0
    # fill: reflect the L0 most extreme positive-side studies
    mu = pooled(np.ones(n, bool))
    side = 1 if np.sum((y - mu) > 0) >= np.sum((y - mu) < 0) else -1
    extreme = np.argsort(-np.abs(y - mu))[:trimmed]
    filled_y, filled_v = list(y), list(v)
    for idx in extreme:
        filled_y.append(2 * mu - y[idx])
        filled_v.append(v[idx])
    fw = [1 / vv for vv in filled_v]
    adj = sum(w * yy for w, yy in zip(fw, filled_y)) / sum(fw)
    return {"imputed_studies": int(trimmed),
            "adjusted_estimate": round(float(adj), 4),
            "reference": citations.ref("duval2000")}


# --------------------------------------------------------------------------- #
# Meta-regression (moments / DL-based random effects)
# --------------------------------------------------------------------------- #
def _meta_regression(items):
    mods = [it.get("moderator") for it in items]
    if any(m is None for m in mods) or len({m for m in mods}) < 2:
        return None
    y = np.array([it["yi"] for it in items], float)
    v = np.array([it["vi"] for it in items], float)
    x = np.array([float(m) for m in mods], float)
    X = np.column_stack([np.ones_like(x), x])
    k, p = len(y), 2

    def wls(tau2):
        W = np.diag(1 / (v + tau2))
        xtwx_inv = np.linalg.inv(X.T @ W @ X)
        beta = xtwx_inv @ X.T @ W @ y
        return beta, xtwx_inv, W

    beta, _, W = wls(0.0)
    resid = y - X @ beta
    q_res = float(resid.T @ W @ resid)
    # method-of-moments tau2 for residual heterogeneity
    P = W - W @ X @ np.linalg.inv(X.T @ W @ X) @ X.T @ W
    trace = np.trace(P @ np.diag(v))
    tau2 = max(0.0, (q_res - (k - p)) / (np.trace(P))) if np.trace(P) > 0 else 0.0
    beta, xtwx_inv, W = wls(tau2)
    se = np.sqrt(np.diag(xtwx_inv))
    zvals = beta / se
    pvals = [float(2 * (1 - stats.norm.cdf(abs(z)))) for z in zvals]
    return {
        "intercept": {"estimate": round(float(beta[0]), 4), "se": round(float(se[0]), 4),
                      "p_value": pvals[0]},
        "slope": {"estimate": round(float(beta[1]), 4), "se": round(float(se[1]), 4),
                  "z": round(float(zvals[1]), 4), "p_value": pvals[1]},
        "residual_tau2": round(float(tau2), 4),
        "Q_residual": round(q_res, 4), "df": k - p,
        "reference": citations.ref("thompson2002"),
    }


def _leave_one_out(items, tau2_method, hksj):
    out = []
    for i in range(len(items)):
        sub = items[:i] + items[i + 1:]
        if len(sub) < 2:
            continue
        r = _pool(sub, tau2_method, hksj)["random"]
        out.append({"omitted": items[i]["name"], "estimate": r["estimate"],
                    "ci_low": r["ci_low"], "ci_high": r["ci_high"]})
    return out


def _cumulative(items, tau2_method, hksj):
    ordered = sorted(items, key=lambda it: (it["sort_key"] is None, it["sort_key"]))
    out = []
    for i in range(2, len(ordered) + 1):
        r = _pool(ordered[:i], tau2_method, hksj)["random"]
        out.append({"added": ordered[i - 1]["name"], "estimate": r["estimate"],
                    "ci_low": r["ci_low"], "ci_high": r["ci_high"]})
    return out


def _model_refs(tau2_method, hksj):
    keys = ["borenstein2009", "higgins2002"]
    keys.append({"DL": "dersimonian1986", "PM": "paule1982", "REML": "viechtbauer2005"}
                .get((tau2_method or "DL").upper(), "dersimonian1986"))
    if hksj:
        keys += ["hartung2001", "sidik2002"]
    return keys


def analyze(studies, *, measure="generic", model="random", tau2_method="DL",
            hksj=False, subgroups=True, meta_regression=True, cumulative=True,
            bias_tests=True) -> dict:
    """Run a comprehensive meta-analysis. See module docstring for options."""
    items = _prepare(studies, measure)
    result = _pool(items, tau2_method, hksj)
    tau2 = result.pop("_tau2")

    # per-study rows with weights for the chosen model
    w = [1 / (it["vi"] + (tau2 if model == "random" else 0.0)) for it in items]
    sw = sum(w)
    result["studies"] = [
        {"name": it["name"], "effect": round(it["yi"], 4), "se": round(it["se"], 4),
         "ci_low": round(it["yi"] - Z * it["se"], 4), "ci_high": round(it["yi"] + Z * it["se"], 4),
         "weight_pct": round(100 * wi / sw, 1), "group": it["group"]}
        for it, wi in zip(items, w)
    ]

    result["model"] = model
    result["effect_measure"] = measure
    transform, label = _TRANSFORM.get(measure, (None, "effect"))
    result["scale_label"] = label
    result["log_scale"] = measure in _LOG_MEASURES

    # back-transformed pooled estimates for display
    if transform:
        def bt(x):
            if transform == "exp":
                return round(math.exp(x), 4)
            if transform == "tanh":
                return round(math.tanh(x), 4)
            if transform == "expit":
                return round(1 / (1 + math.exp(-x)), 4)
            return x
        for m in ("fixed", "random"):
            e = result[m]
            e["transformed"] = {"estimate": bt(e["estimate"]), "ci_low": bt(e["ci_low"]),
                                "ci_high": bt(e["ci_high"])}
        if result["prediction_interval"]:
            pi = result["prediction_interval"]
            pi["transformed"] = {"low": bt(pi["low"]), "high": bt(pi["high"])}

    result["leave_one_out"] = _leave_one_out(items, tau2_method, hksj)

    if subgroups and any(it["group"] for it in items):
        groups: dict[str, list] = {}
        for it in items:
            groups.setdefault(it["group"] or "(none)", []).append(it)
        sg = {g: _pool(gi, tau2_method, hksj) for g, gi in groups.items() if len(gi) >= 2}
        for v in sg.values():
            v.pop("_tau2", None)
        # test for subgroup differences (Q_between)
        q_between = None
        if len(sg) >= 2:
            q_within = sum(v["heterogeneity"]["Q"] for v in sg.values())
            overall_q = result["heterogeneity"]["Q"]
            qb = max(0.0, overall_q - q_within)
            dfb = len(sg) - 1
            q_between = {"Q": round(qb, 4), "df": dfb,
                         "p_value": float(1 - stats.chi2.cdf(qb, dfb)) if dfb > 0 else None}
        result["subgroups"] = {"groups": sg, "test_for_differences": q_between}

    if meta_regression:
        mr = _meta_regression(items)
        if mr:
            result["meta_regression"] = mr

    if cumulative and any(it["sort_key"] is not None for it in items):
        result["cumulative"] = _cumulative(items, tau2_method, hksj)

    if bias_tests:
        result["publication_bias"] = {
            "egger": _egger(items), "begg": _begg(items), "trim_and_fill": _trim_fill(items),
        }

    result["references"] = citations.refs(
        _model_refs(tau2_method, hksj)
        + (["higgins2009pi"] if result["prediction_interval"] else [])
        + ({"smd": ["hedges1981"], "peto": ["yusuf1985"]}.get(measure, []))
    )
    return result
