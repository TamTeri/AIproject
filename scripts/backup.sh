#!/usr/bin/env bash
# Back up the EventHub database (system-019). Dumps contain PII: see docs/runbooks/backup-restore.md.
#   EVENTHUB_DATABASE_URL=... scripts/backup.sh [output-dir]     (default: backups/)
set -euo pipefail

: "${EVENTHUB_DATABASE_URL:?EVENTHUB_DATABASE_URL is not set; refusing to run}"
umask 077
dir="${1:-backups}"
mkdir -p "$dir"
file="$dir/eventhub-$(date -u +%Y%m%dT%H%M%SZ).dump"

# SQLAlchemy-style "postgresql+psycopg://" is not a libpq URL; strip the driver suffix.
url="${EVENTHUB_DATABASE_URL/postgresql+psycopg:/postgresql:}"

if ! pg_dump --format=custom --no-owner --dbname="$url" --file="$file" 2>/dev/null; then
  rm -f "$file"
  echo "backup FAILED (details withheld so the connection string is never printed)" >&2
  exit 1
fi
echo "backup written: $file"
