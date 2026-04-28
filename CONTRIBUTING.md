# Contributing to EDQ

## Local Development

- Clone the repository.
- For normal full-stack work, create the root `.env` or run `setup.sh` / `setup.bat`, then start the stack with `docker compose up --build`.
- For frontend or backend development outside Docker, follow [LOCAL_DEVELOPMENT.md](LOCAL_DEVELOPMENT.md).

## Code Standards

### Backend

- keep route handlers thin
- put business logic in `services/`
- use typed request and response schemas
- prefer explicit validation and clear error messages

### Frontend

- keep components functional
- keep shared data fetching in the existing query layer
- preserve the established UI language in this repo

## Tests

- smoke test: `./scripts/verify-app.sh`
- Windows smoke test: `.\scripts\verify-app.ps1`
- optional API regression script: `./scripts/e2e-test.sh`
- Windows API regression script: `.\scripts\e2e-test.ps1`
- backend suite via Docker: `./scripts/backend-test.sh` or `.\scripts\backend-test.ps1`
- local backend test deps: `python -m pip install -r server/backend/requirements-dev.txt`
- backend tests: `pytest server/backend/tests -v`

## Documentation Map

Use current docs first:

- [README.md](README.md)
- [INSTALL.md](INSTALL.md)
- [LOCAL_DEVELOPMENT.md](LOCAL_DEVELOPMENT.md)
- [ENGINEER_UPDATES.md](ENGINEER_UPDATES.md)
- [DEPLOY.md](DEPLOY.md)
- [OPERATIONS_RUNBOOK.md](OPERATIONS_RUNBOOK.md)
- [SECURITY.md](SECURITY.md)
- [PRODUCTION_READINESS.md](PRODUCTION_READINESS.md)
- [CHANGELOG.md](CHANGELOG.md)

Historical specs remain in `docs/` for reference only. They are not the current operational guide for setup, deployment, or API behavior.

For documentation changes, update the root operational docs instead of editing archived specs unless the task explicitly asks to preserve historical context.
