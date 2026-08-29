# Deployment & launch checklist

Two pieces deploy separately: the **backend** (FastAPI) on **Render**, and the
**frontend** (static SPA) on **Vercel**.

```
Vercel (frontend, static)  ──calls──►  Render (FastAPI + Postgres)
```

---

## 0. Push to GitHub (do this first)

From the project folder on your machine (Git Bash):

```bash
git push -u origin main
```

Everything below deploys from that repo. `.env` is git-ignored and never pushed.

---

## 1. Backend → Render

The repo includes `render.yaml`, so Render sets up the web service **and** a
Postgres database in one step.

1. Render dashboard → **New +** → **Blueprint** → connect this GitHub repo.
2. It creates `ai-research-assistant-api` + `ai-research-db`.
3. Fill in the environment variables (dashboard → the service → Environment):

| Variable | What to set | Notes |
|---|---|---|
| `LLM_API_KEY` | Your Gemini key | Use a **paid** key in prod (no training on your data) |
| `LLM_BASE_URL` | `https://generativelanguage.googleapis.com/v1beta/openai/` | default; change to switch provider |
| `LLM_MODEL` | `gemini-2.5-flash` (or `-flash-lite`) | |
| `CORS_ORIGINS` | your Vercel URL | e.g. `https://yourapp.vercel.app` |
| `FRONTEND_URL` | your Vercel URL | used to build verify/reset email links |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_USER` / `SMTP_PASSWORD` / `SMTP_FROM` | your mail provider | SendGrid/Mailgun/Gmail — needed for verify + reset emails |
| `EASYKASH_API_KEY` / `EASYKASH_WEBHOOK_SECRET` | from EasyKash portal | when your merchant account is live |
| `ADMIN_TOKEN` | a long random string | unlocks `/admin` (send in `X-Admin-Token`) |
| `PRICE_*` | your real prices (EGP) | optional — defaults exist |
| `JWT_SECRET` | (auto-generated) | leave it |
| `DATABASE_URL` | (auto-wired to Postgres) | leave it |

4. Deploy. Health check is `/health`; API is at `https://<your-app>.onrender.com`
   (docs at `/docs`).

### ⚠️ Script execution on Render — decide this

The analysis sandbox needs Docker, which Render's native runtime lacks, so
`/execute` won't run out of the box. Choose one:
- **MVP (quick, less safe):** set `SANDBOX_ALLOW_SUBPROCESS_FALLBACK=true` — runs
  the generated script **without container isolation**. OK for early trusted
  users only.
- **Proper:** run execution on a Docker-capable host (Fly.io Machines, a small
  VM, Fargate). Contained change — only `app/sandbox/docker_runner.py` is affected.

### Retention cleanup (cron)

Add a Render **Cron Job** (daily) running `python -m app.services.cleanup` on the
same repo + `DATABASE_URL` to purge files 30 days after acceptance.

---

## 2. Frontend → Vercel

1. Edit **`frontend/config.js`**:
   - `window.API_BASE` → your Render URL (no trailing slash).
   - `window.SUPPORT_WHATSAPP` → your WhatsApp number (digits only, with country code).
   - `window.SUPPORT_EMAIL` → your support email.
   Commit + push.
2. Vercel → **Add New → Project** → import this repo.
3. **Root Directory** = `frontend`; Framework = **Other**; no build command.
4. Deploy → `https://yourapp.vercel.app`.

---

## 3. Wire the two together

- On **Render**, set `CORS_ORIGINS` **and** `FRONTEND_URL` to your Vercel URL; redeploy.
- When EasyKash is live, set its **webhook URL** to
  `https://<your-render-url>/payments/callback`.

---

## 4. Free-tier caveats

- Render free web services **spin down when idle** (~30–60s cold start).
- Render free Postgres is time-limited — upgrade before it expires.
- Render's disk is **ephemeral** — uploaded files and generated docs don't survive
  a redeploy. For durability, move uploads/outputs to object storage (S3 / R2).

---

## Pre-launch checklist

**You (accounts / real-world):**
- [ ] `git push` to GitHub
- [ ] Gemini **paid** API key
- [ ] Email provider (SMTP) credentials
- [ ] EasyKash merchant account **activated** (ID + bank + the compliance pages) and API creds
- [ ] Legal glance at Terms / Refund / Privacy templates
- [ ] Real support **WhatsApp number + email** in `config.js`
- [ ] Real **prices** decided

**Deploy:**
- [ ] Render blueprint deployed; env vars set; `/health` green
- [ ] Execution decision made (subprocess flag vs. Docker host)
- [ ] Retention cron scheduled
- [ ] Frontend on Vercel; `config.js` → Render URL; `CORS_ORIGINS` + `FRONTEND_URL` set
- [ ] EasyKash webhook URL set + one real test payment
- [ ] `ADMIN_TOKEN` set (so you can see stats / issue refunds)

**Recommended before scaling:**
- [ ] Object storage for durable files
- [ ] Error monitoring (e.g. Sentry) + Postgres backups
- [ ] Validate more test types across real protocols
```
