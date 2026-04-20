# Changelog

This is a curated change history for EDQ. It is intentionally grouped by meaningful milestones instead of listing every commit.

The original `EDQ v1.0` baseline is commit `3a85953`. The entries below summarize notable changes after that point.

## 2026-04-16

### Reachability AND-gate and ghost-ARP defense

- Discovery now requires both a fresh TCP/ICMP probe and nmap's ARP-bypass ping to agree the host is up before running a full scan. Eliminates false "device found" results for up to several minutes after a cable is unplugged.
- Manual device creation now runs the same reachability probe and surfaces `reachability_verified` + `probe_source` in the create response and audit log; `last_seen_at` is set only when the probe succeeded.
- Batch scans now pre-filter targets through the same probe and return `skipped_unreachable` so the UI can show how many IPs were dropped.
- `connectivity_probe` tuned: ICMP latency floor lowered to 50μs (was 1 ms, was rejecting legitimate fast-LAN replies); nmap tiebreaker shrunk to top-50 with a 5 s host-timeout so ghost-host cost halves.
- Discovery rate limiting now uses two buckets per client: `DISCOVERY_RATE_LIMIT_PER_MINUTE` (per target scope) and `DISCOVERY_GLOBAL_RATE_LIMIT_PER_MINUTE` (per client, across all targets) to prevent sweep-style abuse.

### Dockerfile and toolchain fixes

- Fixed a broken single-line `FROM ... AS tools-builder # ...RUN git clone` in `server/backend/Dockerfile` that was silently swallowing the testssl.sh clone. Stage 1 produced an empty `/opt/testssl`; downstream TLS tests were running without their tool.
- Added `procps` and `dnsutils` so `testssl.sh` runtime dependencies resolve, plus `libjson-perl` and `libxml-writer-perl` so nikto loads its required Perl modules.

### Test engine hardening

- Generic web-server products (`nginx`, `apache`, `microsoft-iis`, etc.) are no longer written into `device.model` or `device.hostname`. A new word-boundary regex replaces the prior `startswith` match that was falsely catching `nginxcontroller` and similar.
- Device fingerprinter now accepts both legacy and seeded profile key names (`port_hints`, `oui_vendors`, `service_hints`).
- Tools sidecar now allows nmap host-discovery probe flags (`-PE`, `-PP`, `-PM`, `-PS`, `-PA`, `-PU`, `-PY`) with a validated port-suffix regex that blocks shell-injection via the suffix.

### Dependency bumps (safe minor/patch)

- `fastapi` 0.135.3 → 0.136.0
- `pydantic` 2.12.5 → 2.13.1
- `sentry-sdk` 2.57.0 → 2.58.0
- `react-router-dom` 7.14.0 → 7.14.1
- `@sentry/react` 10.48.0 → 10.49.0
- `@tanstack/react-query` 5.97.0 → 5.99.0

### Repo hygiene

- Removed the stale `update.bat` and `update.sh` helpers; the four documented git + docker commands in `ENGINEER_UPDATES.md` are the supported path.
- Removed `GEMINI.md`; consolidated AI-agent guidance into `CLAUDE.md` with `AGENTS.md` as a pointer.
- Refreshed `CLAUDE.md`, `README.md`, and `ENGINEER_UPDATES.md` to reflect the current stack (Python 3.13, PostgreSQL 17, node:24, reachability AND-gate).

### New tests

- `test_discovery_reachability`, `test_discovery_subnet_ghost`, `test_network_scan_batch_ghost`, `test_devices_manual_add_reachability`, `test_nmap_parser_reachability` — regression guards for the reachability and ghost-host paths.

## 2026-04-09

### CI And Quality Fixes

- Fixed CI: upgraded Vite 6.4.1 to 6.4.2 to resolve high-severity CVE (GHSA-p9ff-h696-f583). All three CI jobs now pass.
- Removed hardcoded admin password from docker-compose.yml; now required from `.env`.
- Added 404 catch-all route so unknown paths show a proper "Page not found" instead of a blank page.
- Fixed WCAG accessibility: added `htmlFor`/`id` bindings on login and settings forms.
- Replaced bare `except: pass` blocks with logging across backend services.
- Added frontend tests for TestRunDetailPage, NetworkScanPage, ReportsPage, and ReviewQueuePage.
- Aligned backend test assertions with actual API behavior (refresh token is a cookie, device patch is open to all roles).

## 2026-04-07 To 2026-04-08

### Audit And Reliability

- Resolved all 24 tester-reported issues including DHCP addressing mode support and performance optimizations.
- Increased tools sidecar rate limit from 5 to 30 scans per minute per target.
- Resolved remaining medium-severity audit findings.
- UX improvements: styled modals, form validation with debounce, and accessibility enhancements.
- Resolved 16 audit findings covering security, reliability, and code quality.
- Resolved 16 bug report issues spanning critical fixes, test logic corrections, and UX polish.

## 2026-04-02

### Documentation And Handoff

- Reworked the repo documentation around current behavior instead of historical planning docs.
- Added a dedicated engineer update guide and cleaned up the local verification flow.
- Separated app overview, install flow, deploy guidance, security notes, and change history more clearly.
- Added a dedicated local frontend or backend development guide for running outside the full Docker stack.

### Operations And Release Workflow

- Improved the release and update workflow for local installs.
- Added Windows and shell verification helpers for smoke tests and backend test runs.
- Hardened local network detection with fallback probe behavior.
- Corrected PowerShell smoke checks so tool-sidecar counts reflect the live response shape.

## 2026-03-31

### Test Run Control And Visibility

- Added richer test-run UX with filters, confidence signals, resume handling, and duplicate detection.
- Added process tracking, cancel support, and orphaned-run cleanup.
- Expanded test explanations and explicit skip reasons across the 43-test universal library.

## 2026-03-30

### Security Hardening

- Added and completed multiple security phases covering IDOR prevention, authorization enforcement, per-user rate limiting, audit logging, refresh-token rotation, session revocation, API key rotation, CSP and nginx hardening, sanitized error handling, and stricter CI auditing.
- Added 2FA, optional OIDC/SSO, audit-log retention, monitoring hooks, and Sentry integration points.
- Tightened production configuration handling, CSRF behavior, and secret management.

### Scanning Governance And Network Workflows

- Added authorized networks as an explicit admin gate for subnet scanning.
- Improved network detection, active scan persistence, fallback probes, and richer subnet-discovery results.
- Added clickable discovery results and improved navigation from discovery into device workflows.

### Qualification Workflow And Reporting

- Added smart device profiling, auto-template generation, profile editor support, and automatic device metadata enrichment from test results.
- Added live terminal output streaming, per-device live dashboards, improved run names, and stronger visual run states.
- Improved report generation, branding support, and real-device accuracy fixes.
- Resolved issues affecting zero-result runs, LibreOffice PDF generation, and early production-readiness gaps.

### Deployment And Packaging

- Added a one-command server deployment script and expanded deployment documentation.
- Improved secret generation for packaged and local flows.
- Cleaned up stale files and repository artifacts.

## 2026-03-24 To 2026-03-25

### Product Expansion And UX Refinement

- Added device profiles, scan schedules, CVE lookup, and manufacturer or model auto-detection.
- Added dark mode, keyboard navigation, CSV export, guided-tour polish, and broader layout consistency improvements.
- Applied the Electracom branding overhaul across the app and assets.
- Fixed device creation validation issues, test-run endpoint failures, landing/login flow problems, and other UI stability issues.
- Switched the seeded admin login identity to username `admin`.

## 2026-03-23

### Post-v1 Baseline Cleanup

- Added comprehensive E2E verification coverage for CI and local validation.
- Simplified installation guidance and removed stale development artifacts.
- Started the production-readiness hardening pass that later expanded into the security and operations work above.
