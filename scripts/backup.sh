#!/usr/bin/env bash
# EDQ Database Backup Script
# Creates timestamped backups of the SQLite database using .backup command
# (safe for WAL mode — produces a consistent snapshot)
#
# Usage:
#   ./scripts/backup.sh                    # Backup to ./backups/
#   ./scripts/backup.sh /path/to/backups   # Backup to custom directory
#   BACKUP_RETAIN_DAYS=30 ./scripts/backup.sh  # Keep backups for 30 days (default: 7)
#
# Crontab example (daily at 2am):
#   0 2 * * * cd /path/to/edq && ./scripts/backup.sh >> /var/log/edq-backup.log 2>&1

set -euo pipefail

BACKUP_DIR="${1:-./backups}"
RETAIN_DAYS="${BACKUP_RETAIN_DAYS:-7}"
DB_PATH="./data/edq.db"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/edq_backup_${TIMESTAMP}.db"

# Ensure backup directory exists
mkdir -p "${BACKUP_DIR}"

# Check database exists
if [ ! -f "${DB_PATH}" ]; then
    echo "[$(date -Iseconds)] ERROR: Database not found at ${DB_PATH}"
    exit 1
fi

# Use SQLite .backup command for WAL-safe backup
echo "[$(date -Iseconds)] Starting backup to ${BACKUP_FILE}..."
if command -v sqlite3 >/dev/null 2>&1; then
    sqlite3 "${DB_PATH}" ".backup '${BACKUP_FILE}'"
else
    # Fallback: use docker container's sqlite3 if available
    if docker ps --filter name=edq-backend --format '{{.Names}}' | grep -q edq-backend; then
        docker exec edq-backend python3 -c "
import sqlite3, shutil
src = sqlite3.connect('/app/data/edq.db')
dst = sqlite3.connect('/tmp/backup.db')
src.backup(dst)
src.close()
dst.close()
" && docker cp edq-backend:/tmp/backup.db "${BACKUP_FILE}"
    else
        echo "[$(date -Iseconds)] ERROR: No sqlite3 binary found and edq-backend container is not running."
        echo "Cannot safely back up a WAL-mode SQLite database with a file copy."
        echo "Install sqlite3 or ensure the edq-backend container is running."
        exit 1
    fi
fi

# Compress backup
if command -v gzip >/dev/null 2>&1; then
    gzip "${BACKUP_FILE}"
    BACKUP_FILE="${BACKUP_FILE}.gz"
fi

# Calculate size
BACKUP_SIZE=$(du -h "${BACKUP_FILE}" | cut -f1)
echo "[$(date -Iseconds)] Backup complete: ${BACKUP_FILE} (${BACKUP_SIZE})"

# Prune old backups
PRUNED=$(find "${BACKUP_DIR}" -name "edq_backup_*.db*" -mtime +"${RETAIN_DAYS}" -delete -print | wc -l)
if [ "${PRUNED}" -gt 0 ]; then
    echo "[$(date -Iseconds)] Pruned ${PRUNED} backup(s) older than ${RETAIN_DAYS} days"
fi

echo "[$(date -Iseconds)] Backup retention: ${RETAIN_DAYS} days"
