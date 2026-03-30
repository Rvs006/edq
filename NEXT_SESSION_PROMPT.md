# EDQ — Next Session: Logo Fix, Live Terminal Output & Polish

## Current State
- **Branch:** `main` — clean working tree, all pushed
- **App:** Running at http://localhost via `docker compose up --build -d`
- **Login:** admin / `EdqhiCL6PbV07RSx6au!` (reset last session)
- **Tests:** 162 backend tests passing
- **Containers:** All 3 healthy (backend, frontend, tools)

## What Was Built (Previous Sessions)

### Production Hardening
- Tools sidecar auth bypass fixed (crash on empty key, hmac.compare_digest)
- HTTPS redirect middleware, Sentry SDK, Prometheus /metrics
- Startup validation, structured JSON audit logs, .dockerignore
- Complete production readiness checklist in DEPLOY.md

### Authentication
- TOTP 2FA (setup, verify, disable, QR code, login enforcement)
- OIDC/SSO (Google, Microsoft, Keycloak — auto-provision users)
- Per-user rate limiting, audit log retention policy

### Network Scan UX
- Authorized networks (admin CRUD, scan enforcement)
- Device cards with hostname/vendor, clickable + expandable
- Scan persists across page navigations (sessionStorage)

### Live Test Dashboard Per Device (latest — just merged)
- Backend `GET /api/network-scan/{id}/results` returns per-test breakdown: test_id, test_name, verdict, tool, duration_seconds, raw_output, device_category
- DeviceTestDashboard replaces old DeviceProgressCard — real-time checklist grouped by category (Network, TLS, SSH, Web, Manual)
- Status icons per test: spinner (running), check (pass), X (fail), clock (pending)
- Click any completed test to expand raw output inline
- Unselected tests shown greyed at bottom
- Device-aware relevance flagging: tests dimmed if irrelevant to device type, marked "Critical" if essential for device category

---

## Priority 1: Logo Icon Size Fix

**Goal:** Make the black "C" icon the same visual height as the "ELECTRACOM" wordmark — they should look balanced side-by-side. Consistent across landing page, login page, and in-app sidebar.

**Reference image was provided** (visual only — do NOT use any assets from it). Use only existing project assets.

**Current state:**
- `ElectracomLogo` component: `frontend/src/components/common/ElectracomLogo.tsx`
- Uses PNG: `/electracom-logo.png` (the wordmark with colored bars)
- Renders "Device Qualifier" subtitle below
- Three sizes: sm (28px), md (44px), lg (56px)

**Icon assets used alongside the logo:**
- `/frontend/public/icon.png` (light theme)
- `/frontend/public/icon-white.png` (dark theme)
- `/frontend/public/icon-blue.png`

**Where icon + logo appear together:**
- **DashboardLayout.tsx** sidebar header (line ~317): icon-white.png at 32px next to ElectracomLogo size="md" (44px)
- **LandingPage.tsx** header (line ~56): ElectracomLogo size="md"
- **LoginPage.tsx** (line ~118): ElectracomLogo size="lg"

**What to do:**
- Adjust the icon height to match the wordmark proportionally in each context
- The icon should feel like it belongs next to the text — same optical height
- Check all three pages (landing, login, dashboard sidebar) for consistency

---

## Priority 2: Live Terminal Output Per Device

**Goal:** Show actual tool output as it streams, not just a spinner.

**What to build:**
- "Show live output" toggle on each device card in DeviceTestDashboard
- Opens xterm.js terminal with real nmap/testssl/hydra stdout
- xterm.js already installed, WebSocket routes already exist

**Key files:**
- `server/backend/app/routes/websocket_routes.py`
- Check `package.json` for xterm.js version
- `server/backend/app/services/test_engine.py` — where tool output is captured

---

## Priority 3: Nice-to-haves (if time permits)
- Pause/skip a single test on a single device mid-scan
- Re-run a failed test without restarting entire scan
- Add engineer notes on a device during scanning
- Side-by-side comparison of two devices
- Export partial report while scan is still running

---

## Execution Order

1. Fix logo icon sizing across all pages (Priority 1)
2. Add xterm.js live terminal output toggle per device (Priority 2)
3. Test end-to-end with a real scan on 192.168.1.0/24
4. Nice-to-haves if time permits (Priority 3)

---

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

# Run tests
docker run --rm -v "$(pwd)/server/backend:/app" \
  -e DEBUG=true -e JWT_SECRET=test -e JWT_REFRESH_SECRET=test \
  -e SECRET_KEY=test -e TOOLS_API_KEY=test -e ALLOW_REGISTRATION=true \
  edq-backend sh -c "pip install -q pytest pytest-asyncio httpx && python -m pytest tests/ -v --tb=short"
```

## What NOT to Change
- Auth/security middleware — working, tested, production-hardened
- Docker compose architecture — 3 services, working correctly
- The 43 test definitions in `universal-tests.ts` / `test_library.py`
- The fingerprinter service — working correctly
- 2FA/OIDC routes — built, not yet tested on real IdP but code is solid
- DeviceTestDashboard component — just built, working correctly
- Device relevance mapping in NetworkScanPage.tsx — maps device categories to relevant tests
