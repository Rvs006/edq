# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

EDQ (Electracom Device Qualifier) is a local-first qualification app for smart building IP devices. The default deployment is a two-container Docker stack (frontend plus a combined backend+tools container) with optional Postgres and TLS overlays, plus an optional Electron desktop wrapper. Engineers discover devices on a network, run automated and manual security checks, and generate qualification reports.

## Architecture

**Default deployment uses two services** orchestrated via Docker Compose:
- **frontend** — React 19 SPA served by nginx. Proxies `/api/` and `/ws/` to the backend.
- **backend** — FastAPI (Python 3.12, async SQLAlchemy, SQLite WAL default). All routes under `/api/v1/`.
- **tools sidecar** — starts inside the backend container by default (gunicorn on `127.0.0.1:8001`). It still runs the scanning toolchain (nmap, testssl.sh, hydra, nikto) and requires Linux capabilities.

**Electron** (`electron/`) is a desktop wrapper that manages Docker Compose lifecycle; it is not a dev launcher.

**Docker Compose variants:**
- `docker-compose.yml` — default (SQLite).
- `docker-compose.postgres.yml` — PostgreSQL overlay (`docker compose -f docker-compose.yml -f docker-compose.postgres.yml up`).
- `docker-compose.tls.yml` — TLS via Caddy reverse proxy (`docker compose -f docker-compose.yml -f docker-compose.tls.yml up`). Uses `Caddyfile` at repo root.

### Key backend patterns
- Route handlers stay thin; business logic lives in `server/backend/app/services/`.
- Auth: JWT access token (cookie `edq_session`, 1h) + refresh token (30d) with family revocation. CSRF via `X-CSRF-Token` header on mutating methods. 2FA and OIDC/SSO supported.
- Roles: admin, reviewer, engineer. Policy enforcement in route dependencies.
- Background jobs: APScheduler (scan_scheduler), periodic token cleanup, started in FastAPI lifespan.
- Database seeds idempotently on startup via `init_db.py`.
- Route mounting: all routers prefixed `/api/v1/`. A `LegacyAPIRewriteMiddleware` transparently rewrites `/api/*` → `/api/v1/*` for backward compat.
- Migrations: Alembic (`server/backend/migrations/`). Run from `server/backend/`: `alembic upgrade head`, `alembic revision --autogenerate -m "description"`.
- `entrypoint.sh` starts both the tools sidecar (gunicorn on :8001) and the backend (uvicorn on :8000) in a single container for simplified deployment.
- Services include: CVE auto-correlation (`cve_correlator.py`), device fingerprinting, Nessus import parsing, report generation, scan scheduling.

### Key frontend patterns
- State: TanStack React Query for server state, React context for auth/theme.
- API client (`frontend/src/lib/api.ts`): Axios with auto CSRF injection, 401→refresh→retry interceptor.
- Live updates: WebSocket hook (`useTestRunWebSocket`) for test run progress.
- Styling: Tailwind CSS with custom `surface`/`dark`/`brand`/`verdict` color tokens. Dark mode via class toggle.
- Components: Radix UI headless primitives, Lucide icons, Framer Motion.
- Component directories: `devices/` (TopologyMap, TrendChart), `tour/` (GuidedTour onboarding), `common/` (ErrorBoundary), `layout/`, `profiles/`, `testing/`.
- Pages include: Projects, Devices (list/detail/compare), TestRuns, Templates, Reports, Admin, AuditLog, NetworkScan, TestPlans, ScanSchedules, Agents, DeviceProfiles, AuthorizedNetworks, ReviewQueue.

## Common Commands

### Full stack (Docker)
```bash
docker compose up --build -d          # Start all services
docker compose down                   # Stop all services
docker compose logs -f backend        # Tail backend logs
```

### Frontend development
```bash
cd frontend
pnpm install --frozen-lockfile        # Install deps (prefer pnpm 10.x)
pnpm dev                              # Vite dev server on :5173, proxies /api to :8000
pnpm test                             # Vitest (run mode)
pnpm test:watch                       # Vitest (watch mode)
pnpm test:coverage                    # Vitest with coverage
pnpm build                            # Production build to dist/
```

### Backend development
```bash
cd server/backend
python -m venv .venv                  # Create venv (Python 3.12)
.venv/Scripts/python.exe -m pip install -r requirements-dev.txt   # Windows
source .venv/bin/activate && pip install -r requirements-dev.txt  # Linux/Mac

# Run locally (override TOOLS_SIDECAR_URL for non-Docker):
TOOLS_SIDECAR_URL=http://localhost:8001 \
  python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# Tests
pytest tests -v                       # Full suite
pytest tests/test_auth.py -v          # Single file
pytest tests -k "test_login" -v       # Single test by name
```

### Integration / smoke tests
```bash
./scripts/verify-app.sh               # Smoke test (or .ps1 on Windows)
./scripts/e2e-test.sh                 # API regression (or .ps1)
./scripts/backend-test.sh             # Pytest in Docker (or .ps1)
```

### Testing notes
- Backend tests use pytest-asyncio with in-memory SQLite. Fixtures in `server/backend/tests/conftest.py`.
- Additional E2E-style suites live in root `tests/` and are intended to run against a live app instance using `tests/pytest.ini`; they are not a substitute for the backend unit/integration suite in `server/backend/tests/`.
- Security-specific tests in `server/backend/tests/security/` cover auth, headers, injection, and rate limiting.
- Frontend tests use Vitest. Setup in `frontend/src/test/setup.ts`. Test files co-located in `frontend/src/test/`.
- No linting/formatting tools are configured (no ESLint, Prettier, flake8, or ruff). CI runs tests only.

## Environment

- Root `.env` is the single source of truth for all config. Do NOT create `server/backend/.env`.
- `.env.example` documents every variable. Key secrets: `JWT_SECRET`, `JWT_REFRESH_SECRET`, `SECRET_KEY`, `TOOLS_API_KEY`.
- `COOKIE_SECURE=false` for local HTTP dev, `true` for production HTTPS.
- Default database: `sqlite+aiosqlite:///./data/edq.db`. PostgreSQL supported via `DATABASE_URL`.

## Code Standards

- Backend: typed Pydantic request/response schemas, async SQLAlchemy sessions, business logic in `services/`.
- Frontend: functional components, data fetching via React Query, preserve existing UI language (Radix + Tailwind + verdict colors).
- Path alias: `@/` maps to `frontend/src/` in imports.

## Documentation

Operational docs live at repo root: `INSTALL.md`, `LOCAL_DEVELOPMENT.md`, `DEPLOY.md`, `SECURITY.md`, `ENGINEER_UPDATES.md`. Files in `docs/` are historical specs for reference only.
