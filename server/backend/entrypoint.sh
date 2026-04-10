#!/bin/sh
set -eu

shutdown() {
    if [ "${BACKEND_PID:-}" != "" ]; then
        kill "$BACKEND_PID" 2>/dev/null || true
        wait "$BACKEND_PID" 2>/dev/null || true
    fi
    if [ "${TOOLS_PID:-}" != "" ]; then
        kill "$TOOLS_PID" 2>/dev/null || true
        wait "$TOOLS_PID" 2>/dev/null || true
    fi
}

trap 'shutdown; exit 143' INT TERM

# Start the tools sidecar first.
# Keep a single worker process because the sidecar tracks active subprocesses
# in memory, but allow multiple threads so health checks and control endpoints
# are not blocked by one long-running scan request.
cd /app/tools
gunicorn --bind 127.0.0.1:8001 --workers 1 --worker-class gthread --threads 8 --timeout 600 server:app &
TOOLS_PID=$!

ready=0
i=0
while [ "$i" -lt 30 ]; do
    if curl -sf http://localhost:8001/health >/dev/null 2>&1; then
        echo "[EDQ] Tools sidecar ready on :8001"
        ready=1
        break
    fi
    i=$((i + 1))
    sleep 1
done

if [ "$ready" -ne 1 ]; then
    echo "[EDQ] Tools sidecar failed to become ready"
    shutdown
    exit 1
fi

cd /app
echo "[EDQ] Waiting for database connectivity"
python - <<'PY'
import time

from sqlalchemy import create_engine, text

from app.config import settings


def to_sync_url(url: str) -> str:
    return url.replace("+aiosqlite", "").replace("+asyncpg", "")


last_error = None
for attempt in range(1, 31):
    try:
        engine = create_engine(to_sync_url(settings.DATABASE_URL), pool_pre_ping=True)
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        engine.dispose()
        print(f"[EDQ] Database reachable on attempt {attempt}")
        break
    except Exception as exc:  # pragma: no cover - startup retry path
        last_error = exc
        print(f"[EDQ] Database not ready yet (attempt {attempt}/30): {exc}")
        time.sleep(2)
else:
    raise SystemExit(f"[EDQ] Database failed to become ready: {last_error}")
PY

echo "[EDQ] Ensuring database schema is current"
python - <<'PY'
from app.models.database import ensure_database_schema_sync

ensure_database_schema_sync()
PY

uvicorn app.main:app --host 0.0.0.0 --port 8000 --loop uvloop --http httptools &
BACKEND_PID=$!

while :; do
    if ! kill -0 "$TOOLS_PID" 2>/dev/null; then
        echo "[EDQ] Tools sidecar exited unexpectedly"
        shutdown
        exit 1
    fi
    if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
        echo "[EDQ] Backend exited unexpectedly"
        shutdown
        exit 1
    fi
    sleep 2
done
