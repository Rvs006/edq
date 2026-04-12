# CI Audit Verification

This repo CI runs audit generation plus targeted backend/frontend verification. Goal: make findings reproducible, artifact-backed, and less hand-wavy.

## Workflow file

- `.github/workflows/ci.yml`

## Jobs

### 1. `audit-report`

Runs:

- `python scripts/audit/run_audit.py --scope full --format both --strict --strict-fail-on-severity high`
- `python scripts/audit/validate_report.py ...`

Produces:

- `reports/audit/ci/audit-report.json`
- `reports/audit/ci/audit-report.md`

Uploads artifacts even if later jobs fail.

What it proves:

- report structure valid
- findings contain required evidence fields
- summary counts are internally consistent
- report avoids forbidden blanket phrases
- high-confidence high/critical findings can fail CI if present

What it does **not** prove:

- exploitability
- absence of N+1 queries
- correctness of runtime auth semantics without tests

### 2. `backend-verify`

Runs targeted backend tests:

- `tests/test_auth.py`
- `tests/test_authorization.py`
- `tests/security/test_auth_security.py`
- `tests/security/test_rate_limiting.py`
- `tests/security/test_injection.py`
- `tests/test_health.py`

What it proves:

- core auth paths
- authorization behavior
- key security regression tests
- health route behavior

### 3. `frontend-verify`

Runs:

- TypeScript check: `pnpm exec tsc --noEmit`
- targeted Vitest suite:
  - `src/test/LoginPage.test.tsx`
  - `src/__tests__/AppRoutes.test.tsx`
  - `src/__tests__/DeviceDetailPage.test.tsx`

What it proves:

- frontend type graph still valid
- key auth/router/device-detail behavior still passes

### 4. `docker-build`

Runs after audit + targeted tests pass.

What it proves:

- Docker compose build still succeeds with CI environment variables

## Artifacts

CI uploads:

- `audit-report.json`
- `audit-report.md`

Artifact name:

- `audit-report`

## Local run

From repo root:

```text
python scripts/audit/run_audit.py --scope full --output-dir reports/audit/local --format both
python scripts/audit/validate_report.py --report reports/audit/local/audit-report.json --markdown reports/audit/local/audit-report.md
cd server/backend && pytest tests/test_auth.py tests/test_authorization.py tests/security/test_auth_security.py tests/security/test_rate_limiting.py tests/security/test_injection.py tests/test_health.py -v --tb=short
pnpm --dir frontend exec tsc --noEmit
pnpm --dir frontend exec vitest run src/test/LoginPage.test.tsx src/__tests__/AppRoutes.test.tsx src/__tests__/DeviceDetailPage.test.tsx
```

## Failure interpretation

### Audit job fails

Likely causes:

- malformed JSON/Markdown report
- missing evidence fields
- summary mismatch
- forbidden blanket phrase detected
- high-confidence high/critical finding reached configured threshold

### Backend job fails

Likely causes:

- auth/authz regression
- security regression
- health behavior regression

### Frontend job fails

Likely causes:

- TypeScript breakage
- route/auth/device-detail regression

## Why targeted tests

PR path stays faster and still checks highest-value security/auth behavior. Full broader suites can run manually or in a future scheduled workflow.