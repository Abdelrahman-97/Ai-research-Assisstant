# Neura — Roadmap

We build these **one at a time, together**. Captured so nothing is lost.

## ✅ Live now (v1 shipped)
- Full pipeline: upload → price → pay → AI plan (human-approved) → script preview
  → sandboxed run → Results section (Word + PDF).
- Analyst chat layer; interaction tiers (Basic/Standard/Pro).
- Output formatting: presets (Standard, APA, Vancouver, two-column), **match my
  document** (template upload), custom font/size/spacing, numbered figure/table
  captions with configurable start numbers, real tables, style-sample preview.
- Expert consultation add-ons: review (+500), full analysis (+3000).
- Custom domain + HTTPS, Zoho email, Budget pricing, Apple-academic redesign with
  light/dark toggle, keyless SSH + push-to-deploy.

---

## v1 — next, in order (agreed step-by-step)

### 1. Arabic support (first priority)
- ✅ **Generate results in Arabic** — DONE. Results write-up + headings + captions
  in Modern Standard Arabic; Word is fully right-to-left; PDF uses an Arabic font
  (Amiri) with proper shaping. Language picker at the results step. Numbers/stats
  stay in standard form to match the analysis.
- ✅ **Run Arabic data** — DONE. Uploaded CSV/TSV is auto-normalised to UTF-8;
  reads handle UTF-8 (incl. BOM) and Windows-Arabic (cp1256); the generated
  script is told to keep Arabic column names/values intact.
- ✅ **Arabic UI + RTL** — DONE. Language toggle (🌐 EN ⇄ ع) in the top bar flips
  the whole layout right-to-left and translates the interface (i18n.js).
  *(See "Languages" note below for how many we can offer.)*

### 2. Meta-analysis — ✅ engine + free tool built
Engine (`app/services/meta_analysis.py`) + public tool on `calculators.html`:
fixed/random effects, heterogeneity (Q, df, p, I², τ²), leave-one-out, subgroups,
per-study weights. **Still to do (v1 polish):** forest/funnel plot images and
optional integration into the paid pipeline + Word/PDF write-up.

Original scope for reference — a parallel analysis type with its own configuration:
- Pooled effect (fixed / random effects).
- **Heterogeneity** test (I², Q, τ²).
- **Sensitivity analysis** (leave-one-out).
- **Subgroup analysis**.
- Forest plot + funnel plot outputs.

### 3. Sample-size calculation — ✅ built (free tool)
- Power / sample-size for two-means (t-test), two-proportions, one-way ANOVA, and
  correlation, with inputs for effect size, power, alpha. Live on `calculators.html`.
  **Later:** survival / repeated-measures designs if demand appears.

### 4. Data preview on upload — ✅ built
- On upload, a **"Preview data & descriptives"** button shows the rows in a table
  plus a per-column summary (mean, SD, min/median/max, missing, unique/top). Live
  at the estimate step. **Later:** preliminary significance hints tied to the
  study protocol (that's really the paid analysis).

### 5. Founder / about — ✅ page scaffolded (needs your photo + bio)
- `about.html` is live with a founder section. **To personalise:** drop a square
  `founder.jpg` into `frontend/` and replace the placeholder circle + the bracketed
  bio text with your own (instructions are in the page).

### 6. Diagnostic / biomedical statistics — ✅ core built (free tool)
- Diagnostic-test metrics from a 2×2 with 95% CIs: **sensitivity, specificity,
  PPV, NPV, accuracy, prevalence, likelihood ratios, diagnostic OR**. Live on
  `calculators.html`. **Later:** ROC curve + AUC from raw data; agreement stats
  (Cohen's/Fleiss' kappa, Bland–Altman).

### 7. Require email verification before access — ✅ BUILT (off by default)
- A new account must **verify its email** before starting a job. Controlled by
  `REQUIRE_EMAIL_VERIFICATION` (default off). **To turn it on in production:** add
  `REQUIRE_EMAIL_VERIFICATION=true` to `/opt/neura/deploy/.env`, then
  `docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env up -d`.

---

## v2 — after v1
- **Consultant marketplace**: directory of vetted consultants with profiles and
  **ratings/reviews**; choosing a consultant routes the job to a human instead of
  the AI pipeline. (The +3000 "full expert" add-on is the first step.)
- **Blog / articles** section (SEO + credibility).
- **Social media manager (Facebook + Instagram only, for now)** — writes the posts,
  designs the images/graphics, and publishes them to Facebook & Instagram (via the
  Meta Graph API). Content generation + image design + scheduling/auto-posting.

---

## Languages — how many we can offer
The AI provider (DeepSeek) is strongly multilingual, so the **generated Results
text** can be produced in many languages. Realistic plan:
- **Start:** Arabic + English (Arabic needs RTL + encoding work — priority #1).
- **Easy to add next:** French, Spanish, German, Hindi, and other major languages —
  each needs (a) UI-string translation and (b) light QA of the generated academic
  wording. The statistics engine itself is language-neutral.
- **Bottom line:** output text ≈ any major language the model handles well; a fully
  *translated UI* is added language-by-language. Hindi is very doable after Arabic.

---

## Smaller improvements (backlog)
- Strip unused media from uploaded templates to keep output files small.
- Figure DPI / size options.
- More journal presets as demand shows which journals customers target.
- Inline figure/table placement (referenced in text) vs grouped at the end.
