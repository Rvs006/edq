#!/bin/bash
# =============================================================================
# EDQ Server Deployment Script
# Electracom Device Qualifier — One-command production deployment
#
# Usage:
#   chmod +x deploy.sh
#   ./deploy.sh
#
# Prerequisites:
#   - Ubuntu 22.04+ (or any Linux with Docker)
#   - Docker and Docker Compose installed
#   - Root or sudo access
# =============================================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}╔══════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║  EDQ — Electracom Device Qualifier       ║${NC}"
echo -e "${GREEN}║  Production Deployment                   ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════╝${NC}"
echo ""

# Check Docker
if ! command -v docker &> /dev/null; then
    echo -e "${RED}Docker is not installed.${NC}"
    echo "Install it with: curl -fsSL https://get.docker.com | sh"
    exit 1
fi

if ! command -v docker compose &> /dev/null && ! docker compose version &> /dev/null; then
    echo -e "${RED}Docker Compose is not installed.${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Docker and Docker Compose found${NC}"

# Generate .env if it doesn't exist
if [ ! -f .env ]; then
    echo ""
    echo -e "${YELLOW}No .env file found. Creating production configuration...${NC}"
    echo ""

    # Generate secrets
    JWT_SECRET=$(openssl rand -hex 64)
    JWT_REFRESH_SECRET=$(openssl rand -hex 64)
    SECRET_KEY=$(openssl rand -hex 32)
    TOOLS_API_KEY=$(openssl rand -hex 32)
    ADMIN_PASSWORD=$(openssl rand -base64 18)

    # Ask for server IP/domain
    echo -n "Enter server IP or domain (e.g., 192.168.1.50 or edq.company.com): "
    read -r SERVER_HOST
    SERVER_HOST=${SERVER_HOST:-localhost}

    cat > .env << EOF
# EDQ Production Configuration
# Generated: $(date -u +"%Y-%m-%d %H:%M:%S UTC")

# Security — unique cryptographic secrets
JWT_SECRET=${JWT_SECRET}
JWT_REFRESH_SECRET=${JWT_REFRESH_SECRET}
SECRET_KEY=${SECRET_KEY}
COOKIE_SECURE=false
INITIAL_ADMIN_PASSWORD=${ADMIN_PASSWORD}

# Database
DATABASE_URL=sqlite+aiosqlite:///./data/edq.db

# JWT
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=60
JWT_REFRESH_TOKEN_EXPIRE_DAYS=30

# CORS
CORS_ORIGINS=["http://${SERVER_HOST}","https://${SERVER_HOST}"]

# File Storage
UPLOAD_DIR=./uploads
REPORT_DIR=./reports

# Tools Sidecar
TOOLS_SIDECAR_URL=http://tools:8001
TOOLS_API_KEY=${TOOLS_API_KEY}

# AI Synopsis (optional)
AI_API_KEY=
AI_API_URL=
AI_MODEL=gpt-4o

# Logging
LOG_LEVEL=INFO
DEBUG=false

# Registration (set true to allow engineers to self-register)
ALLOW_REGISTRATION=false
EOF

    echo ""
    echo -e "${GREEN}✓ .env file created${NC}"
    echo ""
    echo -e "  ╔══════════════════════════════════════════════════╗"
    echo -e "  ║  ${YELLOW}ADMIN CREDENTIALS — SAVE THESE!${NC}                  ║"
    echo -e "  ║                                                  ║"
    echo -e "  ║  Username: ${GREEN}admin${NC}                                 ║"
    echo -e "  ║  Password: ${GREEN}${ADMIN_PASSWORD}${NC}  ║"
    echo -e "  ║                                                  ║"
    echo -e "  ║  ${RED}This password is shown only once!${NC}                ║"
    echo -e "  ╚══════════════════════════════════════════════════╝"
    echo ""
else
    echo -e "${GREEN}✓ .env file exists${NC}"
fi

# Build and start
echo ""
echo -e "${YELLOW}Building and starting containers (first run takes 3-5 minutes)...${NC}"
echo ""

docker compose up -d --build 2>&1

# Wait for health
echo ""
echo -e "${YELLOW}Waiting for services to become healthy...${NC}"

for i in $(seq 1 60); do
    if curl -sf http://localhost:80/api/health > /dev/null 2>&1; then
        echo ""
        echo -e "${GREEN}✓ All services are healthy!${NC}"
        break
    fi
    echo -n "."
    sleep 2
done

# Final status
echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║  EDQ is running!                                 ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  App URL:       ${GREEN}http://$(hostname -I 2>/dev/null | awk '{print $1}' || echo 'localhost')${NC}"
echo -e "  Health check:  curl http://localhost/api/health"
echo ""
echo -e "  Container status:"
docker ps --format "    {{.Names}}\t{{.Status}}" | grep edq
echo ""
echo -e "  ${YELLOW}Next steps:${NC}"
echo -e "  1. Open the URL above in a browser"
echo -e "  2. Log in with the admin credentials"
echo -e "  3. Create engineer accounts via Admin panel"
echo -e "  4. Engineers access the same URL from their browsers"
echo ""
echo -e "  ${YELLOW}Useful commands:${NC}"
echo -e "  docker compose logs -f          # View live logs"
echo -e "  docker compose down             # Stop EDQ"
echo -e "  docker compose up -d            # Start EDQ"
echo -e "  docker compose up -d --build    # Rebuild and start"
echo ""
