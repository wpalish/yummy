#!/usr/bin/env bash
set -euo pipefail
: "${DATABASE_URL:?DATABASE_URL required}"
: "${AGE_RECIPIENT:?AGE_RECIPIENT required}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/yummy}"
mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"
name="yummy-$(date -u +%Y%m%dT%H%M%SZ).dump.age"
tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT
PGDATABASE="$DATABASE_URL" pg_dump --format=custom --no-owner --no-acl --file="$tmp"
pg_restore --list "$tmp" >/dev/null
age -r "$AGE_RECIPIENT" -o "$BACKUP_DIR/$name" "$tmp"
sha256sum "$BACKUP_DIR/$name" > "$BACKUP_DIR/$name.sha256"
find "$BACKUP_DIR" -type f -name 'yummy-*.dump.age*' -mtime +30 -delete
printf '{"last_backup":"%s","file":"%s"}\n' "$(date -u +%FT%TZ)" "$name" > "$BACKUP_DIR/status.json"
echo "Encrypted backup created: $BACKUP_DIR/$name"
