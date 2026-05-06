# Pull Request

## Description

Brief description of changes.

## Type of Change

- [ ] Bug fix
- [ ] New feature
- [ ] Breaking change
- [ ] Documentation update

## Testing

- [ ] Smoke test run
- [ ] API regression run when API behavior changed
- [ ] Backend tests run when backend code changed
- [ ] Frontend tests run when frontend code changed
- [ ] Docs reviewed for setup, deploy, or security impact

Smoke test commands:

```text
./scripts/verify-app.sh
.\scripts\verify-app.ps1
```

Regression commands:

```text
./scripts/e2e-test.sh
.\scripts\e2e-test.ps1
./scripts/backend-test.sh
.\scripts\backend-test.ps1
cd frontend && pnpm typecheck
cd frontend && pnpm test
```

## Screenshots

If applicable, add screenshots or screen recordings to demonstrate the changes.

## Checklist

- [ ] Code follows project conventions
- [ ] Type hints added (Python)
- [ ] No `console.log` in production code
- [ ] Error handling included
- [ ] Readiness or deployment notes updated when release risk changed
