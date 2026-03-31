# EDQ — Next Session Context

## Current State
- **Branch:** `main` (PR #45 pending: test runs UX overhaul)
- **App:** Running at http://localhost via `docker compose up --build -d`
- **Login:** admin / `EdqhiCL6PbV07RSx6au!`
- **Frontend tests:** 50 passing (vitest)
- **Containers:** 3 services (backend, frontend, tools)

## What's Built

### Core
- 43 security tests (25 automated, 18 guided manual)
- Device discovery via nmap with active reverse DNS resolution
- Test engine with WebSocket live streaming
- Device fingerprinting and smart profiling
- Report generation (Excel, Word)

### Test Runs (PR #45)
- Grouped status filters (Active/Review/Done) with counts, pulse, tooltips
- Rich device info in table (name, IP, manufacturer, model, category)
- Confidence score (1-10) per test run
- Resume cancelled/failed test runs
- Duplicate detection warning in create modal

### Auth & Security
- TOTP 2FA, OIDC/SSO (Google, Microsoft, Keycloak)
- Per-user rate limiting, CSRF protection
- Role-based access (admin, reviewer, engineer)
- Full audit logging

### Infrastructure
- Docker Compose (backend, frontend nginx, tools sidecar)
- CI: GitHub Actions (lint, test, build, Docker, dep audit)
- Authorized networks, scan schedules

## Known Issues / Next Steps
- PDF report generation not yet implemented (Excel and Word work)
- Device enrichment still limited for some device types (hostname resolution added, but model/firmware guessing depends on nmap banner data)
- `gh` CLI not installed locally — install with `winget install GitHub.cli` for CI checks

## Utility Commands

```bash
# Reset admin password
docker exec edq-backend python -c "
from app.security.auth import hash_password
import sqlite3
h = hash_password('EdqhiCL6PbV07RSx6au!')
c = sqlite3.connect('/app/data/edq.db')
c.execute('UPDATE users SET password_hash=?, failed_login_attempts=0, locked_until=NULL WHERE username=?', (h, 'admin'))
c.commit(); print('OK')
"

# Run migrations
docker exec edq-backend alembic stamp head

# Check health
docker compose ps && curl -sf http://localhost:8000/api/health

# Rebuild
docker compose up --build -d

# Run frontend tests
cd frontend && npx vitest run
```
