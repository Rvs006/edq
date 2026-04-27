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

case "$(printf '%s' "${EDQ_START_INTERNAL_TOOLS:-true}" | tr '[:upper:]' '[:lower:]')" in
    0|false|no|off) START_INTERNAL_TOOLS=false ;;
    *) START_INTERNAL_TOOLS=true ;;
esac

if [ "$START_INTERNAL_TOOLS" = "true" ]; then
# Start the tools sidecar first.
# Keep a single worker process because the sidecar tracks active subprocesses
# in memory, but allow multiple threads so health checks and control endpoints
# are not blocked by one long-running scan request.
cd /app/tools
gunicorn --bind 0.0.0.0:8001 --workers 1 --worker-class gthread --threads 8 --timeout 600 server:app &
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
sidecar_probe_url="http://localhost:8001/versions"
else
    echo "[EDQ] Internal tools sidecar disabled; backend will use TOOLS_SIDECAR_URL=${TOOLS_SIDECAR_URL:-<unset>}"
    if [ -n "${TOOLS_SIDECAR_URL:-}" ]; then
        sidecar_probe_url="${TOOLS_SIDECAR_URL%/}/versions"
    else
        sidecar_probe_url=""
    fi
fi

# Authenticated self-test: verify backend's TOOLS_API_KEY actually works
# against the configured scanner agent. Catches env-drift/key-mismatch deployments at boot
# instead of letting them silently mark "Security Tools: Unavailable" in
# the UI 30+ seconds after login.
if [ -n "${TOOLS_API_KEY:-}" ] && [ -n "${sidecar_probe_url:-}" ]; then
    auth_probe=$(curl -s -o /dev/null -w "%{http_code}" \
        -H "X-Tools-Key: ${TOOLS_API_KEY}" \
        "$sidecar_probe_url" 2>/dev/null || true)
    if [ "$auth_probe" != "200" ]; then
        echo "[EDQ] WARNING: authenticated scanner /versions probe returned HTTP ${auth_probe:-<none>}."
        echo "[EDQ] Automated scans may be unavailable until TOOLS_SIDECAR_URL and TOOLS_API_KEY match the scanner agent."
        # Non-fatal: container stays up so the UI can still render manual
        # tests and show the diagnostic banner. An env-mismatch should not
        # brick the whole stack — engineers still get to log in and fix it.
    else
        echo "[EDQ] Authenticated scanner /versions probe OK"
    fi
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
    if [ "${TOOLS_PID:-}" != "" ] && ! kill -0 "$TOOLS_PID" 2>/dev/null; then
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
