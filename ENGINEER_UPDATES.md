# EDQ Engineer Update Guide

Use this guide only if EDQ is already installed and you just need the latest official build.

## Rules

- Stay on the `main` branch
- Do not update over uncommitted local work
- Keep using the existing root `.env`

## Fastest Update

From the repo root, run these four commands in order:

Windows PowerShell:

```powershell
git fetch origin
git switch main
git pull --ff-only origin main
docker compose up --build -d
```

macOS or Linux:

```bash
git fetch origin
git switch main
git pull --ff-only origin main
docker compose up --build -d
```

What each step does:

1. `git fetch origin` — downloads the latest refs without touching your working tree
2. `git switch main` — moves you to the release branch (fails if you have uncommitted changes; resolve first)
3. `git pull --ff-only origin main` — fast-forwards your `main` to the latest official commit; aborts if you have diverged
4. `docker compose up --build -d` — rebuilds any changed images and restarts containers in the background

No local scripts are required. A previous `update.bat`/`update.sh` helper has been removed; the four commands above are the supported path.

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

If this update is part of a pilot or release validation, also run:

```powershell
.\scripts\e2e-test.ps1
.\scripts\backend-test.ps1
docker scout cves edq-backend:latest --only-severity critical,high
docker scout cves edq-frontend:latest --only-severity critical,high
.\scripts\configure-production.ps1 -Domain <real-hostname> -BaseUrl https://<real-hostname> -AuthorizedCidrs <approved-cidr> -DryRun
.\scripts\collect-production-evidence.ps1 -PilotDeviceIps <pilot-device-ip> -SkipBackupRestore
. .\reports\production\production-gate-env-YYYYMMDD_HHMMSS.ps1
.\scripts\production-gate.ps1 -Mode pilot -DeploymentConfig prod-compose
```

Pass `-BaseUrl` to `collect-production-evidence.ps1` if the pilot stack is being checked through a different URL than `EDQ_PUBLIC_URL`.
Use production mode only against the final HTTPS deployment URL; local engineer validation should stay in pilot mode.

## If Update Fails

- If Git reports local changes, stop and clean up your work before updating.
- If Docker rebuild fails, inspect `docker compose logs` and retry.
- If login fails after update, confirm the root `.env` still contains the correct `INITIAL_ADMIN_PASSWORD`.
- If a test run stays in the `Paused Cable` state, the target IP did not answer both probes of the reachability AND-gate. Verify the cable and power, then retry.
