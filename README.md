# EDQ

EDQ, short for Electracom Device Qualifier, is a local-first qualification app for smart building IP devices. It gives engineers one place to discover devices, run repeatable security checks, capture guided manual findings, and generate client-ready reports.

## What EDQ Is For

EDQ is built for teams qualifying cameras, controllers, intercoms, sensors, meters, and other IP-connected building devices before they are accepted onto enterprise networks.

It replaces fragmented terminal work, spreadsheet transcription, and manual report writing with a single workflow:

1. Register or discover a device.
2. Auto-profile the device and load the right qualification setup.
3. Run 43 universal checks: 29 automated and 14 guided manual.
4. Review findings, overrides, and audit history.
5. Generate Excel, Word, PDF, or CSV deliverables.

## Who Uses It

| Role | Typical Responsibilities |
| --- | --- |
| Admin | Manage users, security settings, authorized networks, branding, and operational controls |
| Engineer | Discover devices, run tests, complete manual checks, and generate reports |
| Reviewer | Review results, approve outcomes, and apply justified overrides |

## Current App Surface

- Dashboard: qualification activity, recent runs, and quick actions
- Devices and device detail: device records, discovered metadata, CVE lookup, and report context
- Device Profiles: fingerprint rules that classify devices and tailor test applicability
- Test Runs: live execution, manual steps, cancel and resume controls, and run history
- Bulk Discovery: subnet scanning, enriched network results, and device intake
- Templates, Test Plans, Scan Schedules, and Whitelists: reusable qualification configuration
- Reports: Excel, Word, and PDF generation for completed runs
- Review Queue: reviewer workflow and outcome control
- Admin: users, settings, audit visibility, and system governance
- Authorized Networks: admin-controlled scan boundaries for subnet discovery
- Agents: optional distributed runner registrations for non-default deployments
- Security and identity: username login, refresh-token sessions, CSRF protection, 2FA, and optional OIDC/SSO
- Reporting extras: branding settings and AI synopsis drafting when configured

## Architecture At A Glance

EDQ currently ships as a three-container Docker stack plus an optional Electron wrapper:

- `frontend`: React app served by nginx and published at `http://localhost:3000` by default
- `backend`: FastAPI API and the co-located tools sidecar on container ports `8000` and `8001`, proxied through the frontend
- `postgres`: primary application database for both Docker and direct local backend runs
- `redis`: optional shared-environment rate limiting and session support (profile-based)
- `electron`: packaged desktop wrapper for local workstation use

Persistent state is stored in Docker volumes for:

- database state: `edq-pgdata`
- legacy SQLite backups or transitional local data: `edq-data`
- uploaded files: `edq-uploads`
- generated reports: `edq-reports`

The supported local configuration file is the repo-root `.env`.

## Quick Start

macOS or Linux:

```bash
git clone https://github.com/Rvs006/edq.git
cd edq
./setup.sh
```

Windows PowerShell:

```powershell
git clone https://github.com/Rvs006/edq.git
cd edq
.\setup.bat
```

After startup:

1. Open `http://localhost:3000`
2. Log in with username `admin`
3. Use the password stored in `INITIAL_ADMIN_PASSWORD` in the root `.env`
4. Run the smoke test:

macOS or Linux:

```bash
./scripts/verify-app.sh
```

Windows PowerShell:

```powershell
.\scripts\verify-app.ps1
```

5. Change the password after first login

If you rotate the admin password before rerunning smoke scripts, pass the current password with `EDQ_ADMIN_PASS`, `-AdminPass`, or the matching PowerShell parameter. The root `.env` keeps the initial seed password only.

## Security Scanning

EDQ includes a simple local ShieldMyRepo workflow for quick repo hygiene checks.

ShieldMyRepo uses a standard letter grade scale:

- `A`: 90-100
- `B`: 80-89
- `C`: 70-79
- `D`: 60-69
- `F`: below 60

Run a full local scan from the repo root with either:

```bash
npm run security:scan
```

```bash
./scripts/security-scan.sh
```

```powershell
.\scripts\security-scan.ps1
```

To regenerate JSON only:

```bash
npm run security:scan:json
```

```bash
./scripts/security-scan.sh json
```

Check local ShieldMyRepo health with:

```bash
./scripts/security-doctor.sh
```

```powershell
.\scripts\security-doctor.ps1
```

Run the full local security flow (doctor -> scan -> doctor) with:

```bash
npm run security:all
```

```bash
npm run security:all:sh
```

On Windows you can also run the repo-root launcher:

```powershell
.\security-all.cmd --no-pause
```

Or simply double-click `security-all.cmd` from File Explorer.

You also have dedicated Windows launchers:

```powershell
.\security-doctor.cmd --no-pause
.\security-scan.cmd --no-pause
.\security-all.cmd --no-pause
.\security-update.cmd --no-pause
```

You can also update the global ShieldMyRepo install with:

```powershell
npm run security:update
```

For the complete security tooling reference, see [SECURITY_TOOLING.md](SECURITY_TOOLING.md).


Generated outputs are written to:

- `reports/shieldmyrepo-report.md`
- `reports/shieldmyrepo-report.json`
- `reports/shieldmyrepo-badge.svg`

## Documentation Map

| File | Purpose |
| --- | --- |
| [INSTALL.md](INSTALL.md) | Primary local install, validation, and troubleshooting guide |
| [LOCAL_DEVELOPMENT.md](LOCAL_DEVELOPMENT.md) | Local frontend and backend development outside the full Docker stack |
| [ENGINEER_UPDATES.md](ENGINEER_UPDATES.md) | Update-only workflow for existing local installs |
| [DEPLOY.md](DEPLOY.md) | Shared and production deployment guidance |
| [SECURITY.md](SECURITY.md) | Current security model, secret handling, and operational controls |
| [SECURITY_TOOLING.md](SECURITY_TOOLING.md) | ShieldMyRepo + security scanner reference |
| [REDIS.md](REDIS.md) | Optional Redis profile for shared-env rate limiting |
| [CHANGELOG.md](CHANGELOG.md) | Curated history of major changes after the original v1.0 baseline |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Development and contribution notes |
| [CLAUDE.md](CLAUDE.md) / [AGENTS.md](AGENTS.md) | Guidance for AI coding agents working in this repo |

## Current Operational Notes

- Local login accepts either username or email. The seeded admin username is `admin`.
- `setup.sh` and `setup.bat` create the root `.env`, fill missing secrets, and generate an initial admin password if needed.
- For shared environments, enable the Redis profile and set `REDIS_URL` so rate limiting is consistent across instances.
- The default runtime database is PostgreSQL on `127.0.0.1:55432`; Docker overrides the backend container to use the internal `postgres` host on `5432`.
- Optional frontend telemetry is controlled by `VITE_*` build-time variables such as `VITE_CLIENT_ERROR_ENDPOINT` and `VITE_SENTRY_ENABLED`; if unset, the frontend keeps using the local client-error beacon path with safe defaults.
- Interactive backend API docs are available only when `DEBUG=true`.
- Subnet scanning is blocked until an admin configures at least one authorized network range in the app.
- Single-IP discovery uses an AND-gate reachability check: a target must answer **both** a fresh TCP/ICMP probe and nmap's ARP-bypass ping before the full scan runs. This prevents stale-ARP ghost results on recently unplugged devices.
- Frontend and backend development can run locally outside Docker; the tools sidecar remains Docker-backed on Windows. See [LOCAL_DEVELOPMENT.md](LOCAL_DEVELOPMENT.md).
- Historical product and engineering specs remain in `docs/` as archive material only and should not be treated as the current operational guide.

## Archived Reference

These files remain available for historical context:

- [docs/PRODUCT_REQUIREMENTS.md](docs/PRODUCT_REQUIREMENTS.md)
- [docs/ENGINEERING_SPEC.md](docs/ENGINEERING_SPEC.md)
- [docs/DESIGN_SYSTEM.md](docs/DESIGN_SYSTEM.md)
