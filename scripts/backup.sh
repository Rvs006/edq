#!/bin/bash
# EDQ database backup script
# Usage: ./scripts/backup.sh [backup_dir]
set -e

BACKUP_DIR="${1:-./backups}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
mkdir -p "$BACKUP_DIR"

echo "[EDQ Backup] Starting backup at $TIMESTAMP"

DB_URL=$(docker compose exec -T backend python -c "from app.config import settings; print(settings.DATABASE_URL)" | tr -d '\r')

if [[ "$DB_URL" == postgresql* ]]; then
  docker compose exec -T postgres sh -lc '
    tmpfile=$(mktemp)
    trap "rm -f \"$tmpfile\"" EXIT
    printf "%s:%s:%s:%s:%s\n" localhost 5432 "$POSTGRES_DB" "$POSTGRES_USER" "$POSTGRES_PASSWORD" > "$tmpfile"
    chmod 600 "$tmpfile"
    export PGPASSFILE="$tmpfile"
    pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB"
  ' > "$BACKUP_DIR/edq_${TIMESTAMP}.sql"
  echo "[EDQ Backup] PostgreSQL dump saved: $BACKUP_DIR/edq_${TIMESTAMP}.sql"
else
  # Backup SQLite database using SQLite's online backup API for a consistent snapshot
  TEMP_BACKUP="/tmp/edq_${TIMESTAMP}.db"
  docker compose exec -T backend python -c "
import sqlite3
source = sqlite3.connect('/app/data/edq.db')
target = sqlite3.connect('${TEMP_BACKUP}')
with target:
    source.backup(target)
source.close()
target.close()
print('SQLite backup complete')
"
  docker cp "edq-backend:${TEMP_BACKUP}" "$BACKUP_DIR/edq_${TIMESTAMP}.db"
  docker compose exec -T backend rm -f "${TEMP_BACKUP}" >/dev/null 2>&1 || true
  echo "[EDQ Backup] SQLite backup saved: $BACKUP_DIR/edq_${TIMESTAMP}.db"
fi

# Backup uploads
docker cp edq-backend:/app/uploads "$BACKUP_DIR/uploads_${TIMESTAMP}" 2>/dev/null || echo "No uploads to backup"

# Keep only last 7 backups
ls -t "$BACKUP_DIR"/edq_*.* 2>/dev/null | tail -n +8 | xargs rm -f 2>/dev/null
echo "[EDQ Backup] Cleanup done. Keeping last 7 backups."
echo "[EDQ Backup] Complete!"
