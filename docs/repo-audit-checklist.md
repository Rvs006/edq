# Repo Audit Checklist

Use this checklist after running `scripts/audit/run_audit.py`. Goal: turn pattern scan into higher-confidence review.

## 1. Scope and exclusions

- Confirm scan scope:
  - `full` for whole-repo audit
  - `changed` for diff review
- Confirm excluded paths match intent:
  - `.venv`
  - `node_modules`
  - `dist`
  - `build`
  - `__pycache__`
  - cache and coverage outputs
- Confirm report metadata includes:
  - commit SHA
  - branch
  - generation time
  - exact command run

## 2. Evidence sanity

For each finding:

- file path repo-relative
- line numbers present
- snippet matches source
- claim status sensible
- severity not inflated
- confidence justified
- remediation actionable

Reject finding if:

- evidence missing
- snippet wrong
- path points into excluded dependency folder
- conclusion overstates what evidence proves

## 3. Authentication and authorization review

Use route inventory from report.

Check:

- public endpoints intentionally public
- authenticated endpoints return `401` when unauthenticated
- role-protected endpoints return `403` for wrong role
- inactive users blocked where expected
- alternate auth paths documented:
  - agent key routes
  - metrics/API key routes

Required evidence before global auth claim:

- route inventory complete
- request tests cover representative public/auth/role/alternate-auth paths
- false positives documented

Do **not** claim “all endpoints are protected” unless every endpoint has been classified and tested.

## 4. SQL injection review

Automation can prove raw SQL presence, not exploitability.

For each raw SQL site:

- identify source file and line
- inspect whether user-controlled data reaches query
- confirm parameter binding or fixed literal SQL
- add/request targeted injection test if endpoint is externally reachable

Acceptable outcomes:

- fixed-literal raw SQL, low risk
- parameterized raw SQL, documented
- exploitability unknown, manual review required

Do **not** claim “all queries are parameterized” unless every query path was exhaustively checked.

## 5. N+1 and performance review

Automation should not auto-claim “no N+1 queries”.

Manual verification:

- identify list/detail endpoints with ORM relationships
- enable SQL logging or query-count capture
- compare single-item and multi-item query counts
- inspect eager-loading usage (`selectinload`, `joinedload`, etc.)
- document measured result

Required before saying N+1 absent:

- runtime measurement
- representative endpoint coverage
- evidence attached to report or perf notes

## 6. Resource lifecycle review

Check:

- background task singletons guarded by start/stop checks
- cancellation path exists
- restart path avoids duplicate task creation
- websocket cleanup paths tested
- subprocess cleanup paths log or intentionally ignore failures

For each singleton task finding:

- determine whether pattern is intentional
- note lifecycle tests that cover it
- record unresolved shutdown/startup edge cases

## 7. Debug and runtime logging review

Check `print()` findings.

Classify each as:

- runtime startup path
- local development only
- setup/init script
- migration script

Expectation:

- runtime code should prefer structured logging
- scripts may use human-readable `print()` intentionally

Do not summarize all `print()` findings as bugs without classification.

## 8. Exception handling review

For each broad `except Exception` finding, classify:

- logs and re-raises
- logs and returns safe fallback
- safe framework boundary fallback
- swallowed with `pass`
- fallback without logging

Priority:

- swallowed with `pass` and no logging: highest review priority
- fallback without logging in security-sensitive path: high review priority
- logged fallback in health or cleanup path: lower priority

Do not count all broad handlers as equally risky.

## 9. Dependency and version review

Separate from code-pattern audit.

Manual or CI checks should confirm:

- backend dependency versions from `requirements.txt`
- frontend dependency versions from lockfile/package manifest
- package audit tool results if run
- known vulnerability exceptions documented

Do not mix version currency with code safety claims.

## 10. Test coverage review

Confirm inventories:

- backend test modules counted correctly
- frontend test modules counted correctly
- helper files not miscounted as test modules

For major claims, ask:

- which test proves this?
- is it unit, integration, or behavior coverage?
- is failure path tested?

## 11. False-positive review

For each rejected finding, record:

- finding ID
- why rejected
- who reviewed
- source snippet reviewed
- whether rule should be tuned

Common false-positive candidates:

- cleanup-only `except Exception: pass`
- script-only `print()` calls
- test-only `as any`
- fixed health-check `text("SELECT 1")`

## 12. Final sign-off rules

Before publishing audit summary:

- no forbidden blanket claims
- summary counts match detailed findings
- limitations section present
- manual review items present for unproven claims
- reviewer checked top-severity findings
- route auth claims backed by route inventory plus request tests
- SQL injection claims backed by data-flow or tests
- N+1 claims backed by measurement, not guesswork

## 13. Local validation commands

Recommended local sequence:

```text
python scripts/audit/run_audit.py --scope full --output-dir reports/audit/local --format both
python scripts/audit/validate_report.py --report reports/audit/local/audit-report.json --markdown reports/audit/local/audit-report.md
cd server/backend && pytest tests/test_auth.py tests/test_authorization.py tests/security/test_auth_security.py tests/security/test_rate_limiting.py tests/security/test_injection.py tests/test_health.py -v --tb=short
pnpm --dir frontend exec tsc --noEmit
pnpm --dir frontend exec vitest run src/test/LoginPage.test.tsx src/__tests__/AppRoutes.test.tsx src/__tests__/DeviceDetailPage.test.tsx
```

## 14. Audit publication rule

If reviewer cannot defend claim with evidence, move it to:

- `inferred`
- `unverified`
- or `manual_review_required`

Never publish unsupported certainty.