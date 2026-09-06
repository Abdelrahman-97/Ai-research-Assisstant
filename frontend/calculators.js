/* Free statistics tools — talks to the public /tools/* endpoints. No auth. */
const API = window.API_BASE || "http://localhost:8000";

function toast(msg, err) {
  const t = document.getElementById("toast");
  t.textContent = msg; t.className = "toast" + (err ? " err" : "");
  setTimeout(() => (t.className = "toast hidden"), 3200);
}
function esc(s) { return String(s ?? "").replace(/[&<>]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c])); }

async function post(path, body) {
  const res = await fetch(API + path, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || ("Error " + res.status));
  return data;
}

/* ---- Sample size ---- */
const SS_FIELDS = {
  two_means: [["effect_size", "Effect size (Cohen's d)", "0.5"]],
  two_proportions: [["p1", "Proportion group 1", "0.5"], ["p2", "Proportion group 2", "0.3"]],
  anova: [["effect_size", "Effect size (Cohen's f)", "0.25"], ["k_groups", "Number of groups", "3"]],
  correlation: [["r", "Correlation (r)", "0.3"]],
};
function renderSSFields() {
  const design = document.getElementById("ssDesign").value;
  document.getElementById("ssFields").innerHTML = SS_FIELDS[design].map(([id, label, val]) =>
    `<label>${label}</label><input id="ss_${id}" type="number" step="any" value="${val}" />`
  ).join("");
}
document.getElementById("ssDesign").onchange = renderSSFields;
renderSSFields();

document.getElementById("ssBtn").onclick = async () => {
  const design = document.getElementById("ssDesign").value;
  const params = { alpha: parseFloat(document.getElementById("ssAlpha").value),
                   power: parseFloat(document.getElementById("ssPower").value) };
  SS_FIELDS[design].forEach(([id]) => {
    const v = parseFloat(document.getElementById("ss_" + id).value);
    params[id] = id === "k_groups" ? Math.round(v) : v;
  });
  try {
    const r = await post("/tools/sample-size", { design, params });
    let html = "";
    if (r.design === "anova") html = `<strong>${r.n_per_group}</strong> per group · <strong>${r.total}</strong> total (${r.k_groups} groups)`;
    else if (r.design === "correlation") html = `<strong>${r.total}</strong> participants total`;
    else html = `<strong>${r.n_group1}</strong> + <strong>${r.n_group2}</strong> = <strong>${r.total}</strong> total`;
    document.getElementById("ssOut").innerHTML = `<div class="md" style="margin-top:14px;">Required sample size: ${html}</div>`;
  } catch (e) { toast(e.message, true); }
};

/* ---- Diagnostic ---- */
document.getElementById("dBtn").onclick = async () => {
  const body = {
    tp: parseInt(document.getElementById("dTP").value, 10),
    fp: parseInt(document.getElementById("dFP").value, 10),
    fn: parseInt(document.getElementById("dFN").value, 10),
    tn: parseInt(document.getElementById("dTN").value, 10),
  };
  try {
    const r = await post("/tools/diagnostic", body);
    const pct = m => m.value == null ? "—" : `${(m.value * 100).toFixed(1)}% (${(m.ci_low * 100).toFixed(1)}–${(m.ci_high * 100).toFixed(1)})`;
    const rows = [
      ["Sensitivity", pct(r.sensitivity)], ["Specificity", pct(r.specificity)],
      ["PPV", pct(r.ppv)], ["NPV", pct(r.npv)], ["Accuracy", pct(r.accuracy)],
      ["Prevalence", pct(r.prevalence)],
      ["LR+", r.lr_positive ?? "—"], ["LR−", r.lr_negative ?? "—"],
      ["Diagnostic OR", r.diagnostic_or ?? "—"],
    ].map(([k, v]) => `<tr><td style="padding:6px 10px;border-bottom:1px solid var(--line);">${k}</td><td style="padding:6px 10px;border-bottom:1px solid var(--line);"><strong>${esc(v)}</strong></td></tr>`).join("");
    document.getElementById("dOut").innerHTML =
      `<div style="overflow:auto;margin-top:14px;border:1px solid var(--line);border-radius:var(--radius-sm);"><table style="border-collapse:collapse;font-size:14px;width:100%;">${rows}</table></div>
       <p class="muted-note">Percentages show value (95% CI).</p>`;
  } catch (e) { toast(e.message, true); }
};

/* ---- Meta-analysis ---- */
document.getElementById("mBtn").onclick = async () => {
  const lines = document.getElementById("mData").value.split("\n").map(l => l.trim()).filter(Boolean);
  const studies = [];
  for (const line of lines) {
    const parts = line.split(",").map(s => s.trim());
    if (parts.length < 3) { toast("Each line needs at least: name, effect, SE", true); return; }
    const [name, effect, se, group] = parts;
    studies.push({ name, effect: parseFloat(effect), se: parseFloat(se), group: group || null });
  }
  try {
    const r = await post("/tools/meta-analysis", { studies, model: "random", subgroups: true });
    const h = r.heterogeneity;
    const fmt = m => `${m.estimate} (95% CI ${m.ci_low} to ${m.ci_high}), p = ${m.p_value == null ? "—" : m.p_value.toFixed(4)}`;
    const studyRows = r.studies.map(s =>
      `<tr><td style="padding:5px 10px;border-bottom:1px solid var(--line);">${esc(s.name)}</td>
       <td style="padding:5px 10px;border-bottom:1px solid var(--line);">${s.effect} [${s.ci_low}, ${s.ci_high}]</td>
       <td style="padding:5px 10px;border-bottom:1px solid var(--line);">${s.weight_pct}%</td>
       <td style="padding:5px 10px;border-bottom:1px solid var(--line);">${esc(s.group || "")}</td></tr>`).join("");
    let subs = "";
    if (r.subgroups) subs = "<h3>Subgroups</h3>" + Object.entries(r.subgroups).map(([g, sr]) =>
      `<p><strong>${esc(g)}</strong> (k=${sr.k}): random ${fmt(sr.random)}; I² = ${sr.heterogeneity.I2_percent}%</p>`).join("");
    const loo = r.leave_one_out.map(l => `<tr><td style="padding:5px 10px;border-bottom:1px solid var(--line);">omit ${esc(l.omitted)}</td><td style="padding:5px 10px;border-bottom:1px solid var(--line);">${l.estimate} [${l.ci_low}, ${l.ci_high}]</td></tr>`).join("");
    document.getElementById("mOut").innerHTML = `
      <div class="md" style="margin-top:14px;">
        <p><strong>Random effects:</strong> ${fmt(r.random)}</p>
        <p><strong>Fixed effect:</strong> ${fmt(r.fixed)}</p>
        <p><strong>Heterogeneity:</strong> Q = ${h.Q} (df ${h.df}), p = ${h.p_value == null ? "—" : h.p_value.toFixed(4)}, I² = ${h.I2_percent}%, τ² = ${h.tau2}</p>
      </div>
      <h3 style="margin-top:16px;">Per study</h3>
      <div style="overflow:auto;border:1px solid var(--line);border-radius:var(--radius-sm);"><table style="border-collapse:collapse;font-size:13px;width:100%;">
        <thead><tr><th style="text-align:left;padding:6px 10px;">Study</th><th style="text-align:left;padding:6px 10px;">Effect [95% CI]</th><th style="text-align:left;padding:6px 10px;">Weight</th><th style="text-align:left;padding:6px 10px;">Group</th></tr></thead>
        <tbody>${studyRows}</tbody></table></div>
      ${subs}
      <h3 style="margin-top:16px;">Leave-one-out</h3>
      <div style="overflow:auto;border:1px solid var(--line);border-radius:var(--radius-sm);"><table style="border-collapse:collapse;font-size:13px;width:100%;"><tbody>${loo}</tbody></table></div>`;
  } catch (e) { toast(e.message, true); }
};
