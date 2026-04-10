# EDQ Engineer Update Guide

Use this guide only if EDQ is already installed and you just need the latest official build.

## Rules

- Stay on the `main` branch
- Do not update over uncommitted local work
- Keep using the existing root `.env`

## Fastest Update

Windows:

```powershell
.\update.bat
```

macOS or Linux:

```bash
./update.sh
```

These scripts:

1. fetch the latest code from GitHub
2. switch to `main`
3. pull the latest official changes
4. rebuild and restart the containers

## After Updating

Check container status:

```bash
docker compose ps
```

Run the smoke test:

```bash
./scripts/verify-app.sh
```

Windows PowerShell:

```powershell
.\scripts\verify-app.ps1
```

Then open `http://localhost:3000`.

## If Update Fails

- If Git reports local changes, stop and clean up your work before updating.
- If Docker rebuild fails, inspect `docker compose logs` and retry.
- If login fails after update, confirm the root `.env` still contains the correct `INITIAL_ADMIN_PASSWORD`.
