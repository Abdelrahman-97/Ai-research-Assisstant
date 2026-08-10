# Deployment guide

Two pieces deploy separately: the **backend** (FastAPI) on **Render**, and the
**frontend** (static SPA) on **Vercel**.

```
Vercel (frontend, static)  ──calls──►  Render (FastAPI + Postgres)
```

---

## 0. Prerequisite: push to GitHub

From the project folder on your machine (Git Bash):

```bash
git push -u origin main
```

Everything below deploys from that repo.

---

## 1. Backend → Render

The repo includes `render.yaml`, so Render can set up the web service **and** a
Postgres database in one step.

1. Render dashboard → **New +** → **Blueprint** → connect this GitHub repo.
2. Render reads `render.yaml` and creates `ai-research-assistant-api` + `ai-research-db`.
3. Set the secret env vars (Render dashboard → the service → Environment):
   - `MOONSHOT_API_KEY` — your Kimi key (required for the AI steps).
   - `CORS_ORIGINS` — your Vercel URL, e.g. `https://yourapp.vercel.app`.
   - `EASYKASH_API_KEY`, `EASYKASH_WEBHOOK_SECRET` — when EasyKash is ready.
   - `JWT_SECRET` is auto-generated; `DATABASE_URL` is wired to the DB automatically.
4. Deploy. Health check is `/health`. Your API will be at
   `https://ai-research-assistant-api.onrender.com` (docs at `/docs`).

### ⚠️ Script execution on Render — read this

The analysis sandbox (`docker/Dockerfile.sandbox`) needs a Docker daemon, which
Render's native runtime does **not** provide. So out of the box `/execute` will
report that Docker is unavailable.

Options:
- **MVP (quick, less safe):** set `SANDBOX_ALLOW_SUBPROCESS_FALLBACK=true` on
  Render. The generated Python/R script then runs in a plain subprocess **without
  container isolation**. Since the script is AI-generated from user data, this is
  arbitrary code execution on your server — acceptable only for early testing with
  trusted users, never long-term.
- **Proper (recommended before real launch):** run execution on infrastructure
  that supports Docker — e.g. a small VM (Fly.io Machines, a Hetzner/DigitalOcean
  box, or AWS Fargate) that the API calls to run the sandbox container. The
  execution code is already isolated in `app/sandbox/docker_runner.py`, so this is
  a contained change.

### Retention cleanup

Add a Render **Cron Job** (daily) running `python -m app.services.cleanup` against
the same repo + `DATABASE_URL` to purge files 30 days after acceptance.

---

## 2. Frontend → Vercel

The frontend is plain static files in `frontend/` (no build step).

1. Edit **`frontend/config.js`** — set `window.API_BASE` to your Render URL
   (no trailing slash), commit, and push.
2. Vercel dashboard → **Add New** → **Project** → import this repo.
3. Set **Root Directory** to `frontend`. Framework preset: **Other**. No build
   command needed (`vercel.json` is included).
4. Deploy. You'll get `https://yourapp.vercel.app`.

---

## 3. Wire the two together

- On **Render**, set `CORS_ORIGINS` to your exact Vercel URL and redeploy (so the
  browser is allowed to call the API).
- When EasyKash is live, set its **webhook URL** to
  `https://<your-render-url>/payments/callback`.

---

## 4. Free-tier caveats

- Render free web services **spin down when idle**; the first request after
  idle takes ~30–60s to wake.
- Render free Postgres is time-limited — upgrade before it expires if you keep it.
- Uploaded files live on the service's disk; on Render's ephemeral filesystem they
  don't survive redeploys. For durable storage, move uploads/outputs to object
  storage (e.g. S3/R2) — another contained change, since paths are centralized.

---

## Pre-launch checklist

- [ ] `git push` to GitHub
- [ ] Render blueprint deployed; `MOONSHOT_API_KEY` set; `/health` green
- [ ] Decide the execution story (subprocess fallback vs. Docker VM)
- [ ] `frontend/config.js` points at Render; Vercel deployed
- [ ] `CORS_ORIGINS` on Render = Vercel URL
- [ ] EasyKash finalized + webhook URL set
- [ ] Real price numbers set in config
- [ ] Retention cron job scheduled
