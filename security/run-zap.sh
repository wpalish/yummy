#!/usr/bin/env bash
set -euo pipefail
: "${STAGING_URL:?STAGING_URL required}"
[[ "${ALLOW_DAST:-NO}" == "YES" ]] || { echo "Set ALLOW_DAST=YES"; exit 2; }
[[ "${TARGET_ENV:-}" == "staging" ]] || { echo "TARGET_ENV must be staging"; exit 3; }
case "$STAGING_URL" in *prod*|*www.*) echo "Refusing production-looking URL"; exit 4;; esac
mkdir -p security/reports
docker run --rm --network host \
  -v "$PWD/security:/zap/wrk/:rw" \
  ghcr.io/zaproxy/zaproxy:stable \
  zap-baseline.py -t "$STAGING_URL" -c zap-baseline.conf \
  -r reports/zap.html -J reports/zap.json
