#!/bin/bash
# =============================================================================
# EDQ Server Deployment Script
# One-command Docker deployment with optional built-in TLS bootstrap.
# =============================================================================

set -euo pipefail

EDQ_BIND_HOST="${EDQ_BIND_HOST:-127.0.0.1}"
EDQ_PUBLIC_PORT="${EDQ_PUBLIC_PORT:-3000}"
EDQ_PUBLIC_URL="${EDQ_PUBLIC_URL:-}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info() {
    echo -e "${GREEN}$1${NC}"
}

warn() {
    echo -e "${YELLOW}$1${NC}"
}

fail() {
    echo -e "${RED}$1${NC}"
    exit 1
}

read_env_value() {
    local key="$1"
    if [ ! -f .env ]; then
        return 0
    fi
    grep -E "^${key}=" .env | tail -n 1 | cut -d'=' -f2-
}

strip_quotes() {
    local value="$1"
    value="${value%\"}"
    value="${value#\"}"
    value="${value%\'}"
    value="${value#\'}"
    printf '%s' "$value"
}

looks_like_ipv4() {
    printf '%s' "$1" | grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$'
}

wait_for_http_health() {
    local url="$1"
    local attempts="${2:-60}"
    local healthy="false"

    for _ in $(seq 1 "$attempts"); do
        if curl -skf "$url" >/dev/null 2>&1; then
            healthy="true"
            break
        fi
        echo -n "."
        sleep 2
    done
    echo

    if [ "$healthy" != "true" ]; then
        return 1
    fi
    return 0
}

wait_for_https_health() {
    local domain="$1"
    local url="$2"
    local attempts="${3:-60}"
    local healthy="false"

    for _ in $(seq 1 "$attempts"); do
        if curl --resolve "${domain}:443:127.0.0.1" -skf "$url" >/dev/null 2>&1; then
            healthy="true"
            break
        fi
        echo -n "."
        sleep 2
    done
    echo

    if [ "$healthy" != "true" ]; then
        return 1
    fi
    return 0
}

print_admin_credentials() {
    local password="$1"
    echo
    echo "  =================================================="
    echo "  ADMIN CREDENTIALS - SAVE THESE"
    echo
    echo "  Username: admin"
    echo "  Password: ${password}"
    echo
    echo "  This password is shown only once."
    echo "  =================================================="
    echo
}

echo
echo "=================================================="
echo "EDQ Production Deployment"
echo "=================================================="
echo

if ! command -v docker >/dev/null 2>&1; then
    fail "Docker is not installed. Install it first."
fi

if ! docker compose version >/dev/null 2>&1; then
    fail "Docker Compose is not installed."
fi

info "Docker and Docker Compose found"

if [ ! -f .env ]; then
    warn "No .env file found. Creating production configuration..."
    echo

    JWT_SECRET=$(openssl rand -hex 64)
    JWT_REFRESH_SECRET=$(openssl rand -hex 64)
    SECRET_KEY=$(openssl rand -hex 32)
    TOOLS_API_KEY=$(openssl rand -hex 32)
    POSTGRES_PASSWORD=$(openssl rand -hex 24)
    ADMIN_PASSWORD=$(openssl rand -base64 18)

    echo -n "Enter server host or URL target (for example edq.company.com or 192.168.1.50): "
    read -r SERVER_HOST
    SERVER_HOST=${SERVER_HOST:-localhost}

    echo
    echo -n "Will this deployment use HTTPS/TLS? (Y/n): "
    read -r USE_HTTPS
    USE_HTTPS=${USE_HTTPS:-Y}

    BUILTIN_TLS="false"
    DOMAIN_VALUE=""
    LETSENCRYPT_EMAIL_VALUE=""
    COOKIE_SECURE="false"

    if [[ "$USE_HTTPS" =~ ^[Nn] ]]; then
        warn "COOKIE_SECURE=false - session cookies will be sent over plain HTTP."
        warn "This is acceptable for local/dev but not recommended for production."
    else
        COOKIE_SECURE="true"
        echo -n "Use EDQ's built-in HTTPS/certbot stack on this server? (y/N): "
        read -r ENABLE_BUILTIN_TLS
        if [[ "$ENABLE_BUILTIN_TLS" =~ ^[Yy] ]]; then
            BUILTIN_TLS="true"

            while true; do
                echo -n "Enter the public DNS name for HTTPS (for example edq.company.com): "
                read -r DOMAIN_VALUE
                DOMAIN_VALUE=${DOMAIN_VALUE:-}
                if [ -z "$DOMAIN_VALUE" ] || [ "$DOMAIN_VALUE" = "localhost" ] || looks_like_ipv4 "$DOMAIN_VALUE"; then
                    warn "Built-in TLS requires a public DNS name, not localhost or a raw IP address."
                    continue
                fi
                break
            done

            while true; do
                echo -n "Enter the Let's Encrypt notification email address: "
                read -r LETSENCRYPT_EMAIL_VALUE
                LETSENCRYPT_EMAIL_VALUE=${LETSENCRYPT_EMAIL_VALUE:-}
                if [ -z "$LETSENCRYPT_EMAIL_VALUE" ]; then
                    warn "A non-empty email address is required for built-in TLS."
                    continue
                fi
                break
            done
        else
            warn "COOKIE_SECURE=true assumes HTTPS is terminating before traffic reaches EDQ."
            warn "Use a reverse proxy/load balancer or keep COOKIE_SECURE=false until that is true."
        fi
    fi

    CORS_HOST="${SERVER_HOST}"
    if [ "$BUILTIN_TLS" = "true" ]; then
        CORS_HOST="${DOMAIN_VALUE}"
    fi

    cat > .env <<EOF
# EDQ Production Configuration
# Generated: $(date -u +"%Y-%m-%d %H:%M:%S UTC")

# Security
JWT_SECRET=${JWT_SECRET}
JWT_REFRESH_SECRET=${JWT_REFRESH_SECRET}
SECRET_KEY=${SECRET_KEY}
COOKIE_SECURE=${COOKIE_SECURE}
INITIAL_ADMIN_PASSWORD=${ADMIN_PASSWORD}
POSTGRES_PASSWORD=${POSTGRES_PASSWORD}

# Database
DATABASE_URL=
DB_DRIVER=postgresql+asyncpg
DB_HOST=127.0.0.1
DB_PORT=55432
DB_NAME=edq
DB_USER=edq
DB_PASSWORD=${POSTGRES_PASSWORD}
DB_CONNECT_TIMEOUT_SECONDS=15

# JWT
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=60
JWT_REFRESH_TOKEN_EXPIRE_DAYS=30

# CORS
CORS_ORIGINS=["http://${CORS_HOST}","https://${CORS_HOST}"]
DOMAIN=${DOMAIN_VALUE}
LETSENCRYPT_EMAIL=${LETSENCRYPT_EMAIL_VALUE}
EDQ_USE_BUILTIN_TLS=${BUILTIN_TLS}

# File Storage
UPLOAD_DIR=./uploads
REPORT_DIR=./reports

# Frontend publish settings
EDQ_BIND_HOST=${EDQ_BIND_HOST}
EDQ_PUBLIC_PORT=${EDQ_PUBLIC_PORT}
EDQ_BACKEND_BIND_HOST=127.0.0.1
EDQ_BACKEND_PORT=8000
EDQ_TOOLS_BIND_HOST=127.0.0.1
EDQ_TOOLS_PORT=8001
EDQ_POSTGRES_BIND_HOST=127.0.0.1
EDQ_POSTGRES_PORT=55432

# Tools Sidecar
TOOLS_SIDECAR_URL=http://localhost:8001
TOOLS_API_KEY=${TOOLS_API_KEY}

# AI Synopsis (optional)
AI_API_KEY=
AI_API_URL=
AI_MODEL=gpt-4o

# Logging
LOG_LEVEL=INFO
LOG_JSON=true
DEBUG=false

# Registration
ALLOW_REGISTRATION=false

# Frontend telemetry (optional)
VITE_API_URL=/api
VITE_CLIENT_ERROR_ENDPOINT=/api/client-errors
VITE_SENTRY_DSN=
VITE_SENTRY_ENVIRONMENT=production
VITE_SENTRY_RELEASE=
VITE_SENTRY_ENABLED=false
VITE_SENTRY_TRACES_SAMPLE_RATE=0.0
VITE_SOURCEMAP=false

# Sentry (backend, optional)
SENTRY_DSN=
SENTRY_ENVIRONMENT=production
SENTRY_RELEASE=
SENTRY_TRACES_SAMPLE_RATE=0.1
SENTRY_PROFILES_SAMPLE_RATE=0.0
SENTRY_LOG_LEVEL=INFO
SENTRY_EVENT_LEVEL=ERROR
EOF

    info ".env file created"
    print_admin_credentials "${ADMIN_PASSWORD}"
else
    info ".env file exists"
fi

ENV_DOMAIN=$(strip_quotes "$(read_env_value DOMAIN)")
ENV_LETSENCRYPT_EMAIL=$(strip_quotes "$(read_env_value LETSENCRYPT_EMAIL)")
ENV_USE_BUILTIN_TLS=$(strip_quotes "$(read_env_value EDQ_USE_BUILTIN_TLS)")

COMPOSE_ARGS=(-f docker-compose.yml)
COMPOSE_HINT="docker compose"
HEALTH_URL="${EDQ_PUBLIC_URL:-http://localhost:${EDQ_PUBLIC_PORT}/api/health}"

if [ "${ENV_USE_BUILTIN_TLS}" = "true" ]; then
    if [ -z "$ENV_DOMAIN" ]; then
        fail "EDQ_USE_BUILTIN_TLS=true requires DOMAIN in .env."
    fi
    if [ -z "$ENV_LETSENCRYPT_EMAIL" ]; then
        fail "EDQ_USE_BUILTIN_TLS=true requires LETSENCRYPT_EMAIL in .env."
    fi

    COMPOSE_ARGS+=(-f docker-compose.prod.yml)
    COMPOSE_HINT="docker compose -f docker-compose.yml -f docker-compose.prod.yml"
    HEALTH_URL="http://127.0.0.1/api/health"
    EDQ_PUBLIC_URL="https://${ENV_DOMAIN}"
elif [ -z "${EDQ_PUBLIC_URL}" ]; then
    EDQ_PUBLIC_URL="http://localhost:${EDQ_PUBLIC_PORT}"
fi

warn "Building and starting containers..."
echo
docker compose "${COMPOSE_ARGS[@]}" up -d --build

warn "Waiting for services to become healthy..."
if ! wait_for_http_health "$HEALTH_URL" 60; then
    fail "Services did not become healthy. Inspect logs with: ${COMPOSE_HINT} logs -f"
fi
info "All services are healthy"

if [ "${ENV_USE_BUILTIN_TLS}" = "true" ]; then
    warn "Requesting or renewing the Let's Encrypt certificate for ${ENV_DOMAIN}..."
    docker compose "${COMPOSE_ARGS[@]}" run --rm certbot \
        certonly \
        --webroot \
        -w /var/www/certbot \
        -d "${ENV_DOMAIN}" \
        --agree-tos \
        -m "${ENV_LETSENCRYPT_EMAIL}" \
        --non-interactive \
        --keep-until-expiring

    warn "Restarting the frontend to switch from HTTP bootstrap to HTTPS..."
    docker compose "${COMPOSE_ARGS[@]}" restart frontend

    warn "Waiting for HTTPS to become healthy..."
    if ! wait_for_https_health "${ENV_DOMAIN}" "${EDQ_PUBLIC_URL}/api/health" 60; then
        fail "HTTPS did not become healthy. Inspect logs with: ${COMPOSE_HINT} logs -f"
    fi
    info "HTTPS is healthy"
fi

echo "=================================================="
echo "EDQ is running"
echo "=================================================="
echo
echo "App URL:      ${EDQ_PUBLIC_URL}"
echo "Health URL:   ${EDQ_PUBLIC_URL}/api/health"
echo
echo "Container status:"
docker ps --format "  {{.Names}}\t{{.Status}}" | grep edq || true
echo
echo "Next steps:"
echo "  1. Open the URL above in a browser"
echo "  2. Log in with the admin credentials"
echo "  3. Create engineer and reviewer accounts"
echo "  4. Configure authorized networks before subnet scans"
echo
echo "Useful commands:"
echo "  ${COMPOSE_HINT} logs -f"
echo "  ${COMPOSE_HINT} down"
echo "  ${COMPOSE_HINT} up -d"
echo "  ${COMPOSE_HINT} up -d --build"
if [ "${ENV_USE_BUILTIN_TLS}" = "true" ]; then
    echo "  ${COMPOSE_HINT} run --rm certbot renew"
    echo "  ${COMPOSE_HINT} exec -T frontend nginx -s reload"
fi
echo
