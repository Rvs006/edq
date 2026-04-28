#!/bin/bash
set -euo pipefail

echo "=== EDQ Setup ==="

cd "$(dirname "$0")"

generate_hex() {
  local bytes="$1"
  openssl rand -hex "$bytes" 2>/dev/null || python3 -c "import secrets; print(secrets.token_hex(${bytes}))"
}

generate_password() {
  local value
  value=$(openssl rand -base64 18 2>/dev/null | tr -d '\r\n' | tr '+/' 'AZ' | cut -c1-20 || true)
  if [ -n "$value" ]; then
    printf '%s\n' "$value"
    return 0
  fi
  python3 -c "import secrets; print(secrets.token_urlsafe(16))"
}

ensure_env_value() {
  local key="$1"
  local value="$2"
  local current
  if ! grep -q -E "^${key}=" .env; then
    printf '%s=%s\n' "$key" "$value" >> .env
    return 0
  fi
  current=$(grep -E "^${key}=" .env | head -1 | cut -d= -f2- | tr -d '\r' || true)
  if [ -z "$current" ] || [[ "$current" == CHANGE_ME* ]] || [[ "$current" == change-me* ]]; then
    sed -i "s|^${key}=.*|${key}=${value}|" .env
    return 0
  fi
  return 1
}

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created root .env from .env.example"
fi

GENERATED_ADMIN_PASS=""
ADMIN_ENV_KEY="INITIAL_ADMIN_PASSWORD"
POSTGRES_ENV_KEY="POSTGRES_PASSWORD"
ensure_env_value "JWT_SECRET" "$(generate_hex 64)" >/dev/null
ensure_env_value "JWT_REFRESH_SECRET" "$(generate_hex 64)" >/dev/null
ensure_env_value "SECRET_KEY" "$(generate_hex 32)" >/dev/null
ensure_env_value "TOOLS_API_KEY" "$(generate_hex 32)" >/dev/null
ensure_env_value "POSTGRES_PASSWORD" "$(generate_hex 24)" >/dev/null
if ensure_env_value "$ADMIN_ENV_KEY" "$(generate_password)"; then
  GENERATED_ADMIN_PASS=$(grep -E "^${ADMIN_ENV_KEY}=" .env | head -1 | cut -d= -f2- | tr -d '\r')
fi
POSTGRES_DB_CREDENTIAL=$(grep -E "^${POSTGRES_ENV_KEY}=" .env | head -1 | cut -d= -f2- | tr -d '\r')
ensure_env_value "DATABASE_URL" "" >/dev/null
if grep -q -E '^DATABASE_URL=.*sqlite' .env; then
  sed -i 's|^DATABASE_URL=.*|DATABASE_URL=|' .env
fi
ensure_env_value "DB_DRIVER" "postgresql+asyncpg" >/dev/null
ensure_env_value "DB_HOST" "127.0.0.1" >/dev/null
ensure_env_value "DB_PORT" "55432" >/dev/null
ensure_env_value "DB_NAME" "edq" >/dev/null
ensure_env_value "DB_USER" "edq" >/dev/null
ensure_env_value "DB_PASSWORD" "$POSTGRES_DB_CREDENTIAL" >/dev/null
ensure_env_value "DB_CONNECT_TIMEOUT_SECONDS" "15" >/dev/null
ensure_env_value "EDQ_BACKEND_BIND_HOST" "127.0.0.1" >/dev/null
ensure_env_value "EDQ_BACKEND_PORT" "8000" >/dev/null
ensure_env_value "EDQ_TOOLS_BIND_HOST" "127.0.0.1" >/dev/null
ensure_env_value "EDQ_TOOLS_PORT" "8001" >/dev/null
ensure_env_value "EDQ_POSTGRES_BIND_HOST" "127.0.0.1" >/dev/null
ensure_env_value "EDQ_POSTGRES_PORT" "55432" >/dev/null
ensure_env_value "VITE_API_URL" "/api" >/dev/null
ensure_env_value "VITE_CLIENT_ERROR_ENDPOINT" "/api/client-errors" >/dev/null
ensure_env_value "VITE_SENTRY_ENABLED" "false" >/dev/null
ensure_env_value "VITE_SENTRY_TRACES_SAMPLE_RATE" "0.0" >/dev/null
ensure_env_value "VITE_SOURCEMAP" "false" >/dev/null
ensure_env_value "LOG_JSON" "false" >/dev/null

mkdir -p data

PUBLIC_PORT_VALUE=$(grep -E "^EDQ_PUBLIC_PORT=" .env | head -1 | cut -d= -f2- | tr -d '\r')
PUBLIC_PORT_VALUE=${PUBLIC_PORT_VALUE:-3000}

echo "Starting EDQ..."
# Detect a previous install (existing edq-backend image). If found,
# force a --no-cache rebuild to avoid carrying forward broken cached
# layers from an earlier failed install. Adds ~2 min but eliminates
# the "Security Tools: Unavailable" class of first-install issues
# caused by stale image layers.
if [ -n "$(docker image ls -q edq-backend 2>/dev/null)" ]; then
  echo "Detected existing edq-backend image. Rebuilding with --no-cache to"
  echo "avoid stale cached layers (~2 min)."
  docker compose build --no-cache backend
fi
docker compose up --build -d

echo ""
echo "Waiting for services to start..."

RETRIES=0
MAX_RETRIES=30
until docker compose exec -T backend wget -qO /dev/null http://localhost:8000/api/v1/health >/dev/null 2>&1; do
  RETRIES=$((RETRIES + 1))
  if [ "$RETRIES" -ge "$MAX_RETRIES" ]; then
    echo "WARNING: Backend did not become healthy within timeout. Check logs with: docker compose logs backend"
    break
  fi
  sleep 2
done

echo ""
echo "=== EDQ is running at http://localhost:${PUBLIC_PORT_VALUE} ==="
echo "  Login: username 'admin' / password from INITIAL_ADMIN_PASSWORD in the root .env file"
if [ -n "$GENERATED_ADMIN_PASS" ]; then
  echo "  Generated initial admin password: $GENERATED_ADMIN_PASS"
fi
echo "  (Change your password after first login)"
echo "  After password rotation, set EDQ_ADMIN_PASS before running smoke scripts."
echo ""
echo "Useful commands:"
echo "  docker compose logs -f        # View live logs"
echo "  docker compose down           # Stop EDQ"
echo "  docker compose down -v        # Stop EDQ and remove data"
