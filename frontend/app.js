/* AI Research Assistant — single-page frontend (vanilla JS, no build step).
 * Talks to the FastAPI backend at window.API_BASE.
 * Screens are driven by the run's `status` returned from the API. */

const API = window.API_BASE || "http://localhost:8000";

const state = {
  token: localStorage.getItem("ra_token") || null,
  user: null,
  view: "auth",          // auth | dashboard | run
  runId: null,
  run: null,
  // transient selections
  scope: "thesis",
  language: "python",
};

/* ----------------------------- API helper ------------------------------ */
async function api(path, { method = "GET", body, form } = {}) {
  const headers = {};
  if (state.token) headers["Authorization"] = "Bearer " + state.token;
  let payload;
  if (form) {
    payload = form; // FormData; browser sets content-type
  } else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }
  const res = await fetch(API + path, { method, headers, body: payload });
  if (res.status === 204) return null;
  const isJson = (res.headers.get("content-type") || "").includes("application/json");
  const data = isJson ? await res.json() : await res.blob();
  if (!res.ok) {
    const msg = (data && data.detail) ? data.detail : ("Error " + res.status);
    throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
  }
  return data;
}

/* ------------------------------- UI utils ------------------------------ */
const app = document.getElementById("app");
function toast(msg, isErr = false) {
  const t = document.getElementById("toast");
  t.textContent = msg;
  t.className = "toast" + (isErr ? " err" : "");
  setTimeout(() => (t.className = "toast hidden"), 3200);
}
function esc(s) { return String(s ?? "").replace(/[&<>]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c])); }

function syncTopbar() {
  document.getElementById("userEmail").textContent = state.user ? state.user.email : "";
  document.getElementById("logoutBtn").classList.toggle("hidden", !state.user);
}

document.getElementById("logoutBtn").onclick = () => {
  state.token = null; state.user = null; state.run = null; state.runId = null;
  localStorage.removeItem("ra_token");
  state.view = "auth"; render();
};

/* ------------------------------- Screens ------------------------------- */
const STEPS = [
  ["upload", "Upload"], ["estimate", "Price"], ["pay", "Pay"],
  ["plan", "Plan"], ["script", "Script"], ["run", "Run"], ["results", "Results"],
];
function statusToStepIndex(s) {
  return {
    created: 0, uploaded: 1, awaiting_payment: 2, paid: 3, awaiting_approval: 3,
    approved: 4, script_ready: 4, executing: 5, executed: 5, writing: 6,
    completed: 6, accepted: 6,
  }[s] ?? 0;
}
function stepper(status) {
  const cur = statusToStepIndex(status);
  return `<div class="stepper">${STEPS.map(([, label], i) =>
    `<span class="step ${i < cur ? "done" : ""} ${i === cur ? "current" : ""}">${label}</span>`
  ).join("")}</div>`;
}

/* --- Auth --- */
function renderAuth() {
  let mode = "login";
  app.innerHTML = `
    <div class="card" style="max-width:440px;margin:40px auto;">
      <h1 id="authTitle">Welcome back</h1>
      <p class="sub" id="authSub">Log in to continue.</p>
      <label>Email</label>
      <input id="email" type="email" placeholder="you@example.com" />
      <label>Password</label>
      <input id="password" type="password" placeholder="••••••••" />
      <div id="scopeWrap" class="hidden">
        <label>Default scope (you can change it per job)</label>
        <select id="signupScope">
          <option value="thesis">Thesis chapter</option>
          <option value="studies">Paper / study</option>
        </select>
      </div>
      <div class="btn-row">
        <button id="submitAuth" class="btn btn-primary btn-block">Log in</button>
      </div>
      <p class="muted-note center">
        <span id="switchText">No account?</span>
        <button class="link" id="switchMode">Sign up</button>
      </p>
      <p class="muted-note center" id="forgotWrap">
        <button class="link" id="forgotLink">Forgot password?</button>
      </p>
    </div>`;

  const setMode = (m) => {
    mode = m;
    document.getElementById("authTitle").textContent = m === "login" ? "Welcome back" : "Create your account";
    document.getElementById("authSub").textContent = m === "login" ? "Log in to continue." : "Sign up to get started.";
    document.getElementById("submitAuth").textContent = m === "login" ? "Log in" : "Sign up";
    document.getElementById("switchText").textContent = m === "login" ? "No account?" : "Already have an account?";
    document.getElementById("switchMode").textContent = m === "login" ? "Sign up" : "Log in";
    document.getElementById("scopeWrap").classList.toggle("hidden", m === "login");
    document.getElementById("forgotWrap").classList.toggle("hidden", m !== "login");
  };
  document.getElementById("switchMode").onclick = () => setMode(mode === "login" ? "signup" : "login");
  document.getElementById("forgotLink").onclick = () => { state.view = "forgot"; render(); };

  document.getElementById("submitAuth").onclick = async () => {
    const email = document.getElementById("email").value.trim();
    const password = document.getElementById("password").value;
    if (!email || !password) return toast("Enter email and password.", true);
    try {
      const path = mode === "login" ? "/auth/login" : "/auth/signup";
      const body = mode === "login"
        ? { email, password }
        : { email, password, scope: document.getElementById("signupScope").value };
      const data = await api(path, { method: "POST", body });
      state.token = data.access_token; state.user = data.user;
      localStorage.setItem("ra_token", state.token);
      state.view = "dashboard"; render();
    } catch (e) { toast(e.message, true); }
  };
}

/* --- Forgot password --- */
function renderForgot() {
  app.innerHTML = `
    <div class="card" style="max-width:440px;margin:40px auto;">
      <h1>Reset your password</h1>
      <p class="sub">Enter your email and we'll send you a reset link.</p>
      <label>Email</label>
      <input id="fpEmail" type="email" placeholder="you@example.com" />
      <div class="btn-row">
        <button id="fpSend" class="btn btn-primary btn-block">Send reset link</button>
      </div>
      <p class="muted-note center"><button class="link" id="fpBack">← Back to sign in</button></p>
    </div>`;
  document.getElementById("fpBack").onclick = () => { state.view = "auth"; render(); };
  document.getElementById("fpSend").onclick = async () => {
    const email = document.getElementById("fpEmail").value.trim();
    if (!email) return toast("Enter your email.", true);
    try {
      await api("/auth/forgot-password", { method: "POST", body: { email } });
      toast("If that email is registered, a reset link was sent. Check your inbox.");
      setTimeout(() => { state.view = "auth"; render(); }, 1500);
    } catch (e) { toast(e.message, true); }
  };
}

/* --- Dashboard (my runs + new task) --- */
async function renderDashboard() {
  app.innerHTML = `<div class="center"><div class="spinner-lg"></div></div>`;
  let runs = [];
  try { runs = await api("/runs"); } catch (e) { toast(e.message, true); }

  const items = runs.length ? runs.map(r => `
    <div class="run-item" data-id="${r.id}">
      <div>
        <div><strong>${labelScope(r.scope)}</strong> · Results section</div>
        <div class="run-meta">${new Date(r.created_at).toLocaleString()} · ${r.id.slice(0, 8)}</div>
      </div>
      ${statusPill(r.status)}
    </div>`).join("") : `<p class="sub">No jobs yet. Start your first one.</p>`;

  const verifyBanner = (state.user && !state.user.email_verified) ? `
    <div class="card" style="border-color:var(--accent);background:#fbf3ea;">
      <strong>Verify your email.</strong>
      <span class="sub">We sent a link to ${esc(state.user.email)}. </span>
      <button class="link" id="resendVerify">Resend</button>
    </div>` : "";

  app.innerHTML = `
    ${verifyBanner}
    <div class="card">
      <h1>Your workspace</h1>
      <p class="sub">Start a new Results section, or continue a job.</p>
      <button id="newTaskBtn" class="btn btn-primary">+ New Results section</button>
    </div>
    <div class="card">
      <h2>My jobs</h2>
      <p class="sub">Files are kept 30 days after you accept the results.</p>
      <div id="runsList" style="margin-top:12px;">${items}</div>
    </div>
    <p class="muted-note center"><button class="link" id="deleteAccount" style="color:var(--err);">Delete my account and all data</button></p>`;

  document.getElementById("newTaskBtn").onclick = () => { state.view = "newtask"; render(); };
  document.getElementById("deleteAccount").onclick = async () => {
    if (!confirm("Permanently delete your account, all jobs, and all files? This cannot be undone.")) return;
    try {
      await api("/auth/me", { method: "DELETE" });
      toast("Account deleted.");
      state.token = null; state.user = null; localStorage.removeItem("ra_token");
      state.view = "auth"; render();
    } catch (e) { toast(e.message, true); }
  };
  const resend = document.getElementById("resendVerify");
  if (resend) resend.onclick = async () => {
    try { await api("/auth/resend-verification", { method: "POST", body: { email: state.user.email } });
      toast("Verification email resent."); } catch (e) { toast(e.message, true); }
  };
  document.querySelectorAll(".run-item").forEach(el =>
    el.onclick = () => openRun(el.dataset.id));
}

/* --- New task (task + scope) --- */
function renderNewTask() {
  app.innerHTML = `
    <div class="card">
      <button class="link" id="back">← Back</button>
      <h1 style="margin-top:10px;">New Results section</h1>
      <p class="sub">What are you writing this for?</p>
      <div class="choices" id="scopeChoices">
        <div class="choice ${state.scope === "thesis" ? "active" : ""}" data-scope="thesis">
          <div class="c-title">Thesis chapter</div>
          <div class="c-desc">Longer, detailed results chapter</div>
        </div>
        <div class="choice ${state.scope === "studies" ? "active" : ""}" data-scope="studies">
          <div class="c-title">Paper / study</div>
          <div class="c-desc">Concise results section</div>
        </div>
      </div>
      <div class="btn-row">
        <button id="startBtn" class="btn btn-primary">Continue</button>
      </div>
    </div>`;
  document.getElementById("back").onclick = () => { state.view = "dashboard"; render(); };
  document.querySelectorAll("#scopeChoices .choice").forEach(c => c.onclick = () => {
    state.scope = c.dataset.scope;
    document.querySelectorAll("#scopeChoices .choice").forEach(x => x.classList.remove("active"));
    c.classList.add("active");
  });
  document.getElementById("startBtn").onclick = async () => {
    try {
      const run = await api("/runs", { method: "POST", body: { scope: state.scope } });
      state.run = run; state.runId = run.id; state.view = "run"; render();
    } catch (e) { toast(e.message, true); }
  };
}

/* --- Run screen: dispatches on run.status --- */
async function openRun(id) {
  state.runId = id;
  app.innerHTML = `<div class="center"><div class="spinner-lg"></div></div>`;
  try { state.run = await api("/runs/" + id); state.view = "run"; render(); }
  catch (e) { toast(e.message, true); }
}
async function refreshRun() {
  state.run = await api("/runs/" + state.runId);
  render();
}

function runShell(inner) {
  const r = state.run;
  return `
    <div class="card">
      <button class="link" id="toDash">← My jobs</button>
      <h1 style="margin-top:10px;">${labelScope(r.scope)} · Results section</h1>
      ${stepper(r.status)}
      ${inner}
    </div>`;
}

function renderRun() {
  const r = state.run;
  let inner;
  switch (r.status) {
    case "created": inner = viewUpload(); break;
    case "uploaded": inner = viewEstimate(); break;
    case "awaiting_payment": inner = viewPay(); break;
    case "paid": inner = viewStartPlan(); break;
    case "awaiting_approval": inner = viewPlan(); break;
    case "approved": inner = viewScriptGen(); break;
    case "script_ready": inner = viewScriptPreview(); break;
    case "executing": inner = viewBusy("Running the analysis in the sandbox…"); break;
    case "executed": inner = viewWriteResults(); break;
    case "writing": inner = viewBusy("Writing the Results section…"); break;
    case "completed":
    case "accepted": inner = viewResults(); break;
    case "expired": inner = `<p class="sub">This job's files have expired (30-day window).</p>`; break;
    case "failed":
      inner = `<p><span class="pill err">Failed</span></p><p class="sub">${esc(r.error || "Something went wrong.")}</p>`
        + (r.approved_test ? `<div class="btn-row"><button id="retryScript" class="btn btn-primary">Regenerate script & retry</button></div>` : "");
      break;
    default: inner = `<p class="sub">Status: ${r.status}</p>`;
  }
  app.innerHTML = runShell(inner);
  document.getElementById("toDash").onclick = () => { state.view = "dashboard"; render(); };
  bindRunHandlers();
}

/* ---- run sub-views ---- */
function viewUpload() {
  return `
    <h2>Upload your study</h2>
    <p class="sub">We validate the data and use it to price the job — this step is free.</p>
    <label>Protocol / methods</label>
    <textarea id="protocol" placeholder="Paste the methods / analysis plan of your study..."></textarea>
    <label>Data file (Excel or CSV)</label>
    <input id="dataFile" type="file" accept=".xlsx,.xls,.csv,.tsv" />
    <div class="btn-row"><button id="uploadBtn" class="btn btn-primary">Upload & validate</button></div>`;
}
function viewEstimate() {
  const s = state.run.data_summary;
  const cols = s ? s.columns.map(c => `<span class="tag">${esc(c.name)} · ${c.dtype}</span>`).join("") : "";
  return `
    <h2>Data looks good <span class="pill ok">valid</span></h2>
    <div class="kv" style="margin:12px 0;">
      <div class="k">Rows</div><div>${s ? s.n_rows : "?"}</div>
      <div class="k">Columns</div><div>${s ? s.n_cols : "?"}</div>
    </div>
    <div>${cols}</div>
    <label style="margin-top:18px;">Target word count for the Results section</label>
    <input id="wordCount" type="number" min="100" max="20000" step="50" value="800" />
    <div class="btn-row"><button id="estimateBtn" class="btn btn-primary">Get price</button></div>`;
}
function viewPay() {
  const q = state.run.quote || {};
  const rows = Object.entries(q.breakdown || {}).map(([k, v]) =>
    `<li><span class="k">${esc(k)}</span><span class="v">${v} EGP</span></li>`).join("");
  const total = q.customer_total_egp || q.amount_egp || 0;
  const fees = total - (q.amount_egp || 0);
  const feeRow = fees > 0
    ? `<li><span class="k">payment processing fees</span><span class="v">${fees} EGP</span></li>` : "";
  return `
    <h2>Your price</h2>
    <p class="sub">Estimated ${q.estimated_tests ?? "?"} statistical test(s) · ${q.word_count ?? "?"} words.</p>
    <div class="price-total">${total} <small>EGP</small></div>
    <ul class="breakdown">${rows}${feeRow}</ul>
    <label class="agree">
      <input type="checkbox" id="agree" />
      <span>I agree to the <a class="link" href="terms.html" target="_blank">Terms of Service</a>
      and <a class="link" href="refund.html" target="_blank">Refund Policy</a>, and understand that
      completed tasks are processed immediately and are non-refundable.</span>
    </label>
    <div class="btn-row">
      <button id="payBtn" class="btn btn-primary" disabled>Proceed to payment</button>
      <button id="reEstimateBtn" class="btn btn-ghost">Change word count</button>
    </div>
    <p class="muted-note">After paying, this page updates automatically once the payment is confirmed.</p>`;
}
function viewStartPlan() {
  return `
    <h2>Payment confirmed <span class="pill ok">paid</span></h2>
    <p class="sub">Ready to analyse. The AI will propose a statistical plan for you to approve.</p>
    <div class="btn-row"><button id="planBtn" class="btn btn-primary">Propose statistical plan</button></div>`;
}
function viewPlan() {
  const t = state.run.proposed_test || {};
  return `
    <h2>Proposed plan — your approval needed</h2>
    <p class="sub">Review the AI's proposal. Approve it, or edit before continuing. Nothing runs until you approve.</p>
    <label>Test</label>
    <input id="pName" value="${esc(t.name || "")}" />
    <label>Reasoning</label>
    <textarea id="pReason">${esc(t.reasoning || "")}</textarea>
    <label>Variables (comma-separated)</label>
    <input id="pVars" value="${esc((t.variables || []).join(", "))}" />
    <div>${(t.assumptions || []).map(a => `<span class="tag">assumes: ${esc(a)}</span>`).join("")}</div>
    <div class="btn-row">
      <button id="approveBtn" class="btn btn-primary">Approve & continue</button>
    </div>`;
}
function viewScriptGen() {
  return `
    <h2>Plan approved <span class="pill ok">approved</span></h2>
    <p class="sub">Choose the language; the AI writes the analysis script for you to preview.</p>
    <div class="choices" id="langChoices">
      <div class="choice ${state.language === "python" ? "active" : ""}" data-lang="python">
        <div class="c-title">Python</div><div class="c-desc">pandas / scipy / statsmodels</div>
      </div>
      <div class="choice ${state.language === "r" ? "active" : ""}" data-lang="r">
        <div class="c-title">R</div><div class="c-desc">base + stats</div>
      </div>
    </div>
    <div class="btn-row"><button id="genScriptBtn" class="btn btn-primary">Generate script</button></div>`;
}
function viewScriptPreview() {
  return `
    <h2>Script preview</h2>
    <p class="sub">This runs in an isolated sandbox (no network). Review it, then run.</p>
    <pre class="code">${esc(state.run.script || "")}</pre>
    <div class="btn-row"><button id="executeBtn" class="btn btn-primary">Run analysis</button></div>`;
}
function viewWriteResults() {
  const ex = state.run.execution || {};
  const arts = (ex.artifacts || []).map(a => `<span class="tag">${esc(a.caption || a.kind)}</span>`).join("");
  return `
    <h2>Analysis complete <span class="pill ok">executed</span></h2>
    <p class="sub">Output captured. Now the AI writes the Results section grounded in these numbers.</p>
    <label>Output</label>
    <pre class="code">${esc((ex.stdout || "").slice(0, 2000) || "(no output)")}</pre>
    <div>${arts}</div>
    <div class="btn-row"><button id="writeBtn" class="btn btn-primary">Write Results section</button></div>`;
}
function viewResults() {
  const r = state.run;
  const accepted = r.status === "accepted";
  const expiry = r.expires_at ? new Date(r.expires_at).toLocaleDateString() : null;
  return `
    <h2>Your Results section ${accepted ? '<span class="pill ok">accepted</span>' : '<span class="pill ok">ready</span>'}</h2>
    <div class="md">${esc(r.results_markdown || "")}</div>
    ${accepted ? `<p class="muted-note">Files available until ${expiry}.</p>`
      : `<p class="sub" style="margin-top:16px;">Happy with it? Accept to finalise (starts the 30-day storage window).</p>`}
    <div class="btn-row">
      ${accepted ? "" : `<button id="acceptBtn" class="btn btn-primary">Accept results</button>`}
      <button id="dlWord" class="btn btn-ghost">⬇ Word</button>
      <button id="dlPdf" class="btn btn-ghost">⬇ PDF</button>
    </div>`;
}
function viewBusy(msg) {
  return `<div class="center"><div class="spinner-lg"></div><p class="sub">${esc(msg)}</p></div>`;
}

/* ---- handlers for the run sub-views ---- */
function busy(btn, on) {
  if (!btn) return;
  btn.disabled = on;
  btn.dataset.label = btn.dataset.label || btn.textContent;
  btn.innerHTML = on ? `<span class="spinner"></span> Working…` : btn.dataset.label;
}
async function step(btnId, fn) {
  const btn = document.getElementById(btnId);
  busy(btn, true);
  try { await fn(); } catch (e) { toast(e.message, true); busy(btn, false); }
}

function bindRunHandlers() {
  const r = state.run;

  const uploadBtn = document.getElementById("uploadBtn");
  if (uploadBtn) uploadBtn.onclick = () => step("uploadBtn", async () => {
    const protocol = document.getElementById("protocol").value.trim();
    const file = document.getElementById("dataFile").files[0];
    if (!protocol || !file) throw new Error("Add the protocol and a data file.");
    const fd = new FormData();
    fd.append("protocol", protocol);
    fd.append("data_file", file);
    state.run = await api(`/runs/${r.id}/upload`, { method: "POST", form: fd });
    render();
  });

  const estimateBtn = document.getElementById("estimateBtn");
  if (estimateBtn) estimateBtn.onclick = () => step("estimateBtn", async () => {
    const wc = parseInt(document.getElementById("wordCount").value, 10);
    state.run = await api(`/runs/${r.id}/estimate`, { method: "POST", body: { word_count: wc } });
    render();
  });

  const reEstimateBtn = document.getElementById("reEstimateBtn");
  if (reEstimateBtn) reEstimateBtn.onclick = async () => {
    // Go back to the word-count screen by treating the run as uploaded again (client-side).
    state.run = { ...state.run, status: "uploaded" }; render();
  };

  const agree = document.getElementById("agree");
  if (agree) agree.onchange = () => {
    const pb = document.getElementById("payBtn");
    if (pb) pb.disabled = !agree.checked;
  };

  const payBtn = document.getElementById("payBtn");
  if (payBtn) payBtn.onclick = () => step("payBtn", async () => {
    const link = await api(`/runs/${r.id}/pay-link`, { method: "POST" });
    // Open the gateway in a new tab, then poll for the confirmed payment.
    window.open(link.url, "_blank");
    toast("Opened payment page. Waiting for confirmation…");
    pollForPaid(r.id, link.reference);
  });

  const planBtn = document.getElementById("planBtn");
  if (planBtn) planBtn.onclick = () => step("planBtn", async () => {
    state.run = await api(`/runs/${r.id}/plan`, { method: "POST" }); render();
  });

  const approveBtn = document.getElementById("approveBtn");
  if (approveBtn) approveBtn.onclick = () => step("approveBtn", async () => {
    const orig = state.run.proposed_test || {};
    const edited = {
      name: document.getElementById("pName").value.trim(),
      reasoning: document.getElementById("pReason").value.trim(),
      variables: document.getElementById("pVars").value.split(",").map(s => s.trim()).filter(Boolean),
      assumptions: orig.assumptions || [],
      citations: orig.citations || [],
    };
    const changed = edited.name !== orig.name || edited.reasoning !== orig.reasoning
      || edited.variables.join(",") !== (orig.variables || []).join(",");
    const body = changed ? { confirmed: true, edited_plan: edited } : { confirmed: true };
    state.run = await api(`/runs/${r.id}/approve`, { method: "POST", body }); render();
  });

  document.querySelectorAll("#langChoices .choice").forEach(c => c.onclick = () => {
    state.language = c.dataset.lang;
    document.querySelectorAll("#langChoices .choice").forEach(x => x.classList.remove("active"));
    c.classList.add("active");
  });
  const genScriptBtn = document.getElementById("genScriptBtn");
  if (genScriptBtn) genScriptBtn.onclick = () => step("genScriptBtn", async () => {
    state.run = await api(`/runs/${r.id}/script?language=${state.language}`, { method: "POST" }); render();
  });

  const retryScript = document.getElementById("retryScript");
  if (retryScript) retryScript.onclick = () => step("retryScript", async () => {
    state.run = await api(`/runs/${r.id}/script?language=${state.language}`, { method: "POST" }); render();
  });

  const executeBtn = document.getElementById("executeBtn");
  if (executeBtn) executeBtn.onclick = () => step("executeBtn", async () => {
    state.run = await api(`/runs/${r.id}/execute`, { method: "POST" }); render();
  });

  const writeBtn = document.getElementById("writeBtn");
  if (writeBtn) writeBtn.onclick = () => step("writeBtn", async () => {
    state.run = await api(`/runs/${r.id}/results`, { method: "POST" }); render();
  });

  const acceptBtn = document.getElementById("acceptBtn");
  if (acceptBtn) acceptBtn.onclick = () => step("acceptBtn", async () => {
    state.run = await api(`/runs/${r.id}/accept`, { method: "POST" }); render();
  });

  const dlWord = document.getElementById("dlWord");
  if (dlWord) dlWord.onclick = () => downloadDoc("word");
  const dlPdf = document.getElementById("dlPdf");
  if (dlPdf) dlPdf.onclick = () => downloadDoc("pdf");
}

async function pollForPaid(id, reference) {
  // In production, EasyKash calls /payments/callback server-side. For local dev
  // (stub gateway) there's no real callback, so after a short grace period we
  // offer to simulate it.
  let tries = 0;
  const iv = setInterval(async () => {
    tries++;
    try {
      const run = await api("/runs/" + id);
      if (run.status !== "awaiting_payment") {
        clearInterval(iv); state.run = run; render(); toast("Payment confirmed.");
        return;
      }
    } catch (e) { /* keep polling */ }
    if (tries === 4) {
      if (confirm("No confirmation yet. Simulate a successful payment? (dev only)")) {
        clearInterval(iv);
        try {
          await api("/payments/callback", { method: "POST", body: { reference, status: "success" } });
          await refreshRun(); toast("Payment confirmed (simulated).");
        } catch (e) { toast(e.message, true); }
      }
    }
    if (tries > 20) clearInterval(iv);
  }, 2500);
}

async function downloadDoc(format) {
  try {
    const blob = await api(`/runs/${state.runId}/download?format=${format}`);
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `results_${state.runId}.${format === "pdf" ? "pdf" : "docx"}`;
    document.body.appendChild(a); a.click(); a.remove();
    URL.revokeObjectURL(url);
  } catch (e) { toast(e.message, true); }
}

/* ------------------------------ helpers -------------------------------- */
function labelScope(s) { return s === "thesis" ? "Thesis" : "Paper"; }
function statusPill(s) {
  const map = {
    completed: "ok", accepted: "ok", paid: "ok",
    failed: "err", expired: "err",
    awaiting_payment: "warn", awaiting_approval: "warn",
  };
  return `<span class="pill ${map[s] || "warn"}">${s.replace(/_/g, " ")}</span>`;
}

/* ------------------------------- Router -------------------------------- */
function render() {
  syncTopbar();
  if (!state.token) { state.view = "auth"; }
  switch (state.view) {
    case "auth": renderAuth(); break;
    case "forgot": renderForgot(); break;
    case "dashboard": renderDashboard(); break;
    case "newtask": renderNewTask(); break;
    case "run": state.run ? renderRun() : renderDashboard(); break;
    default: renderAuth();
  }
}

/* --------------------------- Bootstrap --------------------------------- */
(async function init() {
  if (state.token) {
    try { state.user = await api("/auth/me"); state.view = "dashboard"; }
    catch { state.token = null; localStorage.removeItem("ra_token"); state.view = "auth"; }
  }
  render();
})();
