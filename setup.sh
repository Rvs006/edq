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
ensure_env_value "JWT_SECRET" "$(generate_hex 64)" >/dev/null
ensure_env_value "JWT_REFRESH_SECRET" "$(generate_hex 64)" >/dev/null
ensure_env_value "SECRET_KEY" "$(generate_hex 32)" >/dev/null
ensure_env_value "TOOLS_API_KEY" "$(generate_hex 32)" >/dev/null
if ensure_env_value "INITIAL_ADMIN_PASSWORD" "$(generate_password)"; then
  GENERATED_ADMIN_PASS=$(grep -E "^INITIAL_ADMIN_PASSWORD=" .env | head -1 | cut -d= -f2- | tr -d '\r')
fi

mkdir -p data

echo "Starting EDQ..."
docker compose up --build -d

echo ""
echo "Waiting for services to start..."

RETRIES=0
MAX_RETRIES=30
until docker compose exec -T backend curl -sf http://localhost:8000/api/health >/dev/null 2>&1; do
  RETRIES=$((RETRIES + 1))
  if [ "$RETRIES" -ge "$MAX_RETRIES" ]; then
    echo "WARNING: Backend did not become healthy within timeout. Check logs with: docker compose logs backend"
    break
  fi
  sleep 2
done

echo ""
echo "=== EDQ is running at http://localhost ==="
echo "  Login: username 'admin' / password from INITIAL_ADMIN_PASSWORD in the root .env file"
if [ -n "$GENERATED_ADMIN_PASS" ]; then
  echo "  Generated initial admin password: $GENERATED_ADMIN_PASS"
fi
echo "  (Change your password after first login)"
echo ""
echo "Useful commands:"
echo "  docker compose logs -f        # View live logs"
echo "  docker compose down           # Stop EDQ"
echo "  docker compose down -v        # Stop EDQ and remove data"
