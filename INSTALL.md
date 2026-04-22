# EDQ Local Engineer Install and Test Guide

This is the primary guide for engineers testing EDQ locally on `http://localhost:3000`.

## Audience and Scope

Use this guide if you are:

- installing EDQ on your own laptop or workstation
- validating a new build before wider rollout
- updating an existing local install

Do not use this guide for internet-facing or shared production deployment. Use [DEPLOY.md](DEPLOY.md) for that.

If you are doing frontend or backend development outside the full Docker stack, use [LOCAL_DEVELOPMENT.md](LOCAL_DEVELOPMENT.md). That path supports running Vite and Uvicorn locally, but the scan tooling remains Docker-backed on Windows.

## Prerequisites

- Docker Desktop
- Git
- At least 4 GB of RAM available to Docker

Optional but useful:

- `bash` for shell scripts on macOS, Linux, or Git Bash on Windows
- `curl` for manual API checks

## Supported Local Config

- Use the root `.env` file only.
- Do not create or rely on `server/backend/.env`.
- `setup.sh` and `setup.bat` create the root `.env` for you if it does not exist.
- The frontend also reads repo-root `VITE_*` variables through `frontend/vite.config.ts`, so `VITE_CLIENT_ERROR_ENDPOINT` and `VITE_SENTRY_ENABLED` can live alongside the other deployment variables in the root `.env`.

## First-Time Setup

### Recommended path

macOS or Linux:

```bash
git clone https://github.com/Rvs006/edq.git
cd edq
./setup.sh
```

Windows:

```powershell
git clone https://github.com/Rvs006/edq.git
cd edq
.\setup.bat
```

What setup does:

- creates the root `.env` from `.env.example` if needed
- fills required secrets if they are missing or still set to placeholders
- generates an initial admin password if needed
- starts the Docker services

### Manual path

If you need to inspect the config before first start:

```bash
cp .env.example .env
```

Then edit the root `.env` and set the required values before running:

```bash
docker compose up --build -d
```

## First Login

1. Open `http://localhost:3000`
2. Log in with:
   - username: `admin`
   - password: the value of `INITIAL_ADMIN_PASSWORD` in the root `.env`
3. Change the password after first login

After you change the admin password, pass the current password to the smoke scripts with `EDQ_ADMIN_PASS`, `-AdminPass`, or the matching PowerShell parameter. The root `.env` keeps the initial seed password and is no longer correct after rotation.

If `setup.sh` or `setup.bat` generated the initial admin password for you, the script prints it once and also saves it in the root `.env`.

## Baseline Validation

Check the containers:

```bash
docker compose ps
```

Run the supported smoke test:

```bash
./scripts/verify-app.sh
```

Windows PowerShell:

```powershell
.\scripts\verify-app.ps1
```

Manual checks:

1. Open `http://localhost:3000`
2. Log in as `admin`
3. Confirm the dashboard loads
4. Add a device
5. Create a test run
6. Open a completed run and generate a report

Optional API regression script:

```bash
./scripts/e2e-test.sh
```

Windows PowerShell:

```powershell
.\scripts\e2e-test.ps1
```

Backend pytest suite through Docker:

macOS or Linux:

```bash
./scripts/backend-test.sh
```

Windows PowerShell:

```powershell
.\scripts\backend-test.ps1
```

## Network Scan Setup

Network scans are intentionally blocked until an admin authorizes at least one subnet.

Before testing subnet discovery:

1. Log in as `admin`
2. Open `Admin -> Authorized Networks`
3. Add the CIDR ranges your team is allowed to scan, for example `192.168.1.0/24`

If you skip this step, subnet discovery requests will be rejected.

## Daily Operations

Start EDQ:

```bash
docker compose up -d
```

Stop EDQ:

```bash
docker compose down
```

View logs:

```bash
docker compose logs -f
docker compose logs -f backend
docker compose logs -f frontend
```

Update an existing install (all platforms):

```bash
git fetch origin
git switch main
git pull --ff-only origin main
docker compose up --build -d
```

For the supported update flow plus post-update checks, use [ENGINEER_UPDATES.md](ENGINEER_UPDATES.md).

## Troubleshooting

### Port 3000 already in use

Change `EDQ_PUBLIC_PORT` in the root `.env`, then restart the stack.

For example:

```bash
EDQ_PUBLIC_PORT=8080
```

Then open `http://localhost:8080`.

### Backend will not start

Check:

```bash
docker compose logs backend
```

Typical causes:

- required secrets in `.env` are still placeholders
- Docker did not finish building the image
- another local config file was created and caused confusion

### "Service Issue" banner / Security Tools: Unavailable

Symptom: the app loads, login works, Frontend/Backend/Database all report healthy, but the **Security Tools** row in the status panel shows **Unavailable** with the message *"Security tools are unreachable. Automated tests will not run."*

Cause: the tools sidecar (nmap, testssl.sh, hydra, nikto, ssh-audit, snmpwalk) lives inside the backend container. The main FastAPI process is up, but the sidecar process either:

- died at startup (missing tool / bad Perl module / permission issue), or
- is running with a different `TOOLS_API_KEY` than the backend expects (env-drift), or
- started from a **cached Docker image layer** from a previously failed install.

Fix — clean rebuild with `--no-cache`:

```bash
docker compose down
docker compose build --no-cache backend
docker compose up -d
```

The `--no-cache` flag is the important one — it forces Docker to re-apt-install `procps`, `libjson-perl`, etc. that the sidecar needs. `setup.bat` and `setup.sh` now do this automatically when they detect an existing `edq-backend` image, but you can always invoke it manually.

Verification after rebuild:

```bash
docker exec edq-backend curl -sf http://localhost:8001/health
```

Expected: `{"status":"healthy","tools":{"hydra":true,"nikto":true,"nmap":true,"snmpwalk":true,"ssh_audit":true,"testssl":true}}`

If any tool reports `false`, the rebuild did not complete — try again with `docker compose down -v` first (this wipes the database; only do it if you have no data to preserve).

### Login fails on localhost

Confirm:

- you are using the password from the root `.env`
- `COOKIE_SECURE=false` in the local `.env`
- you opened `http://localhost:3000`, not an outdated bookmarked URL

### Tools sidecar unhealthy

The tools sidecar now runs inside the backend container.

Check:

```bash
docker compose logs backend
```

### Blank or broken frontend

Check:

```bash
docker compose logs frontend
```

## API Docs and Debug Mode

Interactive backend API docs are disabled by default.

If you explicitly set `DEBUG=true` in the root `.env`, the backend exposes:

- `http://localhost:8000/docs`
- `http://localhost:8000/redoc`

That is for debugging only and is not part of the normal engineer validation flow.
