#!/usr/bin/env bash
# Restore a backup made by scripts/backup.sh into the database named by EVENTHUB_DATABASE_URL.
#   EVENTHUB_DATABASE_URL=... scripts/restore.sh backups/eventhub-<stamp>.dump
# Objects in the dump are dropped and recreated: point this at a scratch database for a drill,
# or at production only after the steps in docs/runbooks/backup-restore.md.
set -euo pipefail

: "${EVENTHUB_DATABASE_URL:?EVENTHUB_DATABASE_URL is not set; refusing to run}"
file="${1:?usage: restore.sh <dump-file>}"
[ -f "$file" ] || { echo "no such dump file: $file" >&2; exit 1; }

url="${EVENTHUB_DATABASE_URL/postgresql+psycopg:/postgresql:}"

if ! pg_restore --clean --if-exists --no-owner --dbname="$url" "$file" 2>/dev/null; then
  echo "restore FAILED or finished with errors (details withheld so the connection string is never printed)" >&2
  exit 1
fi
echo "restored: $file"
