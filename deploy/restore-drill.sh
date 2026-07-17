#!/usr/bin/env bash
set -euo pipefail
: "${DATABASE_URL:?production DATABASE_URL required for safety comparison}"
: "${RESTORE_DATABASE_URL:?dedicated RESTORE_DATABASE_URL required}"
: "${AGE_IDENTITY_FILE:?AGE_IDENTITY_FILE required}"
backup="${1:?usage: restore-drill.sh backup.dump.age}"
if [[ "$DATABASE_URL" == "$RESTORE_DATABASE_URL" ]]; then
  echo "REFUSING: restore target equals production" >&2; exit 10
fi
tmp="$(mktemp)"; trap 'rm -f "$tmp"' EXIT
sha256sum -c "$backup.sha256"
age -d -i "$AGE_IDENTITY_FILE" -o "$tmp" "$backup"
pg_restore --list "$tmp" >/dev/null
PGDATABASE="$RESTORE_DATABASE_URL" pg_restore --clean --if-exists --no-owner --no-acl "$tmp"
revision=$(PGDATABASE="$RESTORE_DATABASE_URL" psql -Atc 'select version_num from alembic_version')
[[ "$revision" == "20260714_0006" ]] || { echo "Bad revision: $revision"; exit 11; }
count=$(PGDATABASE="$RESTORE_DATABASE_URL" psql -Atc "select count(*) from information_schema.tables where table_schema='public'")
[[ "$count" -ge 15 ]] || { echo "Too few tables: $count"; exit 12; }
echo "RESTORE DRILL OK revision=$revision tables=$count"
