#!/bin/bash
set -e
echo "=== EDQ Setup ==="

cd "$(dirname "$0")"

if [ ! -f .env ]; then
  cp .env.example .env
  JWT_SECRET=$(openssl rand -hex 64 2>/dev/null || python3 -c "import secrets; print(secrets.token_hex(64))")
  JWT_REFRESH_SECRET=$(openssl rand -hex 64 2>/dev/null || python3 -c "import secrets; print(secrets.token_hex(64))")
  SECRET_KEY=$(openssl rand -hex 32 2>/dev/null || python3 -c "import secrets; print(secrets.token_hex(32))")
  TOOLS_API_KEY=$(openssl rand -hex 32 2>/dev/null || python3 -c "import secrets; print(secrets.token_hex(32))")
  ADMIN_PASS=$(openssl rand -base64 16 2>/dev/null || python3 -c "import secrets; print(secrets.token_urlsafe(16))")
  sed -i "s|^JWT_SECRET=.*|JWT_SECRET=$JWT_SECRET|" .env
  sed -i "s|^JWT_REFRESH_SECRET=.*|JWT_REFRESH_SECRET=$JWT_REFRESH_SECRET|" .env
  sed -i "s|^SECRET_KEY=.*|SECRET_KEY=$SECRET_KEY|" .env
  sed -i "s|^TOOLS_API_KEY=.*|TOOLS_API_KEY=$TOOLS_API_KEY|" .env
  sed -i "s|^INITIAL_ADMIN_PASSWORD=.*|INITIAL_ADMIN_PASSWORD=$ADMIN_PASS|" .env
  echo "Created .env with random secrets"
  echo "  Admin password: $ADMIN_PASS"
fi

mkdir -p data

echo "Starting EDQ..."
docker compose up --build -d

echo ""
echo "Waiting for services to start..."
sleep 5

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
echo "  Login: username 'admin' / password from INITIAL_ADMIN_PASSWORD in .env"
echo "  (Change your password after first login)"
echo ""
echo "Useful commands:"
echo "  docker compose logs -f        # View live logs"
echo "  docker compose down            # Stop EDQ"
echo "  docker compose down -v         # Stop EDQ and remove data"
