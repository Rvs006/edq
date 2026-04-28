# EDQ Operations Runbook

This runbook covers the operational evidence needed before EDQ can be treated as production-ready rather than pilot-ready.

## Release Gate

Before a release candidate goes to engineers:

1. Confirm `main` is clean and current.
2. Confirm GitHub CI is green.
3. Confirm CodeQL has no open critical or high alerts.
4. Confirm container scanning has no critical or high findings.
5. Confirm branch protection requires the named CI jobs and `container-scan`.
6. Run the local smoke test against the Docker stack.
7. Run the API regression script.
8. Run the backend regression suite.
9. Confirm authorized scan networks are configured narrowly.
10. Confirm backups are enabled and the latest backup restored successfully in a drill.

Commands:

```powershell
git switch main
git pull --ff-only origin main
docker compose up --build -d
.\scripts\verify-app.ps1
.\scripts\e2e-test.ps1
.\scripts\backend-test.ps1
docker scout cves edq-backend:latest --only-severity critical,high
```

## Backup Drill

Run a backup:

```bash
./scripts/backup.sh ./backups
```

Restore drills should be done on a separate test host or disposable Docker volume first. Do not test restore against a live production database unless you intend to replace it.

Restore a PostgreSQL dump:

```bash
EDQ_RESTORE_CONFIRM=restore ./scripts/restore-postgres.sh ./backups/edq_YYYYMMDD_HHMMSS.sql
```

After restore:

```bash
docker compose ps
./scripts/verify-app.sh
./scripts/e2e-test.sh
```

Record:

- backup filename
- source commit
- restore host
- restore start and finish time
- validation commands and results
- operator name

## Monitoring Gate

Before shared production use:

- configure Sentry or equivalent exception monitoring
- collect backend, frontend, and PostgreSQL logs centrally
- alert when `/api/v1/health` is not healthy
- alert when tools versions cannot be fetched
- alert when disk usage approaches backup or upload capacity

## Scanner Governance

EDQ includes active network security tooling. Treat scan authorization as an operational control, not just a UI setting.

Minimum rules:

- only scan owned, administered, or explicitly approved networks
- keep authorized CIDRs as narrow as possible
- review authorized networks before every pilot or release test
- keep the tools sidecar bound to localhost or private Docker networks only
- review audit logs after pilot scans

## Production Rating Gate

EDQ can move from pilot-ready to production-ready only after the release gate, backup drill, monitoring gate, and scanner-governance checks have evidence attached.
