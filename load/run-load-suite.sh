#!/usr/bin/env bash
set -euo pipefail
: "${BASE_URL:?BASE_URL required}"
[[ "${ALLOW_LOAD_TEST:-NO}" == "YES" ]] || { echo "Set ALLOW_LOAD_TEST=YES"; exit 2; }
[[ "${TARGET_ENV:-}" == "staging" ]] || { echo "TARGET_ENV must be staging"; exit 3; }
case "$BASE_URL" in *prod*|*www.*) echo "Refusing production-looking URL"; exit 4;; esac
k6 run load/k6/catalog.js
if [[ -n "${BOX_ID:-}" ]]; then k6 run load/k6/last-box-race.js; fi
if [[ -n "${PARTNER_BEARER_TOKEN:-}" ]]; then k6 run load/k6/partner-operations.js; fi
