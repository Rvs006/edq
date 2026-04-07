# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

EDQ (Electracom Device Qualifier) is a local-first qualification app for smart building IP devices. Three-service Docker stack (frontend, backend, tools sidecar) with an optional Electron desktop wrapper. Engineers discover devices on a network, run automated and manual security checks, and generate qualification reports.

## Architecture

**Three services** orchestrated via Docker Compose:
- **frontend** — React 19 SPA served by nginx. Proxies `/api/` and `/ws/` to the backend.
- **backend** — FastAPI (Python 3.12, async SQLAlchemy, SQLite WAL default). All routes dual-mounted at `/api/` and `/api/v1/`.
- **tools** — Network scanning sidecar (nmap, testssl.sh, hydra, nikto). Requires Linux capabilities (NET_ADMIN, NET_RAW). Backend calls it via HTTP at `TOOLS_SIDECAR_URL`.

**Electron** (`electron/`) is a desktop wrapper that manages Docker Compose lifecycle; it is not a dev launcher.

### Key backend patterns
- Route handlers stay thin; business logic lives in `server/backend/app/services/`.
- Auth: JWT access token (cookie `edq_session`, 1h) + refresh token (30d) with family revocation. CSRF via `X-CSRF-Token` header on mutating methods.
- Roles: admin, reviewer, engineer. Policy enforcement in route dependencies.
- Background jobs: APScheduler (scan_scheduler), periodic token cleanup, started in FastAPI lifespan.
- Database seeds idempotently on startup via `init_db.py`.

### Key frontend patterns
- State: TanStack React Query for server state, React context for auth/theme.
- API client (`frontend/src/lib/api.ts`): Axios with auto CSRF injection, 401→refresh→retry interceptor.
- Live updates: WebSocket hook (`useTestRunWebSocket`) for test run progress.
- Styling: Tailwind CSS with custom `surface`/`dark`/`brand`/`verdict` color tokens. Dark mode via class toggle.
- Components: Radix UI headless primitives, Lucide icons, Framer Motion.

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
