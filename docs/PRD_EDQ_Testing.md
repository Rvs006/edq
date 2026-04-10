# EDQ — Product Requirements Document for Automated Testing

**Product:** Electracom Device Qualifier (EDQ)
**Version:** 1.0.0
**Date:** 2026-04-09
**Purpose:** Comprehensive PRD for LambdaTest / KaneAI automated testing

---

## 1. Product Overview

EDQ is a local-first qualification app for smart building IP devices. Engineers discover devices on a network, run 43 automated and manual security checks per device, and generate qualification reports.

**Architecture:** 2-container Docker stack (backend + tools combined, frontend nginx)
**URL:** http://localhost:3000
**Login:** bootstrap credentials are environment-driven. Use the locally configured admin account instead of a hard-coded password.

---

## 2. User Roles

| Role | Access Level |
|------|-------------|
| **engineer** | Own devices/runs only. Cannot manage users, templates, or override verdicts. Sees Workflow + Settings in sidebar. |
| **reviewer** | All engineer access + view all runs, override verdicts, manage templates/whitelists/profiles. Sees Workflow + Setup + Settings. |
| **admin** | Full access. User management, authorized networks, audit logs, system settings. Sees all sidebar sections. |

---

## 3. Pages & Routes

| Route | Page | Role Required | Key Elements to Test |
|-------|------|---------------|---------------------|
| `/login` | Login | Public | Username/email field, password field, visibility toggle, submit button, error toast, OIDC button (if configured) |
| `/` | Dashboard | Any auth | KPI cards (devices, runs, pass rate), recent test runs table, quick action buttons |
| `/projects` | Projects | Any auth | "New Project" button, project cards grid, create modal (name, description, client, location), archive/delete on hover |
| `/devices` | Devices | Any auth | Device list table, search bar, category filter, topology view toggle, "Add Device" button, "Import CSV" button, "Discover" button |
| `/devices/compare` | Compare | Any auth | Side-by-side table, difference highlighting, verdict color coding |
| `/devices/:id` | Device Detail | Any auth | Device info card, open ports list, test history trend chart (SVG), edit fields |
| `/network-scan` | Bulk Discovery | Any auth | CIDR input, "Discover Devices" button, discovered devices list, "Start Scan" button, progress indicators |
| `/test-runs` | Test Runs | Any auth | Test runs table, status badges, filter by status, click to detail |
| `/test-runs/:id` | Test Run Detail | Any auth | 43 test results list, verdict badges, expand test details, override button (reviewer/admin), progress bar, WebSocket live updates |
| `/reports` | Reports | Any auth | Template dropdown, test run selector, "Generate Report" button, download link |
| `/templates` | Templates | Reviewer+ | Template list, create/edit modal, test ID checkboxes, whitelist selector |
| `/test-plans` | Test Plans | Reviewer+ | Plan list, create/edit form |
| `/scan-schedules` | Scan Schedules | Reviewer+ | Schedule list, CRON expression input, enable/disable toggle |
| `/whitelists` | Whitelists | Reviewer+ | Whitelist list, port/protocol entries editor |
| `/device-profiles` | Device Profiles | Reviewer+ | Profile list, fingerprint rules editor |
| `/review` | Review Queue | Admin | Flagged test results, approve/reject actions |
| `/admin` | Users | Admin | User list table, role dropdown, activate/deactivate toggle |
| `/authorized-networks` | Auth Networks | Admin | CIDR subnet list, add/remove |
| `/audit-log` | Audit Log | Admin | Log entries table, filters (action, user, date range), "Export CSV" button |
| `/settings` | Settings | Any auth | Profile tab, Security tab (2FA, password change), Appearance tab (theme toggle), Branding tab (admin only) |

---

## 4. Critical User Journeys

### Journey 1: Engineer Qualification Workflow (HIGHEST PRIORITY)
```
1. Login as engineer
2. Navigate to Projects → Create "London Office" project
3. Navigate to Bulk Discovery → Enter subnet 192.168.1.0/24
4. Click "Discover Devices" → Wait for results
5. Select 3 discovered devices → Click "Start Scan"
6. Monitor progress via live WebSocket updates
7. View completed test run → See 43 test results
8. For manual tests, enter engineer notes and set verdict
9. Submit for review
10. Navigate to Reports → Select test run → Generate Excel report
11. Download report file
```

### Journey 2: Admin User Management
```
1. Login as admin
2. Navigate to Admin (Users)
3. See user list with roles
4. Change an engineer to reviewer role
5. Verify sidebar sections update for that user
6. Navigate to Audit Log → Verify role change is logged
```

### Journey 3: CSV Bulk Import
```
1. Login → Navigate to Devices
2. Click "Import CSV" button
3. Download CSV template
4. Upload CSV with 20 devices
5. Verify preview shows first 5 rows
6. Select project from dropdown
7. Click Import → Verify summary (imported/skipped/errors)
8. Navigate to project → Verify devices appear
```

### Journey 4: Device Comparison
```
1. Navigate to Devices
2. Select 3 devices (checkbox)
3. Click "Compare" 
4. Verify side-by-side table shows all properties
5. Verify differences are highlighted in amber
6. Verify verdict color coding (green/red/gray)
```

### Journey 5: Security Qualification Review
```
1. Login as reviewer
2. Navigate to Review Queue
3. See flagged test results
4. Click on a failing test
5. Override verdict with justification
6. Verify override is recorded with username and timestamp
7. Check audit log for the override action
```

---

## 5. API Endpoints (126 total)

### Authentication (7 endpoints)
| Method | Path | Expected Status | Test Scenario |
|--------|------|----------------|---------------|
| POST | /api/auth/login | 200 (valid), 401 (invalid), 422 (empty) | Valid creds, wrong password, empty fields, locked account |
| POST | /api/auth/logout | 200 | Clears cookies |
| POST | /api/auth/refresh | 200 | Returns new access token |
| GET | /api/auth/me | 200 | Returns current user |
| PATCH | /api/auth/me | 200 | Update name/email |
| POST | /api/auth/register | 201 or 403 | Only if ALLOW_REGISTRATION=true |
| POST | /api/auth/change-password | 200, 400 (weak), 401 (wrong old) | Password complexity validation |

### Devices (11 endpoints)
| Method | Path | Expected Status | Test Scenario |
|--------|------|----------------|---------------|
| GET | /api/devices/ | 200 | List with pagination, search, category filter |
| POST | /api/devices/ | 201, 409 (duplicate IP) | Create device, duplicate IP blocked |
| GET | /api/devices/stats | 200 | Returns counts by status/category |
| GET | /api/devices/compare?ids=a,b | 200, 400 (<2 IDs) | Side-by-side comparison |
| POST | /api/devices/import | 201, 422 (bad CSV) | CSV upload with validation |
| GET | /api/devices/export | 200 | CSV streaming download |
| GET | /api/devices/{id} | 200, 404 | Single device |
| PATCH | /api/devices/{id} | 200 | Update fields |
| DELETE | /api/devices/{id} | 204 | Admin only |
| POST | /api/devices/{id}/discover-ip | 200 | ARP scan for DHCP devices |
| GET | /api/devices/{id}/trends | 200 | Historical pass rates |

### Projects (6 endpoints)
| Method | Path | Expected Status | Test Scenario |
|--------|------|----------------|---------------|
| GET | /api/projects/ | 200 | List with status filter |
| POST | /api/projects/ | 201 | Create with name, client, location |
| GET | /api/projects/{id} | 200, 404 | Get with device/run counts |
| PATCH | /api/projects/{id} | 200 | Update name, status, archive |
| DELETE | /api/projects/{id} | 204 | Unlinks devices (doesn't delete them) |
| POST | /api/projects/{id}/devices | 200 | Bulk-add device IDs |

### Test Runs (15 endpoints)
| Method | Path | Expected Status | Test Scenario |
|--------|------|----------------|---------------|
| GET | /api/test-runs/ | 200 | Engineers see only own runs |
| POST | /api/test-runs/ | 201 | Create with device + template |
| POST | /api/test-runs/{id}/start | 200 | Launches automated tests |
| POST | /api/test-runs/{id}/pause | 200 | Pauses running tests |
| POST | /api/test-runs/{id}/resume | 200 | Resumes paused tests |
| POST | /api/test-runs/{id}/cancel | 200 | Cancels and cleans up |
| POST | /api/test-runs/{id}/complete | 200 | Calculates final verdict |
| GET | /api/test-runs/{id} | 200 | Full run with device/template info |

### Health & Metrics (4 endpoints)
| Method | Path | Expected Status | Test Scenario |
|--------|------|----------------|---------------|
| GET | /api/health/ | 200 | No auth required, returns {status, database} |
| GET | /api/health/metrics | 200 | Prometheus format text |
| GET | /api/health/tools/versions | 200 | Auth required, tool versions |
| GET | /api/health/system-status | 200 | Auth required, full status |

---

## 6. Security Test Scenarios

### Authentication Security
| # | Test | Steps | Expected |
|---|------|-------|----------|
| S1 | Account lockout | 5 failed logins with wrong password | 401 on 6th attempt (locked for 15 min) |
| S2 | CSRF protection | POST to /api/devices without X-CSRF-Token header | 403 "CSRF token missing" |
| S3 | Session expiry | Wait 60+ minutes, make authenticated request | 401, must re-login |
| S4 | Token refresh | After access token expires, POST /api/auth/refresh | 200 with new token |
| S5 | Logout clears session | POST /api/auth/logout, then GET /api/devices | 401 Unauthorized |
| S6 | Password complexity | Register/change password with "123" | 422 validation error |

### Input Validation
| # | Test | Input | Expected |
|---|------|-------|----------|
| S7 | SQL injection in login | username: `' OR 1=1--` | 401 (not 500) |
| S8 | XSS in device name | hostname: `<script>alert(1)</script>` | Sanitized (tags stripped) |
| S9 | Path traversal | GET /../../etc/passwd | 200 (SPA fallback, not file content) |
| S10 | Invalid IP address | Create device with ip: "999.999.999.999" | 422 validation error |
| S11 | Invalid MAC format | Create device with mac: "ZZZZ" | 422 validation error |
| S12 | Large file upload | Import 10MB CSV | 413 or 422 (max 2MB) |
| S13 | Empty CSV import | Upload empty .csv file | 400 "No data rows" |

### Authorization (IDOR)
| # | Test | Steps | Expected |
|---|------|-------|----------|
| S14 | Engineer views other's run | Login as engineer A, GET /api/test-runs/{engineer_B_run_id} | 403 Forbidden |
| S15 | Engineer deletes device | Login as engineer, DELETE /api/devices/{id} | 403 (admin only) |
| S16 | Engineer overrides verdict | Login as engineer, POST override on test result | 403 (reviewer+ only) |
| S17 | Engineer accesses admin | Login as engineer, GET /api/users/ | 403 (admin only) |

### Security Headers
| # | Header | Expected Value | Check On |
|---|--------|---------------|----------|
| S18 | X-Content-Type-Options | nosniff | All responses |
| S19 | X-Frame-Options | DENY | All responses |
| S20 | Content-Security-Policy | default-src 'self'... | Frontend / route |
| S21 | Referrer-Policy | strict-origin-when-cross-origin | All responses |
| S22 | X-Request-ID | UUID format | All API responses |
| S23 | Cache-Control | no-store (mutations), public max-age=30 (health) | API responses |

### Rate Limiting
| # | Endpoint | Limit | Test |
|---|----------|-------|------|
| S24 | /api/auth/login | 15/min | 16 rapid requests → 429 |
| S25 | /api/devices/import | 5/min | 6 rapid uploads → 429 |
| S26 | /api/reports/generate | 5/min | 6 rapid generates → 429 |
| S27 | /api/network-scan/discover | 3/min | 4 rapid discovers → 429 |

---

## 7. Edge Cases & Error Scenarios

### Data Edge Cases
| # | Scenario | Steps | Expected |
|---|----------|-------|----------|
| E1 | Empty database | Fresh install, navigate all pages | All pages show "empty state" UI, no crashes |
| E2 | Unicode in project name | Create project with name "日本語テスト 🏢" | Saves and displays correctly |
| E3 | Very long device name | 500-character hostname | Truncated in UI, saved in DB |
| E4 | Duplicate device IP | Create 2 devices with same IP | 409 Conflict on second create |
| E5 | Delete project with devices | Delete project that has 10 devices | Devices unlinked (project_id=null), not deleted |
| E6 | Cancel mid-scan | Start network scan, immediately cancel | Scan stopped, partial results saved |
| E7 | 500 device CSV import | Upload CSV with 500 valid rows | All imported, summary shows 500/0/0 |
| E8 | 501 device CSV import | Upload CSV with 501 rows | Error: "Maximum 500 rows" |
| E9 | CSV with mixed valid/invalid | 10 valid + 5 invalid IPs | 10 imported, 0 skipped, 5 errors with line numbers |
| E10 | Compare 1 device | Navigate to /devices/compare?ids=one-id | Error: "Select at least 2 devices" |
| E11 | Compare 6 devices | compare?ids=1,2,3,4,5,6 | Error: "Maximum 5 devices" |
| E12 | Device with no test runs | View /devices/{id}/trends for untested device | Empty state: "No test history yet" |
| E13 | Concurrent test runs | Start 10 test runs simultaneously | All run without crashing (10 concurrent tool limit) |

### UI/UX Edge Cases
| # | Scenario | Expected |
|---|----------|----------|
| E14 | Mobile viewport (375px) | Sidebar collapsed, hamburger menu, responsive cards |
| E15 | Tablet viewport (768px) | Sidebar collapsed, 2-column grid |
| E16 | Dark mode toggle | All pages render correctly in dark mode |
| E17 | Browser back button | Navigation works, no blank screens |
| E18 | Multiple tabs | Both tabs stay authenticated |
| E19 | Page refresh on /devices | Data reloads, no crash |
| E20 | Network disconnect | Error toast, retry on reconnect |
| E21 | Slow API response | Loading spinners shown, no UI freeze |
| E22 | Sidebar collapse/expand | Setup and Admin sections toggle smoothly |
| E23 | Search bar (Enter) | Navigates to /devices with search query |
| E24 | WebSocket disconnect | Reconnect automatically, resume progress |

---

## 8. Test Templates (5 seeded)

| Template | Tests | Purpose |
|----------|-------|---------|
| Full Security Assessment | All 60 tests | Complete qualification suite |
| Essential Tests Only | 12 essential tests | Minimum for qualification |
| Pelco Camera Assessment | All 60 tests | Camera-specific report format |
| EasyIO Controller Assessment | All 60 tests | Controller-specific report format |
| Extended Qualification (Dylan) | All 60 tests | Matches Electracom Excel template |

---

## 9. Database Schema (22 tables)

### Core Tables
- `users` — accounts with role, lockout, 2FA, OIDC
- `devices` — IP devices with MAC, ports, fingerprint, project_id
- `projects` — organizational folders with client/location
- `test_runs` — qualification sessions (43 checks per device)
- `test_results` — individual test outcomes with overrides
- `test_templates` — reusable test configurations

### Supporting Tables
- `device_profiles` — fingerprint rules for auto-classification
- `protocol_whitelists` — approved port/protocol lists
- `network_scans` — subnet discovery sessions
- `scan_schedules` — recurring scan cron jobs
- `authorized_networks` — allowed scan subnets
- `audit_logs` — full action history
- `report_configs` — report generation settings
- `agents` — distributed test runners
- `refresh_tokens` — JWT refresh token tracking
- `attachments` — uploaded evidence files
- `nessus_findings` — imported vulnerability scan results
- `branding_settings` — logo, colors, company name
- `test_plans` — reusable test configurations
- `sync_queue` — offline sync queue
- `alembic_version` — migration tracking

---

## 10. Automated Security Tests (29)

| ID | Name | Tool | What It Tests |
|----|------|------|--------------|
| U01 | Ping Response | nmap -sn | Device reachability |
| U02 | MAC Address Lookup | nmap | OUI vendor identification |
| U03 | IPv6 Support | nmap -6 | IPv6 stack detection |
| U04 | Open Port Scan | nmap -sV --top-ports 20 | Service discovery |
| U05 | DHCP Behaviour | DHCP probe | Accepts DHCP lease |
| U06 | Full TCP Port Scan | nmap -p 1-65535 | All open ports |
| U07 | UDP Port Scan | nmap -sU --top-ports 50 | UDP services |
| U08 | Service Fingerprint | nmap -sV | Version detection |
| U09 | Whitelist Compliance | nmap + whitelist | Ports vs approved list |
| U10 | TLS Version Assessment | testssl.sh | TLS 1.2+ check |
| U11 | Cipher Suite | testssl.sh | Weak cipher detection |
| U12 | Certificate Validity | testssl.sh | Expiry, chain, CN |
| U13 | HSTS Check | testssl.sh | HSTS header |
| U14 | HTTP Security Headers | nikto/curl | CSP, X-Frame, etc. |
| U15 | SSH Algorithm Assessment | ssh-audit | Key exchange, ciphers |
| U16 | Default Credential Check | hydra | Common default passwords |
| U17 | Brute Force Resistance | hydra | Account lockout behavior |
| U18 | HTTP→HTTPS Redirect | curl | Enforced HTTPS |
| U19 | OS Fingerprint | nmap -O | Operating system detection |
| U26 | NTP Synchronisation | nmap -sU -p123 | NTP service check |
| U28 | SNMP Version Check | nmap | SNMPv3 only |
| U29 | UPnP/SSDP Detection | nmap -sU -p1900 | UPnP exposure |
| U31 | DNS Exposure | nmap -sU -p53 | DNS service check |
| U32 | mDNS Detection | nmap -sU -p5353 | mDNS exposure |
| U33 | RTSP Stream Detection | nmap -p554 | RTSP exposure |
| U34 | Telnet Detection | nmap -p23 | Insecure protocol |
| U35 | Web Vulnerability Scan | nikto | Known vulnerabilities |
| U36 | Modbus Detection | nmap -p502 | Industrial protocol exposure |
| U37 | BACnet Detection | nmap -sU -p47808 | Building automation protocol |

---

## 11. Performance Benchmarks

| Metric | Target | Actual |
|--------|--------|--------|
| Health API response | <50ms | 5ms |
| Frontend page load | <100ms | 2ms |
| Authenticated API response | <100ms | <20ms |
| Concurrent API requests (20) | All 200 | All 200 |
| Gzip compression | Active | Active |
| Static asset caching | 1 year immutable | 1 year immutable |
| Docker memory (backend) | <2GB | 157MB |
| Docker memory (frontend) | <512MB | 11MB |

---

## 12. WebSocket Events

### Test Run Progress (`ws://localhost:3000/ws/test-run/{run_id}`)
```json
{
  "type": "test_progress",
  "test_id": "U01",
  "test_name": "Ping Response",
  "verdict": "pass",
  "progress_pct": 15.5,
  "completed_tests": 3,
  "total_tests": 43
}
```

### Network Scan Progress (`ws://localhost:3000/ws/discovery/{task_id}`)
```json
{
  "type": "scan_progress",
  "phase": "discovering",
  "hosts_found": 12,
  "status": "scanning"
}
```

---

## 13. Compliance Frameworks

| Framework | Tests Mapped | Coverage |
|-----------|-------------|----------|
| ISO 27001 | 27 tests | Network security, access control, encryption |
| Cyber Essentials | 9 tests | Firewalls, secure configuration, access control |
| SOC2 | 6 tests | Access control, encryption, monitoring |

---

## 14. Environment Configuration

| Variable | Purpose | Default |
|----------|---------|---------|
| DATABASE_URL | Database connection | sqlite+aiosqlite:///./data/edq.db |
| JWT_SECRET | Access token signing | (required) |
| JWT_REFRESH_SECRET | Refresh token signing | (required) |
| TOOLS_API_KEY | Backend ↔ tools sidecar auth | (required) |
| INITIAL_ADMIN_PASSWORD | First admin account | (required) |
| COOKIE_SECURE | HTTPS-only cookies | false (local), true (prod) |
| ALLOW_REGISTRATION | Public signup | false |
| CORS_ORIGINS | Allowed origins | ["http://localhost","http://localhost:3000"] |
| SENTRY_DSN | Error tracking | (optional) |
| REDIS_URL | Distributed rate limiting | (optional) |

---

*Generated for LambdaTest / KaneAI automated testing. Covers all 126 API endpoints, 21 pages, 60 security tests, 22 database tables, and comprehensive edge cases.*
