# Engineer Update Guide

This guide is for engineers who already have EDQ installed and just need the latest official version.

## Rule

Stay on the `main` branch only.

Do not do day-to-day work from old feature branches.

## Fastest Update

### Windows

Run:

```powershell
.\update.bat
```

### macOS / Linux

Run:

```bash
./update.sh
```

These scripts:

1. Fetch the latest code from GitHub
2. Switch to `main`
3. Pull the latest official release
4. Rebuild and restart the Docker containers

## Manual Update

If you prefer to run the commands yourself:

```bash
git switch main
git pull --ff-only origin main
docker compose up --build -d
```

## After Updating

Check that all services are healthy:

```bash
docker compose ps
```

Expected services:

- `backend`
- `frontend`
- `tools`

Then open:

- `http://localhost`

## Important

If you have local file changes in your EDQ folder, do not force an update over them.

Either:

- commit your own changes first, or
- ask the admin/release owner to help before updating

## Current Release Includes

- safer cable/disconnect handling for test runs
- automatic pause before tests start if the device is not reachable
- automatic pause/resume if the CAT6 link drops during a run
- improved network detection fallback in Docker/WSL-style environments
- updated release and deployment documentation
