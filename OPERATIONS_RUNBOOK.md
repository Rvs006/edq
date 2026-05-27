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
11. Run the production gate script in the intended mode.

Commands:

```powershell
git switch main
git pull --ff-only origin main
docker compose up --build -d
.\scripts\configure-production.ps1 -Domain edq.example.com -BaseUrl https://edq.example.com -AuthorizedCidrs 192.168.10.0/24
.\scripts\verify-app.ps1
.\scripts\e2e-test.ps1
.\scripts\backend-test.ps1
docker scout cves edq-backend:latest --only-severity critical,high
docker scout cves edq-frontend:latest --only-severity critical,high
.\scripts\collect-production-evidence.ps1 -PilotDeviceIps 192.168.10.42
. .\reports\production\production-gate-env-YYYYMMDD_HHMMSS.ps1
.\scripts\production-gate.ps1 -Mode pilot -DeploymentConfig prod-compose
```

Pass `-BaseUrl` to `collect-production-evidence.ps1` when the URL under test differs from `EDQ_PUBLIC_URL`, such as a local pilot preflight before DNS is live or a final HTTPS check after cutover.
Pass `-BaseUrl` to `configure-production.ps1` when adding authorized CIDRs so the CIDR is written to the intended running stack.

Use `.\scripts\production-gate.ps1 -Mode production -DeploymentConfig prod-compose` only for wider production sign-off. Use `-DeploymentConfig tls-compose` for the Caddy TLS overlay, or `-DeploymentConfig internal-tls-compose` when using the private-hostname Caddy internal TLS overlay. Production mode fails until the operator has recorded evidence and set:

- `EDQ_BACKUP_RESTORE_DRILL_CONFIRMED=true`
- or `EDQ_BACKUP_RESTORE_DRILL_EVIDENCE=<path-to-passing-json>`
- `EDQ_MONITORING_CONFIRMED=true`
- or `EDQ_MONITORING_EVIDENCE=<path-to-passing-json>`
- `EDQ_SCAN_GOVERNANCE_CONFIRMED=true`
- or `EDQ_SCAN_GOVERNANCE_EVIDENCE=<path-to-passing-json>`
- `EDQ_REAL_DEVICE_PILOT_CONFIRMED=true`
- or `EDQ_REAL_DEVICE_PILOT_EVIDENCE=<path-to-passing-json>`

Production runtime checks must target the real HTTPS deployment URL. Use pilot mode for local preflight checks; production mode rejects local or non-HTTPS `-BaseUrl` values.

If there is no public domain yet, choose a stable internal hostname such as `edq.internal`, resolve it through internal DNS or hosts files, and start:

```powershell
docker compose -f docker-compose.yml -f docker-compose.tls.yml -f docker-compose.internal-tls.yml up -d
.\scripts\production-gate.ps1 -Mode production -DeploymentConfig internal-tls-compose -BaseUrl https://edq.internal
```

Every engineer workstation must trust the Caddy internal root CA before this is treated as production-like. If the certificate is not trusted, keep the deployment in pilot mode.

The GitHub gate is verified automatically when the GitHub CLI can read the repository: branch protection, required checks, latest `CI`, `CodeQL`, and `Container Security` runs, and open high/critical CodeQL and Dependabot alerts. Use `EDQ_GITHUB_SECURITY_CONFIRMED=true` only when that evidence was verified outside the script.

## Backup Drill

On Windows, run a disposable restore drill that does not replace the live database:

```powershell
.\scripts\backup-restore-drill.ps1
$env:EDQ_BACKUP_RESTORE_DRILL_EVIDENCE = "backups/restore-drills/edq_restore_drill_YYYYMMDD_HHMMSS.json"
```

The script dumps the running PostgreSQL database, restores it into a temporary PostgreSQL container, verifies core table counts, writes JSON evidence, and removes the temporary container.

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

After the record is stored, set `EDQ_BACKUP_RESTORE_DRILL_CONFIRMED=true` for production-gate validation.

## Monitoring Gate

Before shared production use:

- configure Sentry or equivalent exception monitoring
- collect backend, frontend, and PostgreSQL logs centrally
- alert when `/api/v1/health` is not healthy
- alert when tools versions cannot be fetched
- alert when disk usage approaches backup or upload capacity

Generate a local health-monitor evidence file after the alerting path is configured:

```powershell
New-Item -ItemType Directory -Force reports/production | Out-Null
.\scripts\monitor-health.ps1 -Json > reports/production/monitor-health-YYYYMMDD.json
```

Use `.\scripts\collect-production-evidence.ps1` for the normal release path because it passes the selected target URL into the monitoring check and writes a gate-ready `EDQ_MONITORING_EVIDENCE` file. After externally managed monitoring and alerting evidence is stored, set `EDQ_MONITORING_CONFIRMED=true` for production-gate validation.

## Scanner Governance

EDQ includes active network security tooling. Treat scan authorization as an operational control, not just a UI setting.

Generate a governance report against the running stack:

```powershell
New-Item -ItemType Directory -Force reports/production | Out-Null
.\scripts\scanner-governance-report.ps1
.\scripts\scanner-governance-report.ps1 -Json > reports/production/scanner-governance-YYYYMMDD.json
```

If a legacy database contains active ranges created by the removed auto-authorization behavior, review them first. To deactivate only those legacy `Auto-authorized` ranges through the API:

```powershell
.\scripts\scanner-governance-report.ps1 -DisableLegacyAutoAuthorized
```

Minimum rules:

- only scan owned, administered, or explicitly approved networks
- keep authorized CIDRs as narrow as possible
- review authorized networks before every pilot or release test
- keep the tools sidecar bound to localhost or private Docker networks only
- review audit logs after pilot scans

After the authorized CIDRs and audit-log review are recorded, set `EDQ_SCAN_GOVERNANCE_CONFIRMED=true` for production-gate validation.

## Real-Device Pilot

Run at least one representative qualification run against owned, administered, or explicitly approved devices. Do not use the PowerShell E2E smoke device as pilot evidence.

Generate pilot evidence from the running stack:

```powershell
New-Item -ItemType Directory -Force reports/production | Out-Null
.\scripts\real-device-pilot-report.ps1 -DeviceIps 192.168.10.42 -Json > reports/production/real-device-pilot-YYYYMMDD.json
```

For a broader pilot, increase `-MinCompletedRuns` and `-MinDistinctDevices`, and pass every expected device IP with `-DeviceIps`.

After the evidence is stored, set `EDQ_REAL_DEVICE_PILOT_CONFIRMED=true` or `EDQ_REAL_DEVICE_PILOT_EVIDENCE=<path-to-passing-json>` for production-gate validation.

## Production Rating Gate

EDQ can move from pilot-ready to production-ready only after the release gate, backup drill, monitoring gate, scanner-governance checks, and real-device pilot have evidence attached.


## Evidence Record Template

Create one record per release candidate or pilot rollout. Store it in the team's operational evidence system, not in the public repository if it includes customer names, network ranges, screenshots, logs, or backup filenames.

```text
EDQ release candidate:
Commit:
Operator:
Date:
Environment:
Access boundary:

Release gate:
- GitHub CI:
- CodeQL:
- Container scan:
- Local smoke test:
- API regression:
- Backend regression:

Backup and restore:
- Backup command:
- Backup location:
- Restore host or disposable environment:
- Restore validation:
- Data loss/recovery notes:

Monitoring:
- Error monitoring:
- Log aggregation:
- Health alert:
- Disk/backup alert:

Scanner governance:
- Approved CIDRs:
- Approver:
- Audit-log review:
- Pilot devices tested:
- False positives / false negatives:
- Report-quality issues:

Go/no-go decision:
Decision maker:
Follow-up issues:
```
