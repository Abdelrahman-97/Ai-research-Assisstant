"""Survival engine: Kaplan-Meier estimates + the log-rank test across groups."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from app.services import citations
from app.services.stat_engines import plots
from app.services.stat_engines.base import EngineError, fmt_p, get_col, pstr, refs_block, round4


def survival_logrank(df: pd.DataFrame, params: dict, fig_dir: str | Path | None = None) -> dict:
    from statsmodels.duration.survfunc import SurvfuncRight, survdiff

    time = params.get("time")
    event = params.get("event")
    group = params.get("group")
    if not time or not event:
        raise EngineError("Survival analysis needs 'time' and 'event' (1=event, 0=censored).")
    cols = [time, event] + ([group] if group else [])
    for c in cols:
        get_col(df, c, "column")
    data = df[cols].copy()
    data[time] = pd.to_numeric(data[time], errors="coerce")
    data[event] = pd.to_numeric(data[event], errors="coerce")
    data = data.dropna()
    if len(data) < 4:
        raise EngineError("Not enough complete observations for survival analysis.")

    def _median_survival(sf) -> float | None:
        for t, p in zip(sf.surv_times, sf.surv_prob):
            if p <= 0.5:
                return float(t)
        return None

    curves: dict[str, dict] = {}
    group_summ: dict[str, dict] = {}
    if group:
        levels = list(dict.fromkeys(data[group].astype(str)))
        for lv in levels:
            sub = data[data[group].astype(str) == lv]
            sf = SurvfuncRight(sub[time], sub[event])
            curves[lv] = {"time": [0.0] + list(map(float, sf.surv_times)),
                          "surv": [1.0] + list(map(float, sf.surv_prob))}
            group_summ[lv] = {"n": int(len(sub)), "events": int(sub[event].sum()),
                              "median_survival": _median_survival(sf)}
        chisq, p = survdiff(data[time], data[event], data[group].astype(str))
        values = {"n": int(len(data)), "groups": group_summ,
                  "logrank": {"chi2": round4(chisq), "df": len(levels) - 1, "p_value": float(p)}}
        md = [
            "## Kaplan-Meier survival analysis with log-rank test\n",
            f"We estimated survival over **{time}** by **{group}** (n = {len(data)}, "
            f"events = {int(data[event].sum())}).\n",
        ]
        for lv, s in group_summ.items():
            md.append(f"- **{lv}**: n = {s['n']}, events = {s['events']}, "
                      f"median survival = {s['median_survival'] if s['median_survival'] is not None else 'not reached'}.")
        md.append(f"\nThe log-rank test "
                  + ("showed a statistically significant" if p < 0.05 else "showed no statistically significant")
                  + f" difference in survival between groups, **χ²({len(levels) - 1}) = {round4(chisq)}**, "
                  f"{pstr(p)}. See the Kaplan-Meier curves.")
        refs = citations.refs(["kaplan1958", "mantel1966"])
    else:
        sf = SurvfuncRight(data[time], data[event])
        curves["Overall"] = {"time": [0.0] + list(map(float, sf.surv_times)),
                             "surv": [1.0] + list(map(float, sf.surv_prob))}
        values = {"n": int(len(data)), "events": int(data[event].sum()),
                  "median_survival": _median_survival(sf)}
        md = [
            "## Kaplan-Meier survival analysis\n",
            f"We estimated overall survival over **{time}** (n = {len(data)}, "
            f"events = {int(data[event].sum())}). Median survival = "
            f"{values['median_survival'] if values['median_survival'] is not None else 'not reached'}. "
            "See the Kaplan-Meier curve.",
        ]
        refs = citations.refs(["kaplan1958"])

    fig = None
    if fig_dir:
        fig = plots.km_curves(curves, path=Path(fig_dir) / "km.png", xlabel=str(time))
    return {"key": "survival_logrank", "title": "Kaplan-Meier / log-rank",
            "values": values, "markdown": "\n".join(md) + refs_block(refs),
            "references": refs, "figure_path": fig,
            "assumptions": ["Censoring is independent of prognosis",
                            "For the log-rank test: proportional hazards over time"]}
