# EDQ Local Development

This guide covers local development outside the full Docker stack.

## What This Mode Supports

EDQ is still a Docker-first application for normal use.

This local-development path is intended for:

- frontend work with Vite on `http://localhost:5173`
- backend API work with Uvicorn on `http://localhost:8000`
- local frontend and backend tests

This mode is not a full replacement for Docker on Windows. The default scan tooling remains Docker-backed for normal development because the bundled tools sidecar depends on Linux packages and capabilities such as:

- `nmap` raw-socket capabilities
- `testssl.sh`
- `hydra`
- `nikto`
- other Linux-oriented network utilities installed in the tools container

If you need reliable Windows direct-Ethernet discovery, run the scanner agent on the Windows host and point the backend at it with `TOOLS_SIDECAR_URL`.

## Prerequisites

- Node.js 22 or newer for local development; the current Docker image line uses Node 24
- `pnpm` 10.x preferred for the frontend
- Python 3.12 or newer for the backend; the current Docker image line uses Python 3.13
- Git
- Docker Desktop if you want the default Docker-backed scan tooling available during local development
- For host scanner mode: Nmap on `PATH`, Python scanner dependencies from `tools/requirements.txt`, and any optional tools you intend to run locally

Windows notes:

- If `pnpm` is installed per-user but not on `PATH`, use `%APPDATA%\npm\pnpm.cmd` or add `%APPDATA%\npm` to your user `PATH`.
- The workspace expects the backend virtual environment at `server/backend/.venv`.

## Supported Config Rules

- The root `.env` file remains the source of truth.
- Do not create `server/backend/.env`.
- For local backend development with the Docker-backed scanner, keep `TOOLS_SIDECAR_URL=http://127.0.0.1:8001`.
- For local backend development with a Windows host scanner, keep `TOOLS_SIDECAR_URL=http://127.0.0.1:8001` and set `EDQ_SCANNER_MODE=host`.
- For Docker backend plus Windows host scanner, set `TOOLS_SIDECAR_URL=http://host.docker.internal:8002`, `EDQ_SCANNER_MODE=host`, and `EDQ_START_INTERNAL_TOOLS=false`.
- The default local database path is PostgreSQL on `127.0.0.1:55432`. Override `DATABASE_URL` only if you intentionally want a different database.
- Redis is optional locally. If you want shared-environment rate limiting behavior, start Docker with `--profile redis` and set `REDIS_URL=redis://127.0.0.1:6379/0`.

## Install Dependencies

### Frontend

Preferred:

```powershell
cd frontend
pnpm install --frozen-lockfile
```

Fallback if `pnpm` is unavailable:

```powershell
cd frontend
npm install
```

### Backend

If `python` is not on `PATH`, use your installed interpreter to create the virtual environment, then invoke the venv interpreter directly for package installation.

```powershell
cd server\backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

### Electron

Only needed if you are working on the desktop wrapper:

```powershell
cd electron
npm ci
```

## Run Locally

### Optional: keep PostgreSQL and the tools sidecar available via Docker

```powershell
docker compose up -d postgres backend
```

Because the `backend` container also publishes host port `8000`, either stop it before starting local Uvicorn or temporarily set `EDQ_BACKEND_PORT` in the root `.env` to a different host port such as `18000` before running that compose command.

### Optional: run the scanner agent on the Windows host

Use this for direct-Ethernet discovery where Docker Desktop networking can hide ARP, ICMP, or TCP reachability.

```powershell
cd tools
python -m pip install -r requirements.txt
$env:TOOLS_API_KEY = "<same value as root .env TOOLS_API_KEY>"
python server.py
```

Then point the backend at it:

```powershell
$env:TOOLS_SIDECAR_URL = "http://127.0.0.1:8001"
$env:EDQ_SCANNER_MODE = "host"
```

For the Docker backend to use the Windows host scanner instead of its internal sidecar, set these in the root `.env` before `docker compose up`:

```dotenv
TOOLS_SIDECAR_URL=http://host.docker.internal:8002
EDQ_SCANNER_MODE=host
EDQ_START_INTERNAL_TOOLS=false
```

Run the host scanner on `8002` for that Docker-backend path so it does not collide with the backend service's published internal tools port:

```powershell
cd tools
$env:TOOLS_API_KEY = "<same value as root .env TOOLS_API_KEY>"
$env:EDQ_SCANNER_PORT = "8002"
python server.py
```

### Start the backend locally

From `server\backend`:

```powershell
$env:TOOLS_SIDECAR_URL = "http://127.0.0.1:8001"
$env:EDQ_SCANNER_MODE = "host" # only when using the Windows host scanner
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Notes:

- `TOOLS_SIDECAR_URL=http://127.0.0.1:8001` is required for a local backend process when you want to reuse either the Docker-hosted scanner port or a host scanner on the same machine.
- Leave `EDQ_SCANNER_MODE` unset for the Docker-hosted scanner; set it to `host` for the Windows host scanner.
- The default `.env` now points local backend runs at PostgreSQL on `127.0.0.1:55432`, which is also exposed by `docker compose up -d postgres`.
- If you need an isolated scratch database, override `DATABASE_URL` explicitly before starting the backend.

### Start the frontend locally

From `frontend`:

```powershell
pnpm dev
```

Fallback:

```powershell
npm run dev
```

Then open `http://localhost:5173`.

The Vite dev server proxies `/api` requests to `http://localhost:8000`, so you do not need a separate frontend API URL for the standard local-dev path.

## Tests

Frontend:

```powershell
cd frontend
pnpm test
```

Backend:

```powershell
cd server\backend
.\.venv\Scripts\python.exe -m pytest tests -v
```

Docker-backed integration checks:

```powershell
.\scripts\verify-app.ps1
.\scripts\e2e-test.ps1
.\scripts\backend-test.ps1
```

## Limits And Gotchas

- Electron is not the local-dev launcher. The Electron app starts Docker services through `docker compose`.
- The supported full-stack path is still Docker Compose.
- If you skip `docker compose up -d postgres backend`, the local backend will lose the Docker-hosted Postgres and scanner dependencies unless you start PostgreSQL and a host scanner separately.
- Windows direct-Ethernet discovery should use host scanner mode so nmap, ping, TCP probes, ARP/neighbor lookup, and interface detection run outside Docker.
- If `python`, `py`, or `pip` are not on `PATH`, invoke the installed interpreter directly or update your shell environment first.
- If VS Code prompts for a Python interpreter, select `server/backend/.venv/Scripts/python.exe`.
