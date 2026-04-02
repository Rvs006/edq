# EDQ Production Deployment Guide

This guide is for shared or production-style deployments. It is not the local engineer setup guide.

For local testing on a single laptop, use [INSTALL.md](INSTALL.md).

## Deployment Model

EDQ runs as three services:

- `frontend`: nginx and the built frontend
- `backend`: FastAPI application
- `tools`: scan tooling sidecar

Optional production HTTPS support is provided through `docker-compose.prod.yml`.

## Prerequisites

- Docker Engine or Docker Desktop
- Docker Compose
- A private network or VPN-only access path
- A domain name and TLS certificates if you plan to expose EDQ beyond localhost

## Production Config Preparation

1. Create the root `.env`
2. Set strong values for:
   - `JWT_SECRET`
   - `JWT_REFRESH_SECRET`
   - `SECRET_KEY`
   - `TOOLS_API_KEY`
   - `INITIAL_ADMIN_PASSWORD`
3. Set production-safe values for:
   - `COOKIE_SECURE=true`
   - `DEBUG=false`
   - `CORS_ORIGINS` to your real domain(s)
4. Do not rely on placeholder values from `.env.example`

## Start Without HTTPS

Only use this on a trusted private network.

```bash
docker compose up --build -d
```

Health endpoint:

```bash
curl http://localhost/api/health
```

## Start With HTTPS

1. Set `DOMAIN` in the root `.env`
2. Obtain certificates
3. Start with the production override:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

The production override:

- binds ports `80` and `443`
- enables nginx TLS config
- sets `COOKIE_SECURE=true` for the backend

## Operations

Start:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

Stop:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml down
```

View logs:

```bash
docker compose logs -f
docker compose logs -f backend
docker compose logs -f frontend
docker compose logs -f tools
```

Update:

```bash
git switch main
git pull --ff-only origin main
docker compose -f docker-compose.yml -f docker-compose.prod.yml up --build -d
```

## First Admin Tasks After Deployment

1. Log in as `admin`
2. Change the initial password
3. Create engineer and reviewer accounts
4. Configure authorized networks before enabling subnet scans
5. Confirm backups and log retention behavior

## Health and Monitoring

Public health endpoints:

- `/api/health`
- `/api/health/metrics`

Authenticated status endpoints:

- `/api/health/tools/versions`
- `/api/health/system-status`

## Admin Password Reset

If you lose the admin password, update the database from the backend container:

```bash
docker exec edq-backend python -c "
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from app.security.auth import hash_password
async def reset():
    new_hash = hash_password('NEW_PASSWORD_HERE')
    engine = create_async_engine('sqlite+aiosqlite:///./data/edq.db')
    async with engine.begin() as conn:
        await conn.execute(text('UPDATE users SET password_hash = :h WHERE username = :u'), {'h': new_hash, 'u': 'admin'})
    print('Password reset OK')
asyncio.run(reset())
"
```

## Production Checklist

- `DEBUG=false`
- `COOKIE_SECURE=true`
- `CORS_ORIGINS` set to real domains only
- all required secrets rotated away from placeholders
- access restricted to trusted networks or VPN
- authorized scan networks configured in the app
- backups tested
- log collection in place

## Notes

- Interactive API docs should stay disabled in production.
- Do not expose the tools sidecar directly to the public internet.
- EDQ includes active scan tooling. Treat network access and authorized subnet configuration as a controlled operational boundary.
