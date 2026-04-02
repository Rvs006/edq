# EDQ

EDQ (Electracom Device Qualifier) is a local-first app for qualifying smart building IP devices with automated security checks, guided manual assessments, and report generation.

This repository is now organized for an engineer testing handoff. Use the docs below in this order instead of reading the historical specs first.

## Quick Start

```bash
git clone https://github.com/Rvs006/edq.git
cd edq
./setup.sh
```

On Windows, run `setup.bat` instead.

Then:

1. Open `http://localhost`
2. Log in with username `admin`
3. Use the password stored in the root `.env` file
4. Change the password after first login
5. Run the smoke test:

```bash
./scripts/verify-app.sh
```

On Windows PowerShell:

```powershell
.\scripts\verify-app.ps1
```

Full local engineer instructions: [INSTALL.md](INSTALL.md)

## What Engineers Should Test

- Login and basic navigation
- Device creation and test run creation
- Manual test result entry
- Report generation
- Authorized network setup before any subnet scan
- Update flow with `update.sh` or `update.bat`

## Documentation Map

- [INSTALL.md](INSTALL.md): Primary local engineer setup and testing guide
- [ENGINEER_UPDATES.md](ENGINEER_UPDATES.md): Update instructions for engineers who already have EDQ installed
- [DEPLOY.md](DEPLOY.md): Production and shared-environment deployment only
- [SECURITY.md](SECURITY.md): Current auth, secret, and operator security notes
- [docs/README.md](docs/README.md): Current docs versus archived docs
- [scripts/backend-test.ps1](scripts/backend-test.ps1): Windows backend test runner using Docker

## Current App Shape

- `frontend`: React app served through nginx on `http://localhost`
- `backend`: FastAPI API on container port `8000`, proxied through the frontend
- `tools`: security tooling sidecar for scans and protocol checks
- `reports/`, `uploads/`, and database state are persisted through Docker volumes

## Notes

- The supported local config file is the root `.env` file only.
- Interactive backend API docs are available only when `DEBUG=true`.
- Network scanning is blocked until an admin adds authorized networks in the app.
- Historical spec documents still exist for context, but they are not the current setup guide.
