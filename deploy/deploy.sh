#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
test -f .env.production || { echo "Missing .env.production"; exit 2; }
chmod 600 .env.production
docker compose -f deploy/docker-compose.production.yml --env-file .env.production config >/dev/null
docker compose -f deploy/docker-compose.production.yml --env-file .env.production build --pull
docker compose -f deploy/docker-compose.production.yml --env-file .env.production run --rm app alembic upgrade head
docker compose -f deploy/docker-compose.production.yml --env-file .env.production up -d --remove-orphans
sleep 5
docker compose -f deploy/docker-compose.production.yml --env-file .env.production ps
