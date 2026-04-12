# Evidence Audit Report Spec

## Purpose

This spec defines EDQ audit report contract. Goal: stop vague scan summaries, force evidence on each finding, separate proven facts from inference, and make CI checks reproducible.

Use this spec for:

- local audit runs
- CI artifact generation
- manual reviewer sign-off
- future automation that parses repo audit outputs

## Core rules

1. No finding without evidence.
2. No summary claim without traceable support.
3. No unsupported absolute language.
4. Pattern presence does not equal exploitability.
5. Intentional patterns may be reported without being auto-labeled bugs.
6. Summary counts must match detailed findings exactly.

## Forbidden language

These phrases are forbidden unless reviewer attaches explicit proof trail and marks claim verified:

- `no critical bugs found`
- `all endpoints are protected`
- `all queries are parameterized`
- `no N+1 queries`
- `fully safe`
- `100/100 reliable`

Preferred alternatives:

- `No high-confidence findings at or above configured threshold`
- `Route inventory classified 37 endpoints as role-protected`
- `Raw SQL text(...) usage present; exploitability not proven automatically`

## Report artifacts

- JSON report: machine-readable, CI-validated
- Markdown report: human-readable review artifact
- JSON schema: structural contract
- Markdown template: reusable authoring format

Canonical paths:

- Schema: `reports/schemas/audit-report.schema.json`
- Template: `reports/templates/evidence-audit-report.md`

## Top-level JSON structure

Required keys:

- `$schema`
- `report_version`
- `metadata`
- `summary`
- `inventories`
- `limitations`
- `manual_review_required`
- `findings`

## Metadata

Required fields:

- `repository_name`
- `generated_at`
- `scan_scope`
- `excluded_paths`
- `generator`
- `commands`

Recommended fields:

- `base_ref`
- `changed_files`
- `commit_sha`
- `branch`

### `scan_scope`

Allowed values:

- `full`
- `changed`
- `example`

Use `example` only for illustrative sample reports under `reports/examples/`.

## Finding structure

Required fields:

- `id`
- `rule_id`
- `category`
- `severity`
- `confidence`
- `claim_status`
- `title`
- `description`
- `intentional_pattern`
- `evidence`
- `verification_steps`
- `false_positive_notes`
- `remediation`

### Severity taxonomy

- `critical`
- `high`
- `medium`
- `low`
- `info`

Severity = triage priority, not certainty.

### Confidence taxonomy

- `high`
- `medium`
- `low`

Confidence = confidence in finding statement, not business impact.

### Claim status taxonomy

- `verified`
- `inferred`
- `unverified`
- `disproven`
- `not_applicable`

Use:

- `verified` when evidence proves exact statement
- `inferred` when evidence proves pattern and report adds limited risk interpretation
- `unverified` when automation found signal but not enough proof for conclusion
- `disproven` when prior claim was checked and shown false
- `not_applicable` when rule does not apply to scope

## Evidence structure

Each finding must include at least one evidence item.

Required evidence fields:

- `file_path`
- `line_start`
- `line_end`
- `snippet`
- `collection_method`

Rules:

- `file_path` must be repo-relative
- snippet must be exact matched text or exact nearby code excerpt
- evidence must be enough for reviewer to reopen source quickly

### `collection_method`

Allowed values:

- `pattern`
- `ast`
- `inventory`
- `manual`
- `manual_example`

## Summary structure

Required summary sections:

- findings by severity
- findings by confidence
- findings by claim status
- findings by category
- intentional pattern count
- manual review required count
- verified fact count
- inferred risk count
- unverified claim count
- forbidden phrase detections

Counts must be derivable from detailed findings.

## Inventories

Inventory sections document facts that are useful but not findings by themselves.

Required inventories:

- `route_surface`
- `tests`
- `logging`
- `scan_stats`

Examples:

- route auth classification counts
- backend/frontend test module inventories
- count of `logger.exception(...)`
- scan-scope file count

## Non-finding sections

### `limitations`

Must state what automation did not prove. Examples:

- exploitability not proven
- runtime performance not measured
- dependency vulnerabilities not checked by package audit tool

### `manual_review_required`

Use for topics automation cannot finish alone. Each item needs:

- `id`
- `topic`
- `reason`
- `recommended_verification`

Examples:

- SQL injection exploitability
- route-auth response semantics
- N+1 query behavior
- lifecycle behavior of background tasks

## Authoring rules

1. No finding without evidence.
2. No evidence with absolute path.
3. No summary numbers that cannot be recomputed from findings.
4. No statement that upgrades pattern presence into vulnerability without proof.
5. Intentional patterns must say why they may be intentional.
6. False-positive notes must explain likely-safe contexts.
7. Verification steps must be actionable.

## Markdown report requirements

Markdown report must contain:

- Executive summary
- Scope and exclusions
- Verification methods used
- Findings summary tables
- Detailed findings
- Intentional / low-risk patterns
- Not proven / manual review required
- False positives rejected
- Reproduction / validation commands
- Final assessment with limitations

## Reviewer sign-off rules

Final sign-off should record:

- reviewer name
- review date
- report path and commit SHA
- which findings were manually inspected
- which claims remain unresolved
- which findings were rejected as false positives

No sign-off should say repo is “safe” or “fully verified” unless scope, runtime tests, and dependency review explicitly support that statement.

## Mapping to automation

This spec is designed for:

- `scripts/audit/run_audit.py` to generate JSON + Markdown
- `scripts/audit/validate_report.py` to validate required structure and evidence fields
- GitHub Actions to fail on malformed reports, missing evidence, or configured high-confidence severity thresholds

## Example interpretation rules

- `as any` in app code: verified fact, medium severity, high confidence
- `text(...)` SQL usage: verified fact, low severity, high confidence, not automatically injectable
- `except Exception`: verified fact, severity depends on swallow/log/fallback behavior
- module-level task singleton: verified fact, often intentional, low severity unless lifecycle checks fail

## Minimum acceptable audit package

Acceptable audit result must include:

- valid JSON report
- valid Markdown report
- at least one explicit limitations section
- explicit manual-review items for claims automation cannot prove
- no forbidden blanket claims