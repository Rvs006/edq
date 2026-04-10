#!/bin/bash
# EDQ database backup script
# Usage: ./scripts/backup.sh [backup_dir]
set -e

BACKUP_DIR="${1:-./backups}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
mkdir -p "$BACKUP_DIR"

echo "[EDQ Backup] Starting backup at $TIMESTAMP"

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
echo "[EDQ Backup] Database saved: $BACKUP_DIR/edq_${TIMESTAMP}.db"

# Backup uploads
docker cp edq-backend:/app/uploads "$BACKUP_DIR/uploads_${TIMESTAMP}" 2>/dev/null || echo "No uploads to backup"

# Keep only last 7 backups
ls -t "$BACKUP_DIR"/edq_*.db 2>/dev/null | tail -n +8 | xargs rm -f 2>/dev/null
echo "[EDQ Backup] Cleanup done. Keeping last 7 backups."
echo "[EDQ Backup] Complete!"
