#!/usr/bin/env bash
# Auto-deploy for Neura on the Hetzner box.
#
# Checks GitHub for new commits on `main`; if there are any, pulls them and
# rebuilds the stack. Run on a schedule by cron (see install command below), so
# a plain `git push` from your machine updates the server within a minute or two
# — just like Render/Vercel.
#
# It only rebuilds when something actually changed, so it's cheap to run often.
set -euo pipefail

REPO_DIR=/opt/neura
BRANCH=main
COMPOSE="docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env"

cd "$REPO_DIR"

git fetch --quiet origin "$BRANCH"
LOCAL=$(git rev-parse @)
REMOTE=$(git rev-parse "origin/$BRANCH")

if [ "$LOCAL" = "$REMOTE" ]; then
  exit 0   # nothing new
fi

echo "$(date -Is) new commit $REMOTE detected — deploying"
git pull --ff-only origin "$BRANCH"
$COMPOSE up -d --build
echo "$(date -Is) deploy complete"
