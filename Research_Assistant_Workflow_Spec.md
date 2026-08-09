# AI Research Assistant — Workflow Spec

**Version:** 0.1
**Last updated:** 2026-08-09
**Status:** Design captured from product owner. Source of truth for the v1 pipeline.

---

## 1. Overview

A web application that produces a **Results section** for researchers from their own data and study protocol. The AI proposes the statistical plan and drafts the writing; a human confirms every judgment call; nothing is treated as fact until a script has actually executed against the data and the AI has verified the output.

**Initial market:** researchers, particularly Egyptian PhD students.
**LLM provider (v1):** Kimi API (Moonshot AI).
**v1 task scope:** Results section only. The task-selection step is built to accept more task types later, but only "Results section" is offered now.

---

## 2. Core principles

- **AI proposes, human confirms.** The statistical plan is never executed until the user approves (or edits) it.
- **Grounded output.** The Results section is written strictly from artifacts produced by real script execution — not from the AI's assumptions.
- **Isolated execution.** Generated Python/R scripts run in a sandbox (Docker, no network, strict timeout), separate from the backend.
- **Extensible task model.** Sign-up offers a choice of task; today only Results section exists.

---

## 3. End-to-end workflow

```
Sign up / Sign in
      │
      ▼
Choose task  ─────────────►  (v1: only "Results section")
      │
      ▼
Choose scope  ────────────►  Thesis  |  Studies
      │
      ▼
Payment (EasyKash link)
      │  EasyKash API → payment-success callback → unlock access
      ▼
Upload:  (a) protocol / methods   (b) data file (e.g. Excel)
      │
      ▼
AI (Kimi) analyzes data + protocol  ──►  proposes STATISTICAL PLAN
      │
      ▼
◆ HUMAN CHECKPOINT ◆  user APPROVES or EDITS the plan
      │                         │
      │◄──── edited plan ───────┘
      ▼ (approved)
AI writes Python or R script
      │
      ▼
Script executes in sandbox  ──►  output / artifacts returned to AI
      │
      ▼
AI analyzes + VERIFIES the output
      │
      ▼
AI writes the RESULTS SECTION  ──►  export (Markdown → .docx)
```

---

## 4. Stage detail

### 4.1 Authentication
- Sign up and sign in.
- Sign-up captures the user's chosen **task** and **scope** (see below).

### 4.2 Task selection
- Presented at sign-up.
- Designed as a list of task types; **v1 exposes only "Results section."**

### 4.3 Scope selection
- For the Results-section task, the user specifies whether the work is for a **thesis** or **studies**.
- Scope may influence tone, length, and structure of the generated Results section. *(Exact differences: open decision — see §7.)*

### 4.4 Payment
- User receives an **EasyKash** payment link (Egyptian payment gateway).
- On successful payment, **EasyKash sends a success callback/webhook to our system's API.**
- Receiving a valid success callback **unlocks access** for that user to proceed to upload.
- *(Verification of callback authenticity, and mapping a payment to a user/session: open decision — see §7.)*

### 4.5 Upload
- User uploads two inputs:
  1. **Protocol / methods** of the paper.
  2. **Data file** containing the study data (e.g. Excel `.xlsx`).
- Files are validated (readable, non-empty, columns detectable) before analysis.

### 4.6 AI planning (Kimi)
- The protocol + a summary of the data are sent to the **Kimi API**.
- The AI returns a **statistical plan**: proposed test(s), reasoning, assumptions, and (where possible) citable methodology.

### 4.7 Human checkpoint — approve or edit the plan
- The proposed plan is shown to the user.
- The user **approves** it, or **edits/overrides** it.
- If edited, the revised plan goes back to the AI before any script is written.
- **No script runs until the plan is approved.**

### 4.8 AI writes the script
- Once the plan is approved, the AI writes the analysis **script in Python or R**.
- *(Script preview before execution: recommended, carried over from earlier design — open decision whether to expose in v1, see §7.)*

### 4.9 Execution
- The script runs in the **sandbox** (Docker container, non-AI, no network, strict timeout).
- Output and artifacts (tables, figures, raw output) are collected and returned to the AI.

### 4.10 Verify + write Results
- The AI analyzes and **verifies** the execution output.
- The AI writes the **Results section**, grounded strictly in the verified artifacts.
- Output is produced in Markdown and exported to **Word (.docx)**.

---

## 5. System components

| Component | Responsibility | Runs where |
|---|---|---|
| Frontend | Sign up/in, task + scope selection, payment redirect, upload, plan approval UI, download | Browser |
| Backend (FastAPI) | Auth, payment callback endpoint, orchestrating the pipeline, serving results | Local process (containerize later) |
| LLM client (Kimi) | Propose plan, write script, verify output, write Results section | Backend (calls Kimi API) |
| Sandbox | Execute generated Python/R scripts in isolation | Docker container (separate, no network) |
| Storage / DB | Users, sessions, payments, uploads, run state, artifact metadata | **Not yet decided** (see §7) |

---

## 6. Tech stack (v1)

- **Backend:** Python, FastAPI, Pydantic.
- **LLM:** Kimi API (Moonshot AI).
- **Execution sandbox:** Docker (local first), Python + R.
- **Export:** Markdown → `.docx` (python-docx).
- **Data handling:** pandas, openpyxl.
- **Payment:** EasyKash (link + success callback).

---

## 7. Open decisions

1. **Database** — whether to add one now, and if so which (e.g. Postgres) and whether in Docker. Needed to persist users, payments, uploads, and run state.
2. **Payment ↔ user mapping** — how EasyKash's success callback is authenticated and tied back to the correct user/session before unlocking access.
3. **Scope differences** — concretely how "thesis" vs "studies" changes the generated Results section (length, tone, structure).
4. **Script preview** — whether the user sees the generated script before it executes in v1.
5. **Auth mechanism** — email/password vs. provider login; session vs. JWT.
6. **Retry / edit loops** — how many times a user can edit the plan, and whether they can re-run after seeing results.

---

## 8. Not in v1 (deferred)

- Literature search layer (OpenAlex / PubMed / Semantic Scholar), reference management.
- Risk-of-bias / quality assessment tools.
- Meta-analysis.
- Automated/self-serve payment reconciliation beyond the basic success callback.
- Hosting/deployment (local pipeline proven first).
