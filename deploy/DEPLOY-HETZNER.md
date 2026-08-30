# Deploy Neura on a Hetzner server (~€4/month)

This runs the whole backend — API + Postgres + automatic HTTPS — on one small
server. The frontend stays on Vercel. Total time ~15 minutes.

You do three things: (1) create the server, (2) run one setup command, (3) fill in
a settings file and start it. Copy‑paste is fine throughout.

---

## 1. Create the server

1. Sign up at **https://console.hetzner.cloud** and create a **project**.
2. **Add Server**:
   - **Location:** pick the one nearest your users (e.g. Nuremberg/Falkenstein for
     EU, Ashburn for US).
   - **Image:** **Ubuntu 24.04**.
   - **Type:** **CX22** (2 vCPU, 4 GB RAM) — this is the ~€3.79/mo one.
   - **SSH key:** add one if you have it; otherwise choose **password** and Hetzner
     emails you a root password.
   - Leave the rest default. **Create & Buy**.
3. Copy the server's **public IP** (e.g. `203.0.113.5`).

## 2. Connect and run the setup

Open a terminal (Mac/Linux Terminal, or Windows PowerShell) and log in — replace
the IP with yours:

```bash
ssh root@203.0.113.5
```

(Accept the fingerprint; enter the password if asked.)

Then run the one‑command setup:

```bash
curl -fsSL https://raw.githubusercontent.com/Abdelrahman-97/Ai-research-Assisstant/main/deploy/bootstrap.sh | bash
```

It installs Docker, downloads the app to `/opt/neura`, and creates a settings
file. It will stop and tell you to edit that file.

## 3. Fill in settings and start

Open the settings file:

```bash
nano /opt/neura/deploy/.env
```

Fill in at least these (leave the rest blank for now):

- **`API_DOMAIN`** — where the API is reached, and what HTTPS is issued for.
  - Before you own a domain, use your server IP via **sslip.io** with **dashes**:
    IP `203.0.113.5` → `API_DOMAIN=203-0-113-5.sslip.io`
  - Once you have a domain, point a subdomain at the IP (an **A record**
    `api.yourdomain.com → 203.0.113.5`) and set `API_DOMAIN=api.yourdomain.com`.
- **`POSTGRES_PASSWORD`** — a long random string. Generate one: `openssl rand -hex 32`
- **`JWT_SECRET`** — another random string: `openssl rand -hex 32`
- **`LLM_API_KEY`** — your DeepSeek key (`LLM_BASE_URL`/`LLM_MODEL` are already set).
- **`CORS_ORIGINS`** and **`FRONTEND_URL`** — your Vercel URL
  (`https://ai-research-assisstant.vercel.app`).

Save in nano: `Ctrl+O`, `Enter`, then `Ctrl+X`.

Start everything:

```bash
cd /opt/neura
docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env up -d --build
```

First build takes a few minutes (it installs the scientific stack). Check it:

```bash
docker compose -f deploy/docker-compose.prod.yml ps
curl -k https://$(grep API_DOMAIN deploy/.env | cut -d= -f2)/health
```

You should see `{"status":"ok"}`. Your API is now live at
`https://<API_DOMAIN>`.

## 4. Point the frontend at the new API

In the repo, edit `frontend/config.js`:

```js
window.API_BASE = "https://<API_DOMAIN>";   // e.g. https://api.yourdomain.com
```

Commit + push — Vercel redeploys automatically. (Tell me the API_DOMAIN and I'll
make this change for you.)

---

## Day‑to‑day

- **Update after a code change** (you push to GitHub):
  ```bash
  cd /opt/neura && git pull && \
  docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env up -d --build
  ```
- **Logs:** `docker compose -f deploy/docker-compose.prod.yml logs -f api`
- **Restart:** `docker compose -f deploy/docker-compose.prod.yml restart`
- **Backups:** the Postgres data lives in the `pgdata` volume; enable Hetzner's
  automated backups (a few % of the server cost) for peace of mind.

## Notes

- **Execution mode:** the app runs analyses inline on this box using the hardened
  subprocess path (stripped environment + CPU/memory caps). With 4 GB RAM this
  runs scipy/statsmodels/matplotlib comfortably.
- **Stronger isolation (optional, later):** the repo also ships a Docker sandbox
  image (`docker/Dockerfile.sandbox`) and a socket‑mounted compose for running each
  analysis in a network‑isolated container. That needs a shared runs directory so
  the host daemon can see the work folder — ask me to wire it up when you want it.
- **Firewall:** Hetzner Cloud Firewall — allow inbound 22 (SSH), 80, 443 only.
