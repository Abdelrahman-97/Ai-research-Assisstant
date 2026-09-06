"""Render a paid tool job (meta-analysis / sample-size / diagnostic) into a clear,
explained Markdown report — plain language a non-statistician can follow, with a
References section drawn from the curated citations. report_writer converts this
to the Word/PDF the customer downloads.
"""

from __future__ import annotations

from app.services import citations


def _p(p):
    if p is None:
        return "—"
    return "< .001" if p < 0.001 else f"{p:.3f}"


def _refs_block(refs: list[str]) -> str:
    if not refs:
        return ""
    lines = "\n".join(f"{i + 1}. {r}" for i, r in enumerate(refs))
    return f"\n\n## References\n\n{lines}\n"


# --------------------------------------------------------------------------- #
def _sample_size(inp: dict, r: dict) -> str:
    design_names = {
        "two_means": "two independent groups (means, t-test)",
        "paired_means": "paired/one-sample means (t-test)",
        "one_mean": "one mean vs a reference value",
        "two_proportions": "two independent proportions",
        "one_proportion": "one proportion vs a reference value",
        "anova": "more than two groups (one-way ANOVA)",
        "correlation": "a correlation",
        "chi_square": "a chi-square test",
    }
    name = design_names.get(r.get("design"), r.get("design"))
    md = ["# Sample-size calculation\n",
          f"This report estimates the sample size for **{name}**.\n",
          "## What you entered\n"]
    for k, v in (r.get("inputs") or {}).items():
        md.append(f"- **{k}**: {v}")
    md.append("\n## Result\n")
    if r.get("solve") == "power":
        md.append(f"With the sample size you specified, the achieved **statistical power is {r['power']:.2f}** "
                  f"({r['power'] * 100:.0f}%). Power is the chance of detecting a real effect of the size you "
                  f"assumed; 0.80 (80%) is the common minimum.")
    else:
        if "n_group1" in r:
            md.append(f"You need **{r['n_group1']} in group 1** and **{r['n_group2']} in group 2** "
                      f"(**{r['total']} in total**).")
        elif "n_per_group" in r:
            md.append(f"You need **{r['n_per_group']} per group** across {r.get('k_groups','?')} groups "
                      f"(**{r['total']} in total**).")
        else:
            md.append(f"You need **{r.get('n', r['total'])} participants in total**.")
        md.append("\nThis is the number required to detect the effect size you specified, at your chosen "
                  "significance level (alpha) and power. If you expect drop-out, enrol more so the *completed* "
                  "sample meets this target.")
    return "\n".join(md) + _refs_block(r.get("references", []))


def _diagnostic(inp: dict, r: dict) -> str:
    c = r["counts"]

    def pct(m):
        if m["value"] is None:
            return "—"
        return f"{m['value'] * 100:.1f}% (95% CI {m['ci_low'] * 100:.1f}–{m['ci_high'] * 100:.1f})"

    md = [
        "# Diagnostic accuracy\n",
        f"Based on a 2×2 table of **{c['tp']}** true positives, **{c['fp']}** false positives, "
        f"**{c['fn']}** false negatives, and **{c['tn']}** true negatives (n = {c['n']}).\n",
        "## Results\n",
        f"- **Sensitivity:** {pct(r['sensitivity'])} — of people who truly have the condition, the "
        "proportion the test correctly flags as positive.",
        f"- **Specificity:** {pct(r['specificity'])} — of people who truly do not have it, the proportion "
        "correctly flagged as negative.",
        f"- **Positive predictive value (PPV):** {pct(r['ppv'])} — of those who test positive, the "
        "proportion who truly have the condition.",
        f"- **Negative predictive value (NPV):** {pct(r['npv'])} — of those who test negative, the "
        "proportion who truly do not.",
        f"- **Accuracy:** {pct(r['accuracy'])} — overall proportion correctly classified.",
        f"- **Prevalence (in this sample):** {pct(r['prevalence'])}.",
        f"- **Positive likelihood ratio (LR+):** {r['lr_positive'] if r['lr_positive'] is not None else '—'} — "
        "how much a positive result raises the odds of disease (higher is better; > 10 is strong).",
        f"- **Negative likelihood ratio (LR−):** {r['lr_negative'] if r['lr_negative'] is not None else '—'} — "
        "how much a negative result lowers the odds (lower is better; < 0.1 is strong).",
        f"- **Diagnostic odds ratio:** {r['diagnostic_or'] if r['diagnostic_or'] is not None else '—'}.",
        "\nPredictive values depend on how common the condition is; likelihood ratios do not, so they "
        "transfer better across settings.",
    ]
    refs = citations.refs(["altman1994", "deeks2004", "wilson1927"])
    return "\n".join(md) + _refs_block(refs)


def _meta(inp: dict, r: dict) -> str:
    label = r.get("scale_label", "effect")
    log = r.get("log_scale")

    def show(e):
        if "transformed" in e:
            t = e["transformed"]
            return f"{t['estimate']} (95% CI {t['ci_low']} to {t['ci_high']})"
        return f"{e['estimate']} (95% CI {e['ci_low']} to {e['ci_high']})"

    het = r["heterogeneity"]
    md = [
        "# Meta-analysis\n",
        f"Pooled **{r['k']} studies** on the **{label}** scale using a "
        f"**{r['model']}-effects model**"
        + (f" (τ² by {het['tau2_method']})." if r['model'] == 'random' else ".") + "\n",
        "## Pooled effect\n",
        f"- **Random-effects estimate:** {show(r['random'])}, p = {_p(r['random'].get('p_value'))}"
        + (f" [{r['random'].get('method')} interval]" if r['random'].get('method') else ""),
        f"- **Fixed-effect estimate:** {show(r['fixed'])}, p = {_p(r['fixed'].get('p_value'))}",
    ]
    if r.get("prediction_interval"):
        pi = r["prediction_interval"]
        pit = pi.get("transformed", pi)
        md.append(f"- **95% prediction interval:** {pit.get('low', pi['low'])} to "
                  f"{pit.get('high', pi['high'])} — the range a future study's true effect is expected to fall in.")
    md += [
        "\n## Heterogeneity (how much studies differ)\n",
        f"- **I² = {het['I2_percent']}%** ("
        + ("low" if het['I2_percent'] < 25 else "moderate" if het['I2_percent'] < 75 else "high")
        + " heterogeneity), **τ² = {}**, **Q = {}** (df {}), p = {}.".format(
            het['tau2'], het['Q'], het['df'], _p(het['p_value'])),
        "I² is the share of variation across studies beyond chance. Higher values mean the studies' true "
        "effects differ more, favouring the random-effects estimate.",
        "\n## Studies included\n",
    ]
    for s in r["studies"]:
        md.append(f"- **{s['name']}**: {s['effect']} [{s['ci_low']}, {s['ci_high']}] · weight {s['weight_pct']}%"
                  + (f" · subgroup: {s['group']}" if s.get('group') else ""))

    sg = r.get("subgroups")
    if sg and sg.get("groups"):
        md.append("\n## Subgroup analysis\n")
        for g, gr in sg["groups"].items():
            md.append(f"- **{g}** (k={gr['k']}): {show(gr['random'])}; I² = {gr['heterogeneity']['I2_percent']}%")
        if sg.get("test_for_differences"):
            t = sg["test_for_differences"]
            md.append(f"- **Test for subgroup differences:** Q = {t['Q']} (df {t['df']}), p = {_p(t['p_value'])}.")

    if r.get("meta_regression"):
        mr = r["meta_regression"]
        md.append("\n## Meta-regression\n")
        md.append(f"- **Slope:** {mr['slope']['estimate']} (SE {mr['slope']['se']}), p = {_p(mr['slope']['p_value'])} "
                  f"— association between the moderator and the effect size.")
        md.append(f"- Residual τ² = {mr['residual_tau2']}.")

    pb = r.get("publication_bias") or {}
    if any(pb.get(k) for k in ("egger", "begg", "trim_and_fill")):
        md.append("\n## Publication bias / small-study effects\n")
        if pb.get("egger"):
            e = pb["egger"]
            md.append(f"- **Egger's test:** intercept {e['intercept']}, p = {_p(e['p_value'])} "
                      "(a significant result suggests possible small-study effects).")
        if pb.get("begg"):
            b = pb["begg"]
            md.append(f"- **Begg's test:** Kendall's τ = {b['kendall_tau']}, p = {_p(b['p_value'])}.")
        if pb.get("trim_and_fill"):
            tf = pb["trim_and_fill"]
            md.append(f"- **Trim-and-fill:** {tf['imputed_studies']} study(ies) imputed; "
                      f"bias-adjusted estimate {tf['adjusted_estimate']} (log scale)." if log
                      else f"- **Trim-and-fill:** {tf['imputed_studies']} study(ies) imputed; "
                      f"bias-adjusted estimate {tf['adjusted_estimate']}.")

    if r.get("leave_one_out"):
        md.append("\n## Sensitivity (leave-one-out)\n")
        for l in r["leave_one_out"]:
            md.append(f"- Omitting **{l['omitted']}**: {l['estimate']} [{l['ci_low']}, {l['ci_high']}]")

    return "\n".join(md) + _refs_block(r.get("references", []))


def render(task: str, inputs: dict, result: dict) -> str:
    """Return the explained Markdown report for a tool job."""
    if task == "sample_size":
        return _sample_size(inputs, result)
    if task == "diagnostic":
        return _diagnostic(inputs, result)
    if task == "meta_analysis":
        return _meta(inputs, result)
    return "# Report\n\n(Unsupported tool.)"
