#!/bin/bash
# Restore a PostgreSQL SQL dump created by scripts/backup.sh.
#
# This is destructive. It stops the app, drops and recreates the configured
# Postgres database, restores the dump, then starts EDQ again.
#
# Usage:
#   EDQ_RESTORE_CONFIRM=restore ./scripts/restore-postgres.sh backups/edq_YYYYMMDD_HHMMSS.sql

set -euo pipefail

if [ "$#" -ne 1 ]; then
  echo "Usage: EDQ_RESTORE_CONFIRM=restore $0 <backup.sql>" >&2
  exit 2
fi

BACKUP_FILE="$1"

if [ ! -f "$BACKUP_FILE" ]; then
  echo "Backup file not found: $BACKUP_FILE" >&2
  exit 1
fi

if [ "${EDQ_RESTORE_CONFIRM:-}" != "restore" ]; then
  echo "Refusing destructive restore." >&2
  echo "Set EDQ_RESTORE_CONFIRM=restore to confirm you want to replace the current database." >&2
  exit 2
fi

echo "[EDQ Restore] Stopping application containers"
docker compose stop frontend backend

echo "[EDQ Restore] Copying backup into PostgreSQL container"
docker cp "$BACKUP_FILE" edq-postgres:/tmp/edq_restore.sql

echo "[EDQ Restore] Recreating and restoring database"
docker compose exec -T postgres sh -lc '
  set -e
  export PGPASSWORD="$POSTGRES_PASSWORD"
  psql -U "$POSTGRES_USER" -d postgres -v ON_ERROR_STOP=1 \
    -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '\''$POSTGRES_DB'\'' AND pid <> pg_backend_pid();"
  dropdb --if-exists -U "$POSTGRES_USER" "$POSTGRES_DB"
  createdb -U "$POSTGRES_USER" "$POSTGRES_DB"
  psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -f /tmp/edq_restore.sql
  rm -f /tmp/edq_restore.sql
'

echo "[EDQ Restore] Starting application containers"
docker compose up -d backend frontend

echo "[EDQ Restore] Complete"
