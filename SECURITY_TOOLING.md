# Security Tooling

EDQ is wired to use a local/global ShieldMyRepo installation for repo security checks.

For container dependency checks, use Docker Scout against the built backend image:

```powershell
docker scout cves edq-backend:latest
docker scout cves edq-backend:latest --only-severity critical,high
```

GitHub vulnerability alerts, Dependabot security updates, secret scanning, and push protection are enabled for this repository.

Current repository automation includes:

- Dependabot configuration for GitHub Actions, frontend, Electron, backend Python dependencies, tools Python dependencies, and Dockerfiles.
- Routine Dependabot version-update PRs are disabled with `open-pull-requests-limit: 0`; security updates remain enabled through GitHub security settings.
- CodeQL workflow for Python and JavaScript/TypeScript.
- Container security workflow that scans the backend image for critical and high CVEs.
- Nightly full-verification workflow for broader backend, frontend, and Docker smoke coverage.
- Branch protection requires the real CI job names plus `container-scan`.

## Available commands

### PowerShell

```powershell
.\scripts\security-doctor.ps1
.\scripts\security-scan.ps1
.\scripts\security-scan.ps1 -Format json
```

### Bash / WSL

```bash
./scripts/security-doctor.sh
./scripts/security-scan.sh
./scripts/security-scan.sh json
```

### Windows launchers

```powershell
.\security-doctor.cmd --no-pause
.\security-scan.cmd --no-pause
.\security-all.cmd --no-pause
```

You can also double-click the `.cmd` files from File Explorer.

## Reports

ShieldMyRepo writes outputs to:

- `reports/shieldmyrepo-report.md`
- `reports/shieldmyrepo-report.json`
- `reports/shieldmyrepo-badge.svg`

## Grade scale

- `A`: 90-100
- `B`: 80-89
- `C`: 70-79
- `D`: 60-69
- `F`: below 60

## Auto-update

A daily scheduled task keeps ShieldMyRepo updated:

- Task name: `ShieldMyRepo Auto Update Daily`
- Log file: `C:\Users\ASUS\.local\share\shieldmyrepo-mcp\update.log`

## Desktop shortcuts

The following shortcuts are placed on the Windows desktop:

- `EDQ Security Doctor.lnk`
- `EDQ Security Scan.lnk`
- `EDQ Security All.lnk`
