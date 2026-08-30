#!/usr/bin/env bash
# One-command setup for a fresh Ubuntu 24.04 server (Hetzner CX22 or similar).
#
# It installs Docker, clones the repo, and starts the full stack (API + Postgres
# + Caddy with automatic HTTPS). Run it as root on the server:
#
#   curl -fsSL https://raw.githubusercontent.com/Abdelrahman-97/Ai-research-Assisstant/main/deploy/bootstrap.sh | bash
#
# ...or clone first and run  bash deploy/bootstrap.sh.  After it finishes it tells
# you to edit deploy/.env and re-run the compose command.
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/Abdelrahman-97/Ai-research-Assisstant.git}"
APP_DIR="${APP_DIR:-/opt/neura}"

echo "==> Installing Docker (if needed)…"
if ! command -v docker >/dev/null 2>&1; then
  apt-get update -y
  apt-get install -y ca-certificates curl git
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update -y
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi

echo "==> Fetching the app into ${APP_DIR}…"
if [ -d "${APP_DIR}/.git" ]; then
  git -C "${APP_DIR}" pull --ff-only
else
  git clone "${REPO_URL}" "${APP_DIR}"
fi
cd "${APP_DIR}"

if [ ! -f deploy/.env ]; then
  cp deploy/.env.example deploy/.env
  echo
  echo "======================================================================"
  echo " Created deploy/.env — you must edit it before the app will start."
  echo
  echo "   nano ${APP_DIR}/deploy/.env"
  echo
  echo " Fill in at least: API_DOMAIN, POSTGRES_PASSWORD, JWT_SECRET, LLM_API_KEY."
  echo " Tip: generate a secret with:   openssl rand -hex 32"
  echo " For API_DOMAIN before you own a domain, use your server IP via sslip.io,"
  echo " e.g. if the IP is 203.0.113.5 ->  203-0-113-5.sslip.io"
  echo
  echo " Then start everything with:"
  echo "   cd ${APP_DIR} && docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env up -d --build"
  echo "======================================================================"
  exit 0
fi

echo "==> Building and starting the stack…"
docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env up -d --build

echo
echo "==> Done. Check status with:  docker compose -f deploy/docker-compose.prod.yml ps"
echo "    Logs:                     docker compose -f deploy/docker-compose.prod.yml logs -f api"
