# Neura — Project Reference

Quick map of every service, URL, and console used to run **NeuraRESEARCH**.
Last updated: 2026-09-05.

> ⚠️ **No secrets in this file.** Passwords, API keys, and card details are NOT
> stored here. Keep those in a password manager. This file only holds public
> info: URLs, IPs, hostnames, plan names, and where to log in.

---

## 1. Domain

| | |
|---|---|
| **Domain** | neura-research.com |
| **Registrar** | Namecheap |
| **Manage DNS** | Namecheap → Domain List → Manage → **Advanced DNS** |
| **Renewal** | Annual (already paid for the year) |

### Current DNS records (Namecheap → Advanced DNS)

| Type | Host | Value | Purpose |
|---|---|---|---|
| A | `@` | `216.198.79.1` | Apex → Vercel (frontend) |
| A | `api` | `78.47.103.154` | api.neura-research.com → Hetzner (backend) |
| CNAME | `www` | `cname.vercel-dns.com.` | www → Vercel (frontend) |
| TXT | `@` | `zoho-verification=zb78246680.zmverify.zoho.com.au` | Zoho domain ownership |

*(MX / SPF / DKIM for Zoho email get added here next — see section 4.)*

---

## 2. Frontend — Vercel

| | |
|---|---|
| **Live site** | https://www.neura-research.com (apex redirects to www) |
| **Dashboard** | https://vercel.com/dashboard |
| **Plan** | Free (Hobby) |
| **Deploys** | Automatically on every push to GitHub `main` |
| **Config file** | `frontend/config.js` (API base URL, support contacts) |

---

## 3. Backend — Hetzner

| | |
|---|---|
| **API URL** | https://api.neura-research.com |
| **Health check** | https://api.neura-research.com/health |
| **Server IP** | 78.47.103.154 |
| **Server type** | CX23 (4 GB RAM) — ~$7.60/mo |
| **Cloud console** | https://console.hetzner.cloud |
| **SSH** | `ssh root@78.47.103.154` |
| **App folder** | `/opt/neura` |
| **Settings file** | `/opt/neura/deploy/.env` (holds all server secrets) |
| **Stack** | Docker Compose: API + Postgres + Caddy (auto-HTTPS) |

### Server commands (run over SSH)

```bash
# Update after a git push
cd /opt/neura && git pull && \
docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env up -d --build

# Logs
docker compose -f deploy/docker-compose.prod.yml logs -f api

# Restart
docker compose -f deploy/docker-compose.prod.yml restart

# Status
docker compose -f deploy/docker-compose.prod.yml ps
```

---

## 4. Email — Zoho Mail

| | |
|---|---|
| **Plan** | Mail Lite (5 GB, 1 user) — A$18/year |
| **Mailbox** | support@neura-research.com *(create after verification)* |
| **Admin console** | https://mailadmin.zoho.com.au |
| **Webmail (read mail)** | https://mail.zoho.com.au |
| **Login** | your Gmail (the admin account you signed up with) |
| **Region** | Australia (`.com.au`) |

### Setup status — ✅ COMPLETE
- [x] Domain added to Zoho
- [x] Domain verified (TXT)
- [x] Mailbox `support@neura-research.com` created
- [x] MX records added at Namecheap (green)
- [x] DKIM added (green)
- [x] SPF added (`v=spf1 include:zohomail.com.au ~all`) — may take a bit to go green in Zoho
- [x] SMTP wired into server `/opt/neura/deploy/.env` — test email SENT OK

**SMTP settings (in server .env):** host `smtp.zoho.com.au`, port `587`, TLS on,
user/from `support@neura-research.com`.
**Webmail:** https://mail.zoho.com.au · **App password** name: `neura-server`
(regenerate it — it was shown on screen during setup).

*(MX / SPF / DKIM values come from Zoho after verification — add them at
Namecheap Advanced DNS like the TXT above.)*

---

## 5. LLM provider — DeepSeek

| | |
|---|---|
| **Console** | https://platform.deepseek.com |
| **Billing** | Prepaid balance (top up as needed) |
| **Where configured** | Server `/opt/neura/deploy/.env` → `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL` |

---

## 6. Payments — EasyKash

| | |
|---|---|
| **Dashboard** | https://easykash.net |
| **Status** | Pending (Facebook/business verification) |
| **Fees** | % per customer transaction |
| **Where configured** | Server `.env` → EasyKash API key + webhook |

---

## 7. Code — GitHub

| | |
|---|---|
| **Repo** | https://github.com/Abdelrahman-97/Ai-research-Assisstant |
| **Branch** | `main` (push here → Vercel + server both update) |
| **Frontend** | `frontend/` |
| **Backend** | `app/` |
| **Deploy docs** | `deploy/DEPLOY-HETZNER.md` |

---

## 8. Costs

See **Neura-cost-tracker.xlsx** in this folder for the full breakdown.
Fixed cost ≈ **$9.60/month** (Hetzner $7.60 + Zoho ~$1 + domain ~$1),
plus DeepSeek usage and EasyKash per-sale fees.

---

## Where secrets live (NOT in this repo)

| Secret | Location |
|---|---|
| Server / DB / JWT / API keys | `/opt/neura/deploy/.env` on the Hetzner server |
| Zoho login | your Gmail + password manager |
| DeepSeek / EasyKash / Namecheap / Hetzner / Vercel logins | password manager |

**To do:** rotate the DeepSeek and old Gemini keys that were pasted in chat,
then update `/opt/neura/deploy/.env` and redeploy.

---

## ⚠️ Morning: rebuild the backend to activate new features

Code was pushed overnight (Vercel frontend auto-deployed; the Hetzner backend
does NOT auto-update). SSH in and run:

```bash
cd /opt/neura && git pull && \
docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env up -d --build
curl https://api.neura-research.com/health
```

Until you run this, the new format picker / consultation options degrade
gracefully (the site keeps working; results just use the default format).

## Selling prices (Budget tier — live in code)

| Item | EGP |
|---|---|
| Base — thesis chapter | 600 |
| Base — paper results | 350 |
| Per statistical test | 100 |
| Per 1,000 words | 40 |
| Per 1,000 data cells | 10 |
| Assistant Standard / Pro | +75 / +200 |
| Expert review add-on | +500 |
| Full expert analysis add-on | +3,000 |

Change these in `app/config.py` (pricing block + ASSISTANT_TIERS), then rebuild.

## New this session (needs the rebuild above)
- **Output format options**: Standard, APA 7, Vancouver, Two-column, Custom, and
  **Match my document** (upload thesis/paper → output uses its exact styles).
- **Instant style-sample preview** (PDF) before writing results.
- **Tables rendered as real tables**, **numbered figure/table captions** with a
  configurable **start number**, spacing and heading-numbering controls.
- **Expert consultation** add-ons (review +500 / full +3000).
- **UI redesign**: Apple-academic theme — serif headings, teal accent, pill
  buttons, frosted top bar, smooth motion, and a **light/dark toggle** (Auto /
  Light / Dark) in the top bar. Applied across every page. Frontend-only, so it
  goes live as soon as you push (Vercel); no server rebuild needed for the look.
- See `ROADMAP.md` for the blog and consultant-marketplace ideas.

**Note:** two commits are waiting to be pushed (formatting/consultation +
redesign). A single `git push` ships both.
