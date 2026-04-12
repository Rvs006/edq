# Evidence Audit Report

## Executive summary

- Repository: `<repo-name>`
- Commit: `<sha>`
- Generated at: `<timestamp>`
- Scope: `<full|changed|example>`
- Total findings: `<count>`
- Verified facts: `<count>`
- Manual review required: `<count>`

## Scope and exclusions

- Included scope: `<paths or diff scope>`
- Excluded paths: `<comma-separated exclusions>`
- Commands run:
  - `<command-1>`
  - `<command-2>`

## Verification methods used

- `<method>`
- `<method>`

## Findings summary

### By severity

| Severity | Count |
| --- | --- |
| critical | `<n>` |
| high | `<n>` |
| medium | `<n>` |
| low | `<n>` |
| info | `<n>` |

### By confidence

| Confidence | Count |
| --- | --- |
| high | `<n>` |
| medium | `<n>` |
| low | `<n>` |

### By claim status

| Status | Count |
| --- | --- |
| verified | `<n>` |
| inferred | `<n>` |
| unverified | `<n>` |
| disproven | `<n>` |
| not_applicable | `<n>` |

## Detailed findings

### `<finding-id>` - `<title>`

- Rule: `<rule-id>`
- Category: `<category>`
- Severity: `<severity>`
- Confidence: `<confidence>`
- Claim status: `<claim-status>`
- Intentional pattern: `<true|false>`
- Description: `<description>`
- Evidence: `<relative-path:start-end>`

```text
<snippet>
```

- Verification steps:
  - `<step>`
  - `<step>`
- False-positive notes: `<notes>`
- Remediation: `<remediation>`

## Intentional / low-risk patterns

- `<finding-id>` `<why pattern may be intentional>`

## Not proven / manual review required

- `<manual-review-id>` `<topic>`: `<reason>`
  - `<recommended verification>`

## False positives rejected

- `<finding-id>` rejected because `<reason>`

## Reproduction / validation commands

- `<command>`
- `<command>`

## Final assessment with limitations

- `<limitation>`
- `<limitation>`