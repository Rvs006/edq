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

No local update helper is required. The supported update path is the four commands above.

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
- If a test run stays in the `Paused Cable` state, the target IP did not answer both probes of the reachability AND-gate. Verify the cable and power, then retry.
