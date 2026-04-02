# EDQ Engineering Specification

> Archived reference only.
>
> This document reflects an earlier planning state and is not the current setup,
> deployment, or API guide for this repository. Use `README.md`, `INSTALL.md`,
> `DEPLOY.md`, `SECURITY.md`, and `docs/README.md` for current guidance.

## CRITICAL: READ THIS ENTIRE FILE BEFORE WRITING ANY CODE

This is a historical technical specification preserved for context. It is not the
current operational guide for the running repository.

**Last Updated:** March 2026
**Status:** Production — V1.0
**Company:** Electracom Projects Ltd (a Sauter Group Company)

---

## 1. WHAT EDQ IS (60-Second Summary)

EDQ is a web app that automates cybersecurity qualification testing for smart building IP devices (cameras, HVAC controllers, intercoms, IoT sensors). It replaces a manual process where a security engineer (Dylan) currently spends a FULL WORKING DAY per device running terminal commands (nmap, testssl.sh, ssh-audit, hydra), manually typing results into Excel spreadsheets, and hand-writing Word reports.

EDQ reduces this to 1–2 hours by:
1. Auto-discovering and fingerprinting the connected device
2. Running 60–65% of security tests automatically
3. Presenting remaining manual tests as structured single-click forms (not free-text)
4. Generating pixel-perfect Excel/Word reports matching existing Electracom client formats

**Key Constraint:** Runs entirely offline on a test laptop via Docker. No cloud dependency. No internet required for testing.

---

## 2. ARCHITECTURE (What You Are Building)

```
┌─────────────────────────────────────────────────────────┐
│  DOCKER COMPOSE (runs on engineer's Windows/Mac laptop) │
│                                                          │
│  ┌──────────┐   ┌──────────┐   ┌────────────────────┐  │
│  │  NGINX   │   │ FASTAPI  │   │   TOOLS SIDECAR    │  │
│  │ (port 80)│──▶│ BACKEND  │──▶│  (nmap, testssl,   │  │
│  │  serves  │   │ (port    │   │   ssh-audit, hydra, │  │
│  │  React   │   │  8000)   │   │   nikto)            │  │
│  │  SPA     │   │          │   │  (port 8001)        │  │
│  └──────────┘   └────┬─────┘   └────────────────────┘  │
│                      │                                   │
│                 ┌────┴─────┐                              │
│                 │  SQLite  │                              │
│                 │  /data/  │                              │
│                 │  edq.db  │                              │
│                 └──────────┘                              │
└─────────────────────────────────────────────────────────┘
         │ Cat6 Ethernet cable
    ┌────┴────────┐
    │   DEVICE    │  (Pelco camera, EasyIO controller, etc.)
    │  UNDER TEST │
    └─────────────┘
```

### 2.1 Three Docker Services

| Service | Base Image | Port | Purpose |
| --- | --- | --- | --- |
| `frontend` | node:18 → nginx:alpine | 80 | Serves React SPA, proxies /api/* and /ws/* to backend |
| `api` | python:3.12-slim | 8000 | FastAPI backend: auth, API, WebSocket, database, reports |
| `tools` | ubuntu:22.04 | 8001 | Security scanning tools with REST API wrapper |

### 2.2 Tools Sidecar API

The tools container exposes a simple REST API that the backend calls:

```
GET  /health                    → {"status": "healthy", "tools": {"nmap": true, ...}}
POST /scan/nmap                 → Runs nmap with provided args, returns XML output
POST /scan/testssl              → Runs testssl.sh, returns JSON output  
POST /scan/ssh-audit            → Runs ssh-audit, returns JSON output
POST /scan/hydra                → Runs hydra, returns stdout
POST /scan/nikto                → Runs nikto, returns stdout
```

Each endpoint accepts:
```json
{
  "target": "192.168.1.100",
  "args": ["-sV", "-O", "-p-"],
  "timeout": 300
}
```

And returns:
```json
{
  "exit_code": 0,
  "stdout": "...",
  "stderr": "...",
  "output_file": "base64-encoded XML/JSON if applicable",
  "duration_seconds": 45.2
}
```

### 2.3 Docker Networking

**CRITICAL:** The tools sidecar needs `network_mode: host` (or `NET_ADMIN` + `NET_RAW` capabilities) to scan devices on the host's network. The backend communicates with the tools sidecar via Docker's internal network. The frontend nginx proxies everything.

```yaml
# docker-compose.yml structure
services:
  frontend:
    build: ./frontend
    ports: ["80:80"]
    depends_on: [api]
    
  api:
    build: ./backend
    ports: ["8000:8000"]
    volumes:
      - ./data:/data
      - ./templates:/app/templates
    environment:
      - DATABASE_URL=sqlite:///data/edq.db
      - TOOLS_SIDECAR_URL=http://tools:8001
      - JWT_SECRET=${JWT_SECRET}
      
  tools:
    build: ./tools
    ports: ["8001:8001"]
    cap_add: [NET_ADMIN, NET_RAW]
    network_mode: host  # Required for Layer 2 scanning
```

---

## 3. DATABASE SCHEMA (11 Tables)

Use SQLAlchemy 2.0 ORM with SQLite. All IDs are UUID v4 strings.

### 3.1 users
```sql
CREATE TABLE users (
    id TEXT PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    full_name TEXT NOT NULL,
    password_hash TEXT NOT NULL,          -- bcrypt, cost factor 12
    role TEXT NOT NULL CHECK (role IN ('admin', 'tester', 'reviewer')),
    is_active BOOLEAN NOT NULL DEFAULT 1,
    last_login TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

### 3.2 devices
```sql
CREATE TABLE devices (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    ip_address TEXT NOT NULL,
    mac_address TEXT,
    vendor TEXT,
    manufacturer TEXT,
    model TEXT,
    firmware_version TEXT,
    serial_number TEXT,
    device_category TEXT NOT NULL DEFAULT 'generic',
    fingerprint JSON,                     -- Full discovery results
    template_id TEXT REFERENCES test_templates(id),
    profile_id TEXT REFERENCES device_profiles(id),
    created_by TEXT NOT NULL REFERENCES users(id),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMP
);
```

### 3.3 device_profiles
```sql
CREATE TABLE device_profiles (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT NOT NULL UNIQUE,        -- camera, controller, intercom, iot_sensor, generic
    description TEXT,
    detection_rules JSON NOT NULL,        -- Rules for auto-detection
    additional_tests JSON NOT NULL,       -- Profile-specific test definitions
    scan_policy JSON NOT NULL DEFAULT '{"intensity": "safe", "nmap_rate_limit": "--max-rate 200"}',
    is_active BOOLEAN NOT NULL DEFAULT 1,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

### 3.4 test_templates
```sql
CREATE TABLE test_templates (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    version TEXT NOT NULL,
    device_category TEXT,
    manufacturer_match TEXT,
    description TEXT,
    source_xlsx_path TEXT,
    source_xlsx_hash TEXT,
    test_definitions JSON NOT NULL,       -- Array of test definition objects
    cell_mappings JSON,                   -- Maps test_number → Excel cell coordinates
    is_active BOOLEAN NOT NULL DEFAULT 1,
    created_by TEXT REFERENCES users(id),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

### 3.5 test_runs
```sql
CREATE TABLE test_runs (
    id TEXT PRIMARY KEY,
    device_id TEXT NOT NULL REFERENCES devices(id),
    user_id TEXT NOT NULL REFERENCES users(id),
    template_id TEXT NOT NULL REFERENCES test_templates(id),
    template_version TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'discovering', 'running', 'paused_manual',
                          'paused_cable', 'awaiting_review', 'complete', 'error')),
    start_time TIMESTAMP,
    end_time TIMESTAMP,
    overall_verdict TEXT CHECK (overall_verdict IN ('pass', 'fail', 'advisory', 'incomplete')),
    synopsis_text TEXT,
    synopsis_ai_draft TEXT,
    synopsis_ai_drafted BOOLEAN NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

### 3.6 test_results
```sql
CREATE TABLE test_results (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES test_runs(id),
    test_number TEXT NOT NULL,            -- e.g. "1", "16.1", "16.2"
    test_name TEXT NOT NULL,
    tier TEXT NOT NULL CHECK (tier IN ('automatic', 'guided_manual', 'auto_na')),
    tool_used TEXT,                        -- nmap, testssl, ssh-audit, hydra, manual
    tool_command TEXT,                     -- Exact command executed
    raw_stdout TEXT,                       -- Full tool output
    raw_stderr TEXT,
    parsed_findings JSON,                 -- Structured parsed results
    verdict TEXT CHECK (verdict IN ('pass', 'fail', 'advisory', 'info', 'n/a', 'pending')),
    auto_comment TEXT,                    -- Auto-generated test comment
    engineer_selection TEXT,              -- Manual test: engineer's selection
    engineer_notes TEXT,                  -- Manual test: free-text notes
    is_overridden BOOLEAN NOT NULL DEFAULT 0,
    override_reason TEXT,
    overridden_by TEXT REFERENCES users(id),
    script_flag TEXT DEFAULT 'No',        -- "Yes" or "No" — whether test was automated
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

### 3.7 attachments
```sql
CREATE TABLE attachments (
    id TEXT PRIMARY KEY,
    result_id TEXT NOT NULL REFERENCES test_results(id),
    file_name TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    file_path TEXT NOT NULL,
    file_size_bytes INTEGER,
    sha256_hash TEXT,
    upload_time TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

### 3.8 protocol_whitelists
```sql
CREATE TABLE protocol_whitelists (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    protocols JSON NOT NULL,              -- Array of {protocol, connection, port} objects
    is_default BOOLEAN NOT NULL DEFAULT 0,
    created_by TEXT REFERENCES users(id),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

### 3.9 report_configs
```sql
CREATE TABLE report_configs (
    id TEXT PRIMARY KEY,
    client_name TEXT,
    logo_path TEXT,
    compliance_standards JSON,
    branding_colours JSON,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

### 3.10 audit_logs
```sql
CREATE TABLE audit_logs (
    id TEXT PRIMARY KEY,
    timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    user_id TEXT REFERENCES users(id),
    action TEXT NOT NULL,
    resource_type TEXT,
    resource_id TEXT,
    ip_address TEXT,
    details JSON
);
```

### 3.11 nessus_findings
```sql
CREATE TABLE nessus_findings (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES test_runs(id),
    plugin_id INTEGER NOT NULL,
    plugin_name TEXT NOT NULL,
    severity TEXT NOT NULL,               -- critical, high, medium, low, info
    risk_factor TEXT,
    description TEXT,
    solution TEXT,
    port INTEGER,
    protocol TEXT,
    plugin_output TEXT,
    cvss_score REAL,
    cve_ids JSON,
    imported_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

---

## 4. THREE TEST TEMPLATE FORMATS

EDQ must support three distinct Excel template formats. The generated reports must be PIXEL-PERFECT matches to the originals.

### 4.1 Pelco Camera Format (31 tests)

Source: `templates/1TS__Pelco_SMLE115V53H_Camera_Device_Qualification_Rev_2.xlsx`
Sheets: TEST SYNOPSIS, TESTPLAN, ADDITIONAL INFO

TESTPLAN columns (starting row 12):
| Column | Content |
| --- | --- |
| B | Test Number (integer: 1, 2, 3... or decimal: 16.1, 16.2) |
| C | Brief Description |
| D | Test Description |
| E | Essential Pass (YES/NO) |
| F | Test Result (PASS/FAIL/ADVISORY/N/A) |
| G | Test Comments |
| H | Script? (Yes/No) |

TEST SYNOPSIS metadata cells:
| Cell | Content |
| --- | --- |
| G7 | Test Attempt number |
| G8 | Date range "DD/MM/YYYY - DD/MM/YYYY" |
| G9 | System (e.g. "Security") |
| G11 | Manufacturer |
| G12 | Model |
| G13 | Firmware Version |
| G14 | Serial Number |
| G15 | Name of Tester |
| G16 | TEST RESULT (overall: PASS/FAIL/ADVISORY) |
| B19 | Synopsis text (multi-paragraph narrative) |

### 4.2 EasyIO Controller Format (46 tests)

Source: `templates/EasyIO_FW08__Device_Testing_Plan__v1_1.xlsx`
Sheets: Synopsis, Protocol Whitelist, 01 Test - Questions, 01 Test - Nessus

01 Test - Questions columns (starting row 13):
| Column | Content |
| --- | --- |
| B | Test # (text with non-breaking spaces: "1\xa0", "2\xa0") |
| C | Test Description (full description, not brief) |
| D | Essential Pass (YES/NO/INFO with trailing \xa0) |
| E | Pass, Fail, Info, N/A |
| F | Notes |
| G | Script? (Yes/No) |

**DIFFERENCES FROM PELCO:** Uses "INFO" as a verdict type. Uses "Notes" instead of "Test Comments". No separate "Brief Description" column. Test numbers have trailing non-breaking spaces. Essential Pass values have trailing non-breaking spaces.

Protocol Whitelist sheet (starting row 8):
| Column | Content |
| --- | --- |
| B | Item number |
| C | Protocol name and RFC reference |
| D | Connection type (TCP/UDP/TCP+UDP) |
| E | IANA Assigned Port |

### 4.3 Generic Template Format (43 tests)

Source: `templates/MANUFACTURER__MODEL__IP_Device_Qualification_Template_C00__ADDED_SCRIPT_NO_YES_1.xlsx`
Sheets: TEST SUMMARY, TESTPLAN, ADDITIONAL INFORMATION

TESTPLAN columns (starting row 10):
| Column | Content |
| --- | --- |
| B | Test Number |
| C | Brief Description |
| D | Test Description |
| E | Script? (Yes/No) — NOTE: different column position vs Pelco! |
| F | Essential Pass |
| G | Test Result |
| H | Test Comments |

**DIFFERENCES:** Column E is Script? (in Pelco it's Essential Pass). Column F is Essential Pass (in Pelco it's Test Result). Some Essential Pass values are conditional: "YES (IoT GATEWAYS ONLY)".

### 4.4 Cell Mapping Strategy

Create JSON cell mapping files for each template that define EXACTLY where each piece of data goes:

```json
{
  "template_name": "pelco_camera_rev2",
  "synopsis_sheet": "TEST SYNOPSIS",
  "testplan_sheet": "TESTPLAN",
  "additional_sheet": "ADDITIONAL INFO",
  "metadata_cells": {
    "test_attempt": "G7",
    "date_range": "G8",
    "system": "G9",
    "manufacturer": "G11",
    "model": "G12",
    "firmware": "G13",
    "serial": "G14",
    "tester_name": "G15",
    "overall_result": "G16",
    "synopsis_text": "B19"
  },
  "testplan_start_row": 13,
  "testplan_columns": {
    "test_number": "B",
    "brief_description": "C",
    "test_description": "D",
    "essential_pass": "E",
    "test_result": "F",
    "test_comments": "G",
    "script_flag": "H"
  }
}
```

**CRITICAL:** The report generator must open the ACTUAL .xlsx template file (not create from scratch), fill in cells, and save. This preserves all formatting, merged cells, borders, colours, conditional formatting, and logos.

---

## 5. UNIVERSAL TEST LIBRARY (30 Tests)

These 30 tests apply to ANY IP device. Additional device-specific tests come from templates.

### 5.1 Automatic Tests (Tool-Executed)

| ID | Name | Tool | What It Does | Pass Criteria |
| --- | --- | --- | --- | --- |
| U01 | Ping Response | nmap -sn | Verify device responds to ICMP | Reply received |
| U02 | MAC Vendor Lookup | nmap + OUI DB | Identify manufacturer from MAC | MAC registered to known vendor |
| U03 | Switch Negotiation | ethtool / nmap | Check speed/duplex | Full duplex, auto-negotiates |
| U04 | DHCP Behaviour | discovery metadata | Check DHCP address acceptance | Device accepts DHCP lease |
| U05 | IPv6 Support | nmap -6 | Detect IPv6 capability | Informational (no pass/fail) |
| U06 | Full TCP Port Scan | nmap -sS -p- | Scan all 65535 TCP ports | Returns open port list |
| U07 | UDP Top-100 Scan | nmap -sU --top-ports 100 | Scan common UDP ports | Returns open port list |
| U08 | Service Detection | nmap -sV | Identify services on open ports | Services identified |
| U09 | Protocol Whitelist | custom rules | Compare open ports vs allowed list | All ports on whitelist |
| U10 | TLS Version | testssl.sh / sslyze | Check TLS versions supported | TLS 1.2+ only |
| U11 | Cipher Suites | testssl.sh / sslyze | List and rate cipher suites | No weak ciphers |
| U12 | Certificate Validity | testssl.sh / sslyze | Check cert expiry and chain | Valid, not expired |
| U13 | HSTS Header | testssl.sh / curl | Check HSTS header presence | HSTS present |
| U14 | HTTP Security Headers | nikto / curl | Check CSP, X-Content-Type, etc. | Key headers present |
| U15 | SSH Algorithms | ssh-audit | Assess SSH config | No weak algorithms |
| U16 | Default Credentials | hydra | Try manufacturer defaults | Defaults changed |
| U17 | Brute Force Protection | custom | Rapid login attempts | Lockout after N failures |
| U18 | HTTP→HTTPS Redirect | curl -L | Check unencrypted access | HTTP disabled or redirects |
| U19 | OS Fingerprinting | nmap -O | Identify operating system | Informational |

### 5.2 Guided Manual Tests (Human-Assisted)

| ID | Name | What Engineer Does | Input Type |
| --- | --- | --- | --- |
| U20 | Network Disconnection | Toggle cable, observe recovery | Single-click: Pass/Fail/N/A + notes |
| U21 | Password Change | Change default password via web UI | Single-click: Pass/Fail + notes |
| U22 | Firmware Update | Check update mechanism | Single-click: Pass/Fail/Info + notes |
| U23 | Session Timeout | Wait for inactivity logout | Single-click: Pass/Fail + notes |
| U24 | Physical Security | Check for reset buttons, USB ports | Single-click: Pass/Fail/Info + notes |
| U25 | VLAN Isolation | Test VLAN tagging support | Single-click: Pass/Fail/N/A + notes |
| U26 | Multicast Traffic | Monitor broadcast/multicast output | Single-click: Info + notes |
| U27 | API Authentication | Check API endpoints require auth | Single-click: Pass/Fail/N/A + notes |
| U28 | Audit Trail | Review device logs | Single-click: Pass/Fail/Info + notes |
| U29 | Data-at-Rest Encryption | Check storage encryption | Single-click: Pass/Fail/Info + notes |
| U30 | Vendor Support / EOL | Check manufacturer support status | Single-click: Pass/Fail/Info + notes |

---

## 6. API ENDPOINTS (Complete List)

### 6.1 Authentication
```
POST /api/auth/login          → {email, password} → Set httpOnly cookie + CSRF token
POST /api/auth/logout         → Clear cookies
POST /api/auth/register       → {email, full_name, password, role} (admin only)
GET  /api/auth/me             → Current user info
POST /api/auth/change-password → {old_password, new_password}
```

### 6.2 Devices
```
GET    /api/devices/                → List all devices (paginated)
POST   /api/devices/               → Create device
GET    /api/devices/{id}           → Device detail
PUT    /api/devices/{id}           → Update device
DELETE /api/devices/{id}           → Soft delete
POST   /api/devices/discover       → Trigger auto-discovery scan
```

### 6.3 Test Templates
```
GET    /api/templates/              → List templates
POST   /api/templates/              → Create template (admin)
GET    /api/templates/{id}          → Template detail
PUT    /api/templates/{id}          → Update template (admin)
GET    /api/templates/library       → Get universal test library (30 tests)
POST   /api/templates/import-xlsx   → Import from Excel file
```

### 6.4 Test Runs
```
GET    /api/runs/                   → List test runs (with filters)
POST   /api/runs/                   → Create new test run
GET    /api/runs/{id}               → Run detail with all results
PUT    /api/runs/{id}               → Update run status
POST   /api/runs/{id}/start         → Begin automated tests
POST   /api/runs/{id}/pause         → Pause execution
POST   /api/runs/{id}/resume        → Resume execution
DELETE /api/runs/{id}               → Cancel/delete run
```

### 6.5 Test Results
```
GET    /api/runs/{run_id}/results           → All results for a run
GET    /api/runs/{run_id}/results/{test_id} → Single result detail
PUT    /api/runs/{run_id}/results/{test_id} → Update result (manual test entry)
POST   /api/runs/{run_id}/results/{test_id}/override → Reviewer override
POST   /api/runs/{run_id}/results/{test_id}/rerun    → Re-execute a test
```

### 6.6 Reports
```
POST   /api/runs/{run_id}/report/excel      → Generate Excel report → returns .xlsx download
POST   /api/runs/{run_id}/report/word       → Generate Word report → returns .docx download
POST   /api/runs/{run_id}/report/pdf        → Generate PDF report → returns .pdf download
GET    /api/runs/{run_id}/report/preview     → Preview report data as JSON
```

### 6.7 Nessus
```
POST   /api/runs/{run_id}/nessus/upload     → Upload .nessus XML file
GET    /api/runs/{run_id}/nessus/findings    → List parsed findings
```

### 6.8 Protocol Whitelists
```
GET    /api/whitelists/                      → List whitelists
POST   /api/whitelists/                      → Create whitelist
GET    /api/whitelists/{id}                  → Whitelist detail
PUT    /api/whitelists/{id}                  → Update whitelist
```

### 6.9 Device Profiles
```
GET    /api/profiles/                        → List profiles
POST   /api/profiles/                        → Create profile (admin)
GET    /api/profiles/{id}                    → Profile detail
PUT    /api/profiles/{id}                    → Update profile (admin)
```

### 6.10 Admin
```
GET    /api/admin/users                      → List users
PUT    /api/admin/users/{id}                 → Update user (role, active)
GET    /api/admin/audit-logs                 → View audit trail
GET    /api/admin/stats                      → Dashboard statistics
```

### 6.11 WebSocket
```
WS /ws/test-run/{run_id}    → Real-time test progress updates
```

WebSocket message format:
```json
{
  "type": "test_progress",
  "data": {
    "test_number": "U06",
    "test_name": "Full TCP Port Scan",
    "status": "running",
    "progress_pct": 45,
    "stdout_line": "Scanning 192.168.1.100 [65535 ports]",
    "elapsed_seconds": 23
  }
}
```

### 6.12 Health
```
GET /api/health              → {"status": "ok", "database": "connected", "tools_sidecar": "healthy"}
```

---

## 7. SECURITY REQUIREMENTS

### 7.1 Authentication
- JWT tokens stored in httpOnly cookies (NEVER localStorage)
- CSRF protection via double-submit cookie pattern
- bcrypt password hashing, cost factor 12
- Session expiry: 24 hours
- Role-based access: admin, tester, reviewer

### 7.2 API Security
- All endpoints require authentication except: POST /api/auth/login, GET /api/health
- Rate limiting: 100 requests/minute per IP for auth endpoints, 1000/minute for others
- Input validation on all endpoints (Pydantic schemas)
- SQL injection prevention via SQLAlchemy ORM (never raw SQL with user input)

### 7.3 Network Security
- nginx adds security headers: X-Content-Type-Options, X-Frame-Options, CSP, HSTS
- CORS restricted to same origin
- File uploads: validate MIME type by magic bytes, max 50MB, only .nessus/.xlsx/.png/.jpg

### 7.4 Terminal Output Sanitisation
- All raw tool output displayed in the UI must be sanitised (strip ANSI codes, escape HTML)
- Never render tool output as raw HTML

---

## 8. FRONTEND SPECIFICATIONS

### 8.1 Tech Stack
- React 18 + Vite
- Tailwind CSS 3 (dark theme: navy/charcoal backgrounds, amber accents)
- Zustand for state management
- React Query (TanStack) for API data fetching
- Axios with httpOnly cookie auth + CSRF
- xterm.js for live terminal output
- Recharts for dashboard statistics
- Lucide React for icons

### 8.2 Pages (8 total)

**1. Login Page** — Centred card, dark background, "EDQ" logo, email/password, amber sign-in button

**2. Dashboard** — Overview cards showing: total devices, active test runs, completed today, tests passed/failed. Recent test sessions as cards with device name, IP, status badge, progress bar.

**3. Devices Page** — Searchable/filterable list of all registered devices. Each device shows: name, IP, manufacturer, model, category badge, last test date, last verdict badge.

**4. Device Detail Page** — Full device info card. List of all test runs for this device. "Start New Test Run" button.

**5. Test Session Page (MOST COMPLEX)** — This is the main testing screen:
  - Device info header (name, IP, firmware, serial, MAC)
  - "Run All Automated" button + "Generate Report" button
  - Progress bar: "X/Y tests complete"
  - Grouped test list with expandable cards:
    - Each card: test number, name, tool badge, status icon, verdict badge
    - Expanded: raw terminal output (xterm.js), parsed findings, verdict, comments
    - For manual tests: structured form with single-click PASS/FAIL/INFO/N/A buttons + notes field
  - Wobbly Cable alert banner (shows when device connectivity lost)
  - Live WebSocket progress updates

**6. Reports Page** — List of generated reports. Generate new report: select test run, choose format (Excel/Word/PDF), download.

**7. Review Page** (reviewer role) — List of test runs awaiting review. Click to see all results, ability to override any verdict with documented justification.

**8. Admin Page** (admin role) — User management, template management, protocol whitelists, device profiles, audit log viewer.

### 8.3 Component Architecture

```
src/
├── App.jsx                    # Routes
├── main.jsx                   # Entry point
├── api/
│   ├── client.js              # Axios instance with CSRF + cookie auth
│   ├── auth.js
│   ├── devices.js
│   ├── runs.js
│   ├── templates.js
│   ├── reports.js
│   └── websocket.js
├── components/
│   ├── layout/
│   │   ├── AppLayout.jsx      # Sidebar + header + main content
│   │   ├── Sidebar.jsx
│   │   └── ProtectedRoute.jsx
│   ├── devices/
│   │   ├── DeviceList.jsx
│   │   ├── DeviceCard.jsx
│   │   └── CreateDeviceModal.jsx
│   ├── testing/
│   │   ├── TestSession.jsx    # Main test view
│   │   ├── TestProgress.jsx
│   │   ├── TestResultCard.jsx
│   │   ├── ManualTestForm.jsx
│   │   ├── LiveTerminal.jsx   # xterm.js wrapper
│   │   ├── WobblyCableAlert.jsx
│   │   └── NessusUpload.jsx
│   ├── reports/
│   │   ├── ReportGenerator.jsx
│   │   └── SynopsisEditor.jsx
│   └── common/
│       ├── StatusBadge.jsx
│       ├── VerdictBadge.jsx
│       └── DataTable.jsx
├── pages/
│   ├── LoginPage.jsx
│   ├── DashboardPage.jsx
│   ├── DevicesPage.jsx
│   ├── DeviceDetailPage.jsx
│   ├── TestSessionPage.jsx
│   ├── ReportsPage.jsx
│   ├── ReviewPage.jsx
│   └── AdminPage.jsx
├── hooks/
│   ├── useAuth.js
│   ├── useWebSocket.js
│   └── useTestSession.js
└── context/
    └── AuthContext.jsx
```

### 8.4 Theme Constants

```javascript
// tailwind.config.js extend
colors: {
  edq: {
    bg: '#0f172a',          // Slate 900 - main background
    surface: '#1e293b',     // Slate 800 - cards, panels
    sidebar: '#0c1524',     // Darker than bg - sidebar
    border: '#334155',      // Slate 700 - borders
    amber: '#f59e0b',       // Amber 500 - primary action
    amberHover: '#d97706',  // Amber 600 - hover
    success: '#22c55e',     // Green 500 - pass
    danger: '#ef4444',      // Red 500 - fail
    warning: '#f59e0b',     // Amber 500 - advisory
    info: '#3b82f6',        // Blue 500 - info
    muted: '#94a3b8',       // Slate 400 - secondary text
  }
}
fontFamily: {
  mono: ['JetBrains Mono', 'Fira Code', 'monospace'],  // Technical data
  sans: ['Inter', 'system-ui', 'sans-serif'],           // UI text
}
```

---

## 9. REPORT GENERATION ENGINE

### 9.1 Excel Report Generator (openpyxl)

**Strategy:** Open the actual template .xlsx file, fill in data cells, save as new file. NEVER create from scratch.

```python
from openpyxl import load_workbook
from pathlib import Path

class ExcelReportGenerator:
    def generate(self, run_id: str, template_path: str, cell_mapping_path: str) -> Path:
        """
        1. Load cell_mapping JSON
        2. Load template .xlsx with openpyxl (keep_vba=False, data_only=False)
        3. Fill metadata cells (synopsis sheet)
        4. Fill test result rows (testplan sheet)
        5. Fill additional info (if applicable)
        6. Save to /data/reports/{run_id}/report.xlsx
        """
        wb = load_workbook(template_path)
        mapping = json.loads(Path(cell_mapping_path).read_text())
        
        # Fill synopsis/summary sheet
        synopsis_ws = wb[mapping["synopsis_sheet"]]
        for field, cell in mapping["metadata_cells"].items():
            synopsis_ws[cell] = get_metadata_value(run, field)
        
        # Fill testplan sheet
        testplan_ws = wb[mapping["testplan_sheet"]]
        cols = mapping["testplan_columns"]
        for i, result in enumerate(test_results):
            row = mapping["testplan_start_row"] + i
            testplan_ws[f"{cols['test_result']}{row}"] = result.verdict.upper()
            testplan_ws[f"{cols['test_comments']}{row}"] = result.auto_comment or result.engineer_notes
            testplan_ws[f"{cols['script_flag']}{row}"] = result.script_flag
        
        output_path = Path(f"/data/reports/{run_id}/report.xlsx")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        wb.save(output_path)
        return output_path
```

### 9.2 Handling Template Differences

The generator MUST handle all three formats correctly. Key differences:

| Feature | Pelco | EasyIO | Generic Template |
| --- | --- | --- | --- |
| Verdict values | PASS/FAIL/ADVISORY/N/A | PASS/FAIL/INFO/N/A | PASS/FAIL/ADVISORY/INFO/N/A |
| Test number format | Integer or decimal | Text with \xa0 suffix | Integer |
| Column order | B:num C:brief D:desc E:essential F:result G:comments H:script | B:num C:desc D:essential E:result F:notes G:script | B:num C:brief D:desc E:script F:essential G:result H:comments |
| Synopsis location | Sheet "TEST SYNOPSIS", cell B19 | Sheet "Synopsis" | Sheet "TEST SUMMARY" |
| Protocol whitelist | None (in this file) | Separate sheet | None |
| Nessus data | In ADDITIONAL INFO | Separate sheet "01 Test - Nessus" | In ADDITIONAL INFORMATION |

---

## 10. WOBBLY CABLE HANDLER

Monitors device connectivity during testing. If the device becomes unreachable (cable disconnected, device rebooted), the handler:

1. Detects loss: ping fails 3 times consecutively
2. Pauses current test execution
3. Sends WebSocket alert to frontend
4. Retries connectivity every 30 seconds
5. After device returns: waits 10 seconds for stability, then resumes
6. After 5 minutes of no connectivity: marks test run as "paused_cable", notifies user

```python
class WobblyCableHandler:
    async def check_connectivity(self, ip: str) -> bool:
        """Ping device, return True if reachable."""
        result = await asyncio.create_subprocess_exec(
            "ping", "-c", "1", "-W", "2", ip,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        await result.wait()
        return result.returncode == 0
    
    async def monitor(self, ip: str, run_id: str):
        """Continuous monitoring during test execution."""
        consecutive_failures = 0
        while self.is_running:
            if await self.check_connectivity(ip):
                consecutive_failures = 0
            else:
                consecutive_failures += 1
                if consecutive_failures >= 3:
                    await self.pause_testing(run_id)
                    await self.notify_frontend(run_id, "cable_disconnected")
                    await self.wait_for_reconnection(ip, run_id)
```

---

## 11. NESSUS IMPORT

Parse .nessus XML files (Tenable vulnerability scan output). Use `defusedxml` for safe parsing.

```python
from defusedxml import ElementTree

class NessusParser:
    def parse(self, nessus_file_path: str) -> list[dict]:
        tree = ElementTree.parse(nessus_file_path)
        findings = []
        for report_host in tree.findall('.//ReportHost'):
            host_ip = report_host.get('name')
            for item in report_host.findall('ReportItem'):
                findings.append({
                    "plugin_id": int(item.get('pluginID')),
                    "plugin_name": item.get('pluginName'),
                    "severity": int(item.get('severity')),  # 0=info, 1=low, 2=med, 3=high, 4=crit
                    "port": int(item.get('port')),
                    "protocol": item.get('protocol'),
                    "description": item.findtext('description', ''),
                    "solution": item.findtext('solution', ''),
                    "risk_factor": item.findtext('risk_factor', ''),
                    "cvss_score": float(item.findtext('cvss_base_score', '0')),
                    "cve_ids": [cve.text for cve in item.findall('cve')],
                    "plugin_output": item.findtext('plugin_output', '')
                })
        return findings
```

---

## 12. SEED DATA

On first run, the database must be seeded with:

1. **Default admin user:** `admin` with the password supplied from the active environment / role: admin
2. **30 universal test definitions** (Section 5)
3. **5 device profiles:** camera, controller, intercom, iot_sensor, generic (with scan policies)
4. **1 default protocol whitelist** (from EasyIO template: sFTP/22, DHCP/68, DNS/53, HTTPS/443, NTP/123, SNMPv3/161, LDAPS/636, FTPS/989-990, MQTTS/8883, BACnet/47808)
5. **3 test templates** with cell mappings for Pelco, EasyIO, and Generic formats

Create `backend/seed_data.py`:
```python
def seed_database():
    """Run once on first startup to populate initial data."""
    # Check if already seeded
    if db.query(User).count() > 0:
        return
    
    # 1. Create admin
    # 2. Load universal tests
    # 3. Create device profiles
    # 4. Create default whitelist
    # 5. Create 3 templates with cell mappings
```

---

## 13. DEVELOPMENT RULES

### 13.1 Code Standards
- Python: type hints on EVERY function, docstrings on classes and public methods
- Python: use `async def` for all route handlers and service methods
- Python: use Pydantic schemas for ALL request/response validation
- JavaScript: functional components only, hooks for state
- NEVER use `console.log` in production code — use proper logging
- NEVER store secrets in code — use environment variables

### 13.2 File Organisation
- One model per file in `models/`
- One router per resource in `routes/`
- Business logic in `services/`, NEVER in routes
- Pydantic schemas in `schemas/`, mirroring models

### 13.3 Error Handling
- All API errors return JSON: `{"detail": "Human-readable error message"}`
- Use FastAPI's HTTPException with appropriate status codes
- Log all errors with traceback
- Never expose internal errors to the user

### 13.4 Git Discipline
- Commit after each completed feature
- Descriptive commit messages: "Add nmap parser with XML output handling"
- Never commit broken code — test before committing

---

## 14. CRITICAL GOTCHAS

1. **Windows line endings:** Docker builds fail with \r\n. Use `.gitattributes`: `* text=auto eol=lf`
2. **SQLite concurrent writes:** Use WAL mode: `PRAGMA journal_mode=WAL;`
3. **openpyxl preserving formulas:** Use `data_only=False` when loading templates
4. **Non-breaking spaces in EasyIO:** Test numbers have `\xa0` — strip before comparing
5. **Docker networking:** Tools sidecar needs `network_mode: host` for scanning
6. **CSRF with cookies:** Frontend must include CSRF token header on every mutation request
7. **WebSocket through nginx:** Need `proxy_set_header Upgrade $http_upgrade;` in nginx.conf
8. **testssl.sh on Windows:** Does NOT work. Use sslyze instead on Windows.
9. **nmap needs root/admin:** Container needs `cap_add: [NET_ADMIN, NET_RAW]`
10. **Template column differences:** Pelco, EasyIO, and Generic templates have DIFFERENT column orders — use cell_mappings JSON, never hardcode

---

## 15. DEFINITION OF DONE

EDQ V1.0 is complete when:

1. ✅ Engineer can log in, create a device, start a test run
2. ✅ All 19 automated tests execute against a real device via tools sidecar
3. ✅ All 11 manual tests present structured forms with single-click verdicts
4. ✅ WebSocket shows real-time progress during automated testing
5. ✅ Wobbly Cable Handler detects and recovers from cable disconnection
6. ✅ Nessus .nessus file can be uploaded and findings parsed
7. ✅ Excel report generates using Pelco template with all cells filled correctly
8. ✅ Excel report generates using EasyIO template with all cells filled correctly
9. ✅ Excel report generates using Generic template with all cells filled correctly
10. ✅ Generated report is pixel-perfect match to manually-created original
11. ✅ Protocol whitelist comparison flags non-compliant ports
12. ✅ Reviewer can override any verdict with documented justification
13. ✅ Audit log records all actions
14. ✅ Docker Compose starts all 3 services with one command
15. ✅ Application works fully offline (no internet required)

---

*END OF EDQ ENGINEERING SPECIFICATION*
