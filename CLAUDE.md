# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

EDQ (Electracom Device Qualifier) is a local-first qualification app for smart building IP devices. The default deployment is a three-container Docker stack (frontend, backend+tools, and PostgreSQL) with optional TLS overlays, plus an optional Electron desktop wrapper. Engineers discover devices on a network, run automated and manual security checks, and generate qualification reports.

## Architecture

**Default deployment uses three services** orchestrated via Docker Compose:
- **frontend** — React 19 SPA built by Vite (node:24-alpine) and served by nginx:alpine. Proxies `/api/` and `/ws/` to the backend.
- **backend** — FastAPI on python:3.13-slim (async SQLAlchemy, PostgreSQL). All routes under `/api/v1/`.
- **postgres** — PostgreSQL 17 (postgres:17-alpine) primary database.
- **tools sidecar** — starts inside the backend container by default (gunicorn on `127.0.0.1:8001`). Runs the scanning toolchain (nmap, testssl.sh, hydra, nikto, ssh-audit, snmpwalk) and requires Linux capabilities.

**Electron** (`electron/`) is a desktop wrapper that manages Docker Compose lifecycle; it is not a dev launcher.

**Docker Compose variants:**
- `docker-compose.yml` — default (PostgreSQL + backend + frontend).
- `docker-compose.prod.yml` — built-in nginx TLS bootstrap with certbot for the documented production flow.
- `docker-compose.tls.yml` — optional Caddy reverse-proxy TLS overlay (`docker compose -f docker-compose.yml -f docker-compose.tls.yml up`). Uses `Caddyfile` at repo root.

### Key backend patterns
- Route handlers stay thin; business logic lives in `server/backend/app/services/`.
- Auth: JWT access token (cookie `edq_session`, 1h) + refresh token (30d) with family revocation. CSRF via `X-CSRF-Token` header on mutating methods. 2FA and OIDC/SSO supported. Set `ENVIRONMENT` for consistent auth behavior across deployments.
- Roles: admin, reviewer, engineer. Policy enforcement in route dependencies.
- MAC addresses: best-effort data. nmap only reports MAC on the same L2 segment; in Docker, MAC is typically `null` due to NAT boundary. The `nmap_parser.parse_host_discovery()` handles this gracefully.
- Reachability gate (discovery + device create): uses an **AND-gate** in `connectivity_probe.probe_device_connectivity()` — both a fresh TCP/ICMP probe **and** nmap's ARP-bypass ping must agree the host is up before a single-IP scan proceeds. Prevents stale-ARP "ghost" results on unplugged devices. Same probe feeds manual device creation (`reachability_verified` in the create response) and batch scans (`skipped_unreachable` in the response).
- Rate limiting on discovery/scan endpoints uses two buckets per client: `DISCOVERY_RATE_LIMIT_PER_MINUTE` (per target scope) and `DISCOVERY_GLOBAL_RATE_LIMIT_PER_MINUTE` (per client, across all targets) to prevent sweep-style abuse.
- Background jobs: APScheduler (scan_scheduler), periodic token cleanup, started in FastAPI lifespan.
- Database seeds idempotently on startup via `init_db.py`.
- Route mounting: all routers prefixed `/api/v1/`. A `LegacyAPIRewriteMiddleware` transparently rewrites `/api/*` → `/api/v1/*` for backward compat.
- Migrations: Alembic (`server/backend/migrations/`). Run from `server/backend/`: `alembic upgrade head`, `alembic revision --autogenerate -m "description"`.
- `entrypoint.sh` starts both the tools sidecar (gunicorn on :8001) and the backend (uvicorn on :8000) in a single container for simplified deployment.
- Services include: CVE auto-correlation (`cve_correlator.py`), device fingerprinting, Nessus import parsing, report generation, scan scheduling, connectivity probing.

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
python -m venv .venv                  # Create venv (Python 3.13)
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
- Set `ENVIRONMENT` to `local` (default), `docker`, or `cloud` to auto-derive DB, cookie, and CORS defaults.
- `COOKIE_SECURE=false` for local HTTP dev, `true` for production HTTPS (auto-set when `ENVIRONMENT=cloud`).
- Default database: PostgreSQL via `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`.

## Code Standards

- Backend: typed Pydantic request/response schemas, async SQLAlchemy sessions, business logic in `services/`.
- Frontend: functional components, data fetching via React Query, preserve existing UI language (Radix + Tailwind + verdict colors).
- Path alias: `@/` maps to `frontend/src/` in imports.

## Documentation

Operational docs live at repo root:

| File | Audience | Purpose |
|---|---|---|
| `README.md` | Everyone | Orientation + quickstart |
| `INSTALL.md` | New engineers | First-time install of the Docker stack |
| `LOCAL_DEVELOPMENT.md` | Contributors | Non-Docker dev loop (vite + uvicorn) |
| `DEPLOY.md` | Ops | Production deploy, TLS, backup |
| `ENGINEER_UPDATES.md` | Engineers with EDQ already installed | Pull latest `main`, rebuild |
| `SECURITY.md` | Everyone | Threat model, reporting vulns |
| `SECURITY_TOOLING.md` | Ops | Scanner / dependency audit tooling |
| `CONTRIBUTING.md` | Contributors | Branch, commit, PR flow |
| `CHANGELOG.md` | Everyone | Release history |
| `REDIS.md` | Ops | Optional Redis for shared rate-limit state |
| `AGENTS.md` | AI agents (all) | Pointer to `CLAUDE.md` |

Files in `docs/` are historical specs for reference only.

<!-- code-review-graph MCP tools -->
## MCP Tools: code-review-graph

**IMPORTANT: This project has a knowledge graph. ALWAYS use the
code-review-graph MCP tools BEFORE using Grep/Glob/Read to explore
the codebase.** The graph is faster, cheaper (fewer tokens), and gives
you structural context (callers, dependents, test coverage) that file
scanning cannot.

### When to use graph tools FIRST

- **Exploring code**: `semantic_search_nodes` or `query_graph` instead of Grep
- **Understanding impact**: `get_impact_radius` instead of manually tracing imports
- **Code review**: `detect_changes` + `get_review_context` instead of reading entire files
- **Finding relationships**: `query_graph` with callers_of/callees_of/imports_of/tests_for
- **Architecture questions**: `get_architecture_overview` + `list_communities`

Fall back to Grep/Glob/Read **only** when the graph doesn't cover what you need.

### Key Tools

| Tool | Use when |
|------|----------|
| `detect_changes` | Reviewing code changes — gives risk-scored analysis |
| `get_review_context` | Need source snippets for review — token-efficient |
| `get_impact_radius` | Understanding blast radius of a change |
| `get_affected_flows` | Finding which execution paths are impacted |
| `query_graph` | Tracing callers, callees, imports, tests, dependencies |
| `semantic_search_nodes` | Finding functions/classes by name or keyword |
| `get_architecture_overview` | Understanding high-level codebase structure |
| `refactor_tool` | Planning renames, finding dead code |

### Workflow

1. The graph auto-updates on file changes (via hooks).
2. Use `detect_changes` for code review.
3. Use `get_affected_flows` to understand impact.
4. Use `query_graph` pattern="tests_for" to check coverage.
