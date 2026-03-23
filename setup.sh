#!/bin/bash
set -e
echo "=== EDQ Setup ==="

cd "$(dirname "$0")"

if [ ! -f .env ]; then
  cp .env.example .env
  JWT_SECRET=$(openssl rand -hex 64 2>/dev/null || python3 -c "import secrets; print(secrets.token_hex(64))")
  SECRET_KEY=$(openssl rand -hex 32 2>/dev/null || python3 -c "import secrets; print(secrets.token_hex(32))")
  sed -i "s/change-me-use-openssl-rand-hex-64/$JWT_SECRET/" .env
  sed -i "s/change-me-use-openssl-rand-hex-32/$SECRET_KEY/" .env
  echo "Created .env with random secrets"
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
echo "  Login: admin@electracom.co.uk / Admin123!"
echo "  (Change your password after first login)"
echo ""
echo "Useful commands:"
echo "  docker compose logs -f        # View live logs"
echo "  docker compose down            # Stop EDQ"
echo "  docker compose down -v         # Stop EDQ and remove data"
