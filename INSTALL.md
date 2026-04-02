# EDQ Local Engineer Install and Test Guide

This is the primary guide for engineers testing EDQ locally on `http://localhost`.

## Audience and Scope

Use this guide if you are:

- installing EDQ on your own laptop or workstation
- validating a new build before wider rollout
- updating an existing local install

Do not use this guide for internet-facing or shared production deployment. Use [DEPLOY.md](DEPLOY.md) for that.

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

1. Open `http://localhost`
2. Log in with:
   - username: `admin`
   - password: the value of `INITIAL_ADMIN_PASSWORD` in the root `.env`
3. Change the password after first login

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

1. Open `http://localhost`
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
docker compose logs -f tools
```

Update an existing install:

- Windows: `.\update.bat`
- macOS or Linux: `./update.sh`

Update-only guide: [ENGINEER_UPDATES.md](ENGINEER_UPDATES.md)

## Troubleshooting

### Port 80 already in use

Edit `docker-compose.yml` and map the frontend to another host port, for example `8080:80`, then open `http://localhost:8080`.

### Backend will not start

Check:

```bash
docker compose logs backend
```

Typical causes:

- required secrets in `.env` are still placeholders
- Docker did not finish building the image
- another local config file was created and caused confusion

### Login fails on localhost

Confirm:

- you are using the password from the root `.env`
- `COOKIE_SECURE=false` in the local `.env`
- you opened `http://localhost`, not an outdated bookmarked URL

### Tools sidecar unhealthy

Check:

```bash
docker compose logs tools
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
