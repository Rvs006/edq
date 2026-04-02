# EDQ

EDQ, short for Electracom Device Qualifier, is a local-first qualification app for smart building IP devices. It gives engineers one place to discover devices, run repeatable security checks, capture guided manual findings, and generate client-ready reports.

## What EDQ Is For

EDQ is built for teams qualifying cameras, controllers, intercoms, sensors, meters, and other IP-connected building devices before they are accepted onto enterprise networks.

It replaces fragmented terminal work, spreadsheet transcription, and manual report writing with a single workflow:

1. Register or discover a device.
2. Auto-profile the device and load the right qualification setup.
3. Run 43 universal checks: 29 automated and 14 guided manual.
4. Review findings, overrides, and audit history.
5. Generate Excel, Word, or PDF deliverables.

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

EDQ currently ships as a three-service Docker stack plus an optional Electron wrapper:

- `frontend`: React app served by nginx on `http://localhost`
- `backend`: FastAPI API and WebSocket server on container port `8000`, proxied through the frontend
- `tools`: tooling sidecar used by automated checks for network, TLS, web, and credential probes
- `electron`: packaged desktop wrapper for local workstation use

Persistent state is stored in Docker volumes for:

- database state: `edq-data`
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

1. Open `http://localhost`
2. Log in with username `admin`
3. Use the password stored in `INITIAL_ADMIN_PASSWORD` in the root `.env`
4. Change the password after first login
5. Run the smoke test:

macOS or Linux:

```bash
./scripts/verify-app.sh
```

Windows PowerShell:

```powershell
.\scripts\verify-app.ps1
```

## Documentation Map

| File | Purpose |
| --- | --- |
| [INSTALL.md](INSTALL.md) | Primary local install, validation, and troubleshooting guide |
| [ENGINEER_UPDATES.md](ENGINEER_UPDATES.md) | Update-only workflow for existing local installs |
| [DEPLOY.md](DEPLOY.md) | Shared and production deployment guidance |
| [SECURITY.md](SECURITY.md) | Current security model, secret handling, and operational controls |
| [CHANGELOG.md](CHANGELOG.md) | Curated history of major changes after the original v1.0 baseline |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Development and contribution notes |

## Current Operational Notes

- Local login accepts either username or email. The seeded admin username is `admin`.
- `setup.sh` and `setup.bat` create the root `.env`, fill missing secrets, and generate an initial admin password if needed.
- Interactive backend API docs are available only when `DEBUG=true`.
- Subnet scanning is blocked until an admin configures at least one authorized network range in the app.
- Historical product and engineering specs remain in `docs/` as archive material only and should not be treated as the current operational guide.

## Archived Reference

These files remain available for historical context:

- [docs/PRODUCT_REQUIREMENTS.md](docs/PRODUCT_REQUIREMENTS.md)
- [docs/ENGINEERING_SPEC.md](docs/ENGINEERING_SPEC.md)
- [docs/DESIGN_SYSTEM.md](docs/DESIGN_SYSTEM.md)
