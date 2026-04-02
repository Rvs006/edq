# Contributing to EDQ

## Local Development

1. Clone the repository
2. Create the root `.env` or run `setup.sh` / `setup.bat`
3. Start the stack with `docker compose up --build`

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
- backend tests: `pytest server/backend/tests -v`

## Documentation Map

Use current docs first:

- [README.md](README.md)
- [INSTALL.md](INSTALL.md)
- [ENGINEER_UPDATES.md](ENGINEER_UPDATES.md)
- [DEPLOY.md](DEPLOY.md)
- [SECURITY.md](SECURITY.md)
- [CHANGELOG.md](CHANGELOG.md)
- [docs/README.md](docs/README.md)

Historical specs remain in `docs/` for reference only. They are not the current operational guide for setup, deployment, or API behavior.
