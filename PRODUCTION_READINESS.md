# EDQ Production Readiness

This document is the current go/no-go view for EDQ. It is intentionally direct: passing tests and a clean container scan do not automatically mean the app is ready for unrestricted production use.

## Current Rating

**7.5 / 10 after repository hardening, still requiring operational proof for 8.5-9 / 10.**

EDQ is ready to give to trusted engineers for **controlled testing on authorized private-network IP devices**.

EDQ is not yet a **9/10 production platform** for broad enterprise rollout, internet exposure, or unmanaged scanning against arbitrary networks.

## What Is Ready

- Docker Compose stack starts cleanly with frontend, backend, PostgreSQL, and the co-located tools sidecar.
- Local verification scripts pass against the running stack.
- Backend regression suite passes locally.
- GitHub CI passes on `main`.
- The backend image currently scans clean with Docker Scout for vulnerable packages.
- Dependabot security updates, secret scanning, and push protection are enabled on GitHub.
- CodeQL, container CVE scanning, and nightly full-verification workflows are configured.
- Branch protection requires the named CI jobs plus backend container scanning.
- Auth, refresh-token rotation, CSRF, role checks, 2FA hooks, OIDC hooks, audit logs, and authorized-network gates exist.
- Subnet discovery is blocked until an admin explicitly configures authorized CIDR ranges.
- Report generation and core qualification workflows are implemented.

## What Is Not Ready Enough For Broad Production

- The deployment model is a single Docker Compose host, not high availability.
- Backup and restore are documented, but restore drills still need real operational evidence.
- CI uses targeted backend/frontend tests on every PR; full verification runs on schedule or manual dispatch.
- Real-device scan behavior depends on local network conditions, Docker Desktop networking, host OS, privileges, and device responsiveness.
- Windows direct-Ethernet discovery may need host-scanner mode for reliable ARP/ICMP/TCP behavior.
- The tools sidecar contains active security tools. Misconfigured authorized networks could create operational risk.
- Observability is optional. Sentry/log aggregation must be configured by the deployment owner.
- No formal load, soak, disaster recovery, or multi-engineer concurrency sign-off is documented yet.

## Ship To Engineers?

Yes, for a **pilot**.

Recommended pilot boundary:

- 3 to 5 trusted engineers
- private lab or customer-approved network only
- explicit authorized CIDR ranges configured before scans
- no internet-facing deployment
- daily database backup during the pilot
- collect bugs, scan failures, false positives, and report-quality issues
- keep one admin responsible for approving scan ranges and account access

Do not describe EDQ as ready to test "any IP device" without qualification. It should test devices your team owns, administers, or has written permission to scan.

## Go / No-Go Checklist

Before a wider production rollout:

- Run `.\scripts\verify-app.ps1`
- Run `.\scripts\e2e-test.ps1`
- Run `.\scripts\backend-test.ps1`
- Run `docker scout cves edq-backend:latest`
- Prove backup restore on a separate host
- Configure HTTPS with `COOKIE_SECURE=true`
- Restrict access through VPN or private network controls
- Configure real `CORS_ORIGINS`
- Rotate every placeholder secret
- Configure authorized scan networks
- Enable log collection and incident alerting
- Confirm repository dependency, code, and secret scanning are green
- Run at least one pilot against representative device types
- Complete the release gate in [OPERATIONS_RUNBOOK.md](OPERATIONS_RUNBOOK.md)

## Scale Interpretation

- **1-3:** prototype only
- **4-5:** internal demo or narrow lab validation
- **6-7:** controlled pilot with trusted users
- **8:** production for one controlled environment with operational runbooks
- **9:** production-ready for broader rollout with monitoring, backups, scanning governance, and recovery drills
- **10:** mature multi-environment product with HA, automation, audit evidence, and regular security review

EDQ is currently in the **7-8** band based on repository and CI posture. It reaches **8.5-9** only after restore drills, monitoring, and real-device pilot evidence are completed.
