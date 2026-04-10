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
BOOTSTRAP_MODE="$(python - <<'PY'
import os
from sqlalchemy import create_engine, inspect, text

url = os.environ.get("DATABASE_URL", "sqlite:///./data/edq.db")
sync_url = url.replace("+aiosqlite", "").replace("+asyncpg", "")
engine = create_engine(sync_url)

with engine.connect() as conn:
    insp = inspect(conn)
    tables = set(insp.get_table_names())
    app_tables = tables - {"alembic_version"}
    version_rows = []
    if "alembic_version" in tables:
        try:
            version_rows = list(conn.execute(text("SELECT version_num FROM alembic_version")))
        except Exception:
            version_rows = []

if version_rows:
    print("upgrade")
elif app_tables:
    print("legacy")
else:
    print("upgrade")
PY
)"

if [ "$BOOTSTRAP_MODE" = "legacy" ]; then
    echo "[EDQ] Legacy database detected without Alembic revision state"
    python init_db.py
    alembic stamp head
else
    echo "[EDQ] Applying database migrations"
    alembic upgrade head
fi

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
