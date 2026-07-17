#!/usr/bin/env bash
set -euo pipefail
[[ "${ALLOW_CHAOS_TEST:-NO}" == "YES" ]] || { echo "Set ALLOW_CHAOS_TEST=YES"; exit 2; }
[[ "${TARGET_ENV:-}" == "staging" ]] || { echo "TARGET_ENV must be staging"; exit 3; }
case "${BASE_URL:-}" in *prod*|*www.*) echo "Refusing production-looking URL"; exit 4;; esac
compose=(docker compose -f deploy/docker-compose.production.yml --env-file .env.production)
recover(){ "${compose[@]}" start redis; }
"${compose[@]}" stop redis
trap recover EXIT
sleep 3
code=$(curl -ksS -o /tmp/yummy-health.json -w '%{http_code}' "${BASE_URL:?}/health")
[[ "$code" == "503" ]] || { echo "Expected 503, got $code"; exit 4; }
"${compose[@]}" start redis
trap - EXIT
sleep 5
code=$(curl -ksS -o /dev/null -w '%{http_code}' "$BASE_URL/health")
[[ "$code" == "200" ]] || { echo "Recovery failed: $code"; exit 5; }
echo "Redis outage drill OK"
