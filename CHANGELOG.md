# Changelog

This is a curated change history for EDQ. It is intentionally grouped by meaningful milestones instead of listing every commit.

The original `EDQ v1.0` baseline is commit `3a85953`. The entries below summarize notable changes after that point.

## 2026-04-02

### Documentation And Handoff

- Reworked the repo documentation around current behavior instead of historical planning docs.
- Added a dedicated engineer update guide and cleaned up the local verification flow.
- Separated app overview, install flow, deploy guidance, security notes, and change history more clearly.

### Operations And Release Workflow

- Improved the release and update workflow for local installs.
- Added Windows and shell verification helpers for smoke tests and backend test runs.
- Hardened local network detection with fallback probe behavior.

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
