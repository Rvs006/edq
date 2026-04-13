# Security Tooling

EDQ is wired to use a local/global ShieldMyRepo installation for repo security checks.

## Available commands

### npm

```powershell
npm run security:doctor
npm run security:doctor:sh
npm run security:scan
npm run security:scan:json
npm run security:scan:sh
npm run security:scan:sh:json
npm run security:all
npm run security:all:sh
npm run security:update
```

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
.\security-update.cmd --no-pause
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
- `EDQ Security Update.lnk`
