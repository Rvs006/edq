# Example Evidence Audit Report

## Executive summary

- Repository: `edq`
- Generated at: `2026-04-12T00:00:00Z`
- Scope: `example`
- Total findings: `5`
- Verified facts: `5`
- Manual review required: `2`

## Scope and exclusions

- Excluded paths: `.git`, `.venv`, `node_modules`, `dist`, `build`, `__pycache__`, `.pytest_cache`, `coverage`, `htmlcov`, `.mypy_cache`, `.ruff_cache`, `.code-review-graph`, `reports/audit`, `testsprite_tests`
- Command:
  - `python scripts/audit/run_audit.py --scope full --output-dir reports/audit/local --format both`

## Verification methods used

- Manual-example evidence copied from real repo locations
- Relative paths and exact snippets
- No blanket safety claims

## Findings summary

### By severity

| Severity | Count |
| --- | --- |
| critical | 0 |
| high | 0 |
| medium | 2 |
| low | 3 |
| info | 0 |

### By confidence

| Confidence | Count |
| --- | --- |
| high | 5 |
| medium | 0 |
| low | 0 |

## Detailed findings

### AUD-EXAMPLE-001 - Type-safety bypass via `as any`

- Category: `type_safety`
- Severity: `medium`
- Confidence: `high`
- Claim status: `verified`
- Evidence: `frontend/src/pages/DeviceDetailPage.tsx:40-40`

```text
const val = (device as any)[key]
```

- Verification steps:
  - Run `pnpm --dir frontend exec tsc --noEmit`.
  - Replace `as any` with typed key access such as `keyof Device` where practical.

### AUD-EXAMPLE-002 - Module-level background task singleton state

- Category: `background_tasks`
- Severity: `low`
- Confidence: `high`
- Claim status: `verified`
- Intentional pattern: `true`
- Evidence: `server/backend/app/services/scan_scheduler.py:26-26`

```text
_scheduler_task: asyncio.Task | None = None
```

### AUD-EXAMPLE-003 - Console `print()` call present

- Category: `runtime_logging`
- Severity: `low`
- Confidence: `high`
- Claim status: `verified`
- Evidence: `server/backend/app/main.py:360-360`

```text
print(f"[EDQ] Frontend directory: {FRONTEND_DIR} (exists: {os.path.isdir(FRONTEND_DIR)})")
```

### AUD-EXAMPLE-004 - Exception swallowed with `pass`

- Category: `exception_handling`
- Severity: `medium`
- Confidence: `high`
- Claim status: `verified`
- Evidence: `tools/server.py:57-62`

```text
try:
    proc.kill()
    proc.wait(timeout=5)
    killed += 1
except Exception:
    pass
```

### AUD-EXAMPLE-005 - Raw SQL `text(...)` usage present

- Category: `sql_usage`
- Severity: `low`
- Confidence: `high`
- Claim status: `verified`
- Evidence: `server/backend/app/routes/health.py:52-52`

```text
await session.execute(text("SELECT 1"))
```

## Intentional / low-risk patterns

- `AUD-EXAMPLE-002` singleton task handle may be intentional lifecycle control

## Not proven / manual review required

- `MR-001` SQL injection exploitability: raw SQL presence does not prove vulnerability
- `MR-002` Background task lifecycle safety: runtime start/stop behavior still needs testing

## Final assessment with limitations

- This file is example format, not complete live audit
- Pattern presence does not equal exploitability
- Route inventory classification does not replace request-level auth tests