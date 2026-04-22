# AGENTS.md

This file is the canonical guide for AI coding agents working in this repository.

All agent-specific compatibility files, prompts, or onboarding docs should point here instead of redefining separate rules.

## Project Overview

EDQ (Electracom Device Qualifier) is a local-first qualification app for smart building IP devices. The default deployment is a three-service Docker Compose stack (frontend, backend, and PostgreSQL) with optional TLS overlays, optional Redis for shared-environment support, and an optional Electron desktop wrapper.

Engineers use EDQ to discover devices on a network, run automated and manual security checks, review outcomes, and generate qualification reports.

## Architecture

### Default deployment

- `frontend` - React 19 SPA built with Vite and served by nginx.
- `backend` - FastAPI on Python 3.13 with async SQLAlchemy and PostgreSQL integration.
- `postgres` - PostgreSQL 17 primary database.
- `tools sidecar` - runs inside the backend container by default and hosts the scanning toolchain on `127.0.0.1:8001`.

### Important architectural rules

- All backend API routes live under `/api/v1/`.
- Route handlers should stay thin; business logic belongs in `server/backend/app/services/`.
- `electron/` is a desktop wrapper that manages Docker Compose lifecycle. It is not the development launcher.
- Alembic migrations live in `server/backend/migrations/`.
- The backend container entrypoint starts both the tools sidecar and the FastAPI app for the standard deployment path.

### Frontend patterns

- React 19 + Vite + Tailwind + TanStack Query + Radix UI.
- Axios API client in `frontend/src/lib/api.ts` handles CSRF injection and refresh-on-401 retry flow.
- Live test progress uses the WebSocket hook path already established in the frontend.
- Preserve the existing UI language instead of introducing a new design system.

### Backend patterns

- FastAPI + async SQLAlchemy + PostgreSQL.
- Use typed request and response schemas.
- Auth uses JWT access tokens, refresh-token rotation, CSRF protection, and role-based policy checks.
- Background jobs run through APScheduler in the FastAPI lifespan.
- Database initialization and seed behavior must stay idempotent on startup.

## Environment And Configuration

- The repo-root `.env` is the single source of truth for configuration.
- Do not create `server/backend/.env`.
- `.env.example` documents the expected variables.
- Set `ENVIRONMENT` to `local`, `docker`, or `cloud` so database, cookie, and CORS defaults resolve correctly.

## Development Commands

### Full stack

```bash
docker compose up --build -d
docker compose down
docker compose logs -f backend
```

### Frontend

```bash
cd frontend
pnpm install --frozen-lockfile
pnpm dev
pnpm test
pnpm test:watch
pnpm test:coverage
pnpm build
```

### Backend

```bash
cd server/backend
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements-dev.txt
```

```bash
cd server/backend
source .venv/bin/activate && pip install -r requirements-dev.txt
```

```bash
cd server/backend
pytest tests -v
pytest tests/test_auth.py -v
pytest tests -k "test_login" -v
```

For local backend runs outside Docker, point `TOOLS_SIDECAR_URL` at the tool service before starting `uvicorn`.

## Testing

- Backend tests use `pytest`.
- Frontend tests use `Vitest`.
- No linter or formatter is configured in this repository.
- Backend fixtures live in `server/backend/tests/conftest.py`.
- Frontend test setup lives in `frontend/src/test/setup.ts`.

## Documentation Map

| File | Audience | Purpose |
| --- | --- | --- |
| `README.md` | Everyone | Orientation and quickstart |
| `INSTALL.md` | New engineers | First-time Docker stack install |
| `LOCAL_DEVELOPMENT.md` | Contributors | Local frontend and backend dev loop |
| `DEPLOY.md` | Ops | Production deploy, TLS, backup |
| `ENGINEER_UPDATES.md` | Existing engineers | Pull latest `main`, rebuild, verify |
| `SECURITY.md` | Everyone | Security model and reporting |
| `SECURITY_TOOLING.md` | Ops | Scanner and dependency audit tooling |
| `CONTRIBUTING.md` | Contributors | Branch, commit, and PR flow |
| `CHANGELOG.md` | Everyone | Curated release history |
| `REDIS.md` | Ops | Optional Redis profile guidance |
| `AGENTS.md` | AI agents | Canonical repository guidance for coding agents |
| `CLAUDE.md` | Claude users | Compatibility shim that points to `AGENTS.md` |

Historical specs in `docs/` are archive material and should not be treated as the current operational guide.

## Code Review Graph

This repository maintains a `code-review-graph` knowledge graph.

Use the available `code-review-graph` MCP tools before falling back to plain-text search or ad hoc file reads when you are:

- exploring unfamiliar parts of the codebase
- tracing callers, callees, imports, or tests
- checking architecture or community boundaries
- estimating the impact radius of a change

Use graph-native tools such as `query_graph`, `list_communities`, `get_architecture_overview`, `list_graph_stats`, and related `code-review-graph` tools whenever they cover the task. Fall back to `rg`, direct file reads, or broader scans only when the graph does not provide the needed context.

## Working Norms For Agents

- Prefer focused documentation and code changes. Do not rewrite product or runtime code for documentation-only tasks unless needed for consistency.
- Preserve the existing stack assumptions: Docker Compose deployment, FastAPI backend under `/api/v1/`, React frontend, and root `.env` configuration.
- Keep new instructions tool-agnostic unless a tool-specific compatibility file requires a minimal pointer.
- When a tool-specific file is required by an external agent, make that file a shim to this document instead of creating a second source of truth.
