# EDQ Production Deployment Guide

This guide is for shared or production-style deployments. It is not the local engineer setup guide.

For local testing on a single laptop, use [INSTALL.md](INSTALL.md).

For the current readiness rating and go/no-go checklist, read [PRODUCTION_READINESS.md](PRODUCTION_READINESS.md) before treating EDQ as production software.

For release gates, backup restore drills, monitoring, and scanner-governance checks, use [OPERATIONS_RUNBOOK.md](OPERATIONS_RUNBOOK.md).

## Deployment Model

EDQ runs as three containers:

- `frontend`: nginx and the built frontend
- `backend`: FastAPI application plus the co-located tools sidecar
- `postgres`: primary application database

Built-in production HTTPS support is provided through `docker-compose.prod.yml`.
An optional alternative TLS overlay is also available through `docker-compose.tls.yml` if you prefer Caddy instead of the built-in nginx + certbot path.

Current production posture:

- supported deployment is a single Docker Compose host
- access should stay private-network or VPN-only
- high availability, automated restore drills, and centralized observability are deployment-owner responsibilities
- active scanning must be limited through authorized networks and operational process.

Tip: Set `ENVIRONMENT=cloud` in `.env` for production deployments — this auto-derives `COOKIE_SECURE=true`, `COOKIE_SAMESITE=lax`, and Postgres defaults.

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
   - `POSTGRES_PASSWORD`
3. Set production-safe values for:
   - `COOKIE_SECURE=true`
   - `DEBUG=false`
   - `CORS_ORIGINS` to your real domain(s)
   - `SENTRY_DSN`, `SENTRY_ENVIRONMENT`, and `SENTRY_RELEASE` if you want incident telemetry
   - `VITE_SENTRY_DSN`, `VITE_SENTRY_ENVIRONMENT`, `VITE_SENTRY_RELEASE`, and optionally `VITE_SOURCEMAP=true` if you want browser-side Sentry reporting with hidden source maps
4. Do not rely on placeholder values from `.env.example`

## Start Without HTTPS

Only use this on a trusted private network.

```bash
docker compose up --build -d
```

Health endpoint:

```bash
curl http://localhost:3000/api/v1/health
```

## Start With HTTPS

This guide uses the built-in production HTTPS path: `docker-compose.prod.yml` with nginx + certbot.

1. Set `DOMAIN` in the root `.env`
2. Set `LETSENCRYPT_EMAIL` in the root `.env`
3. Set `EDQ_USE_BUILTIN_TLS=true` in the root `.env`
4. Start with the production override
5. Issue the certificate
6. Restart the frontend so nginx switches from HTTP bootstrap mode to HTTPS

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

```bash
DOMAIN=edq.example.com LETSENCRYPT_EMAIL=ops@example.com \
docker compose -f docker-compose.yml -f docker-compose.prod.yml run --rm certbot \
  certonly --webroot -w /var/www/certbot -d "$DOMAIN" \
  --agree-tos -m "$LETSENCRYPT_EMAIL" --non-interactive --keep-until-expiring
```

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml restart frontend
```

The production override:

- binds ports `80` and `443`
- removes the local-only `:3000` frontend publish
- starts in HTTP bootstrap mode until certificates exist, then enables nginx TLS config
- sets `COOKIE_SECURE=true` for the backend

During the bootstrap phase, port `80` is used for ACME validation and health checks. Browser login should be treated as unavailable until certificates are issued and the frontend has been restarted onto HTTPS.

## Optional Caddy TLS Overlay

If you prefer Caddy-managed TLS instead of the built-in nginx + certbot path, use:

```bash
docker compose -f docker-compose.yml -f docker-compose.tls.yml up -d
```

That optional overlay uses the repo-root `Caddyfile`. Keep one TLS approach per deployment; do not combine `docker-compose.prod.yml` and `docker-compose.tls.yml`.

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
docker compose logs -f postgres
```

Update:

```bash
git switch main
git pull --ff-only origin main
docker compose -f docker-compose.yml -f docker-compose.prod.yml up --build -d
```

Certificate renewal:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml run --rm certbot renew
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec -T frontend nginx -s reload
```

Backup:

```bash
./scripts/backup.sh ./backups
```

Restore drills should be performed on a separate host or disposable environment first. For PostgreSQL restore, use:

```bash
EDQ_RESTORE_CONFIRM=restore ./scripts/restore-postgres.sh ./backups/edq_YYYYMMDD_HHMMSS.sql
```

## First Admin Tasks After Deployment

1. Log in as `admin`
2. Change the initial password
3. Create engineer and reviewer accounts
4. Configure authorized networks before enabling subnet scans
5. Confirm backups and log retention behavior

## Health and Monitoring

Public health endpoints:

- `/api/v1/health`
- `/api/v1/health/metrics`

Authenticated status endpoints:

- `/api/v1/health/tools/versions`
- `/api/v1/health/system-status`

Legacy `/api/...` paths still rewrite for backward compatibility, but `/api/v1/...` is the canonical path.

Operational telemetry:

- backend logs are JSON by default when `LOG_JSON=true`
- backend responses include `X-Request-ID` for correlation
- optional Sentry forwarding supports backend exceptions and frontend beaconed errors
- frontend builds read `VITE_*` values from the repo-root `.env` during local development and from Docker build args when you override the frontend image build

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
    engine = create_async_engine('postgresql+asyncpg://edq:YOUR_POSTGRES_PASSWORD@postgres:5432/edq')
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
- PostgreSQL backups tested with `scripts/backup.sh`
- Sentry configured if you need incident alerting and stack traces
- access restricted to trusted networks or VPN
- authorized scan networks configured in the app
- backups tested
- log collection in place
- dependency, code, and secret scanning enabled in GitHub or an equivalent platform
- restore tested from a real backup before a wider rollout
- pilot completed against representative devices and networks
- release gate completed from [OPERATIONS_RUNBOOK.md](OPERATIONS_RUNBOOK.md)

## Notes

- Interactive API docs should stay disabled in production.
- Do not expose the tools sidecar directly to the public internet.
- EDQ includes active scan tooling. Treat network access and authorized subnet configuration as a controlled operational boundary.
