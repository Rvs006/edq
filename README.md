<div align="center">
  <img src="assets/electracom-logo.png" alt="Electracom" width="400">
  <h1>EDQ — Device Qualifier</h1>
  <p><strong>Automated cybersecurity qualification testing for smart building IP devices</strong></p>
  <p>
    <img src="https://img.shields.io/badge/version-1.0.0-blue" alt="Version">
    <img src="https://img.shields.io/badge/python-3.12-3776AB" alt="Python">
    <img src="https://img.shields.io/badge/react-18-61DAFB" alt="React">
    <img src="https://img.shields.io/badge/docker-compose-2496ED" alt="Docker">
    <img src="https://img.shields.io/badge/license-proprietary-red" alt="License">
  </p>
</div>

---

## Overview

EDQ (Electracom Device Qualifier) automates the security qualification of IP-connected smart building devices — cameras, HVAC controllers, intercoms, access control systems, lighting controllers, and IoT sensors. It is built and maintained by [Electracom Projects Ltd](https://www.electracom.co.uk/), a Sauter Group company that delivers building management and security integration across the UK.

Security engineers at Electracom currently spend a **full working day** per device running terminal commands (`nmap`, `testssl.sh`, `ssh-audit`, `hydra`), manually transcribing results into Excel spreadsheets, and hand-writing Word reports. With 30+ devices per month across 10 engineers, this is unsustainable. EDQ reduces each qualification to **1–2 hours** by automating 60–65% of tests, presenting the remaining manual tests as structured single-click forms, and generating pixel-perfect reports that match Electracom's existing client deliverable formats.

---

## Key Features

### 🔍 43 Security Tests

EDQ runs 43 security tests organised into two categories, each mapped to ISO 27001, Cyber Essentials, and SOC2 controls.

**28 Automated Tests** — executed automatically via industry-standard tools:

| Test | Tool | What It Checks |
|------|------|----------------|
| TCP Port Scan | nmap | All 65,535 TCP ports for open services |
| UDP Scan | nmap | Top 100 UDP ports |
| Service Detection | nmap | Identify services and versions on open ports |
| OS Fingerprinting | nmap | Identify the device operating system |
| TLS Assessment | testssl.sh | TLS versions, cipher suites, certificate validity |
| HSTS Header | testssl.sh | HTTP Strict Transport Security presence |
| SSH Audit | ssh-audit | SSH key exchange, cipher, and MAC algorithms |
| Default Credentials | hydra | Common username/password combinations |
| HTTP Security Headers | nikto | CSP, X-Content-Type-Options, X-Frame-Options |
| Protocol Compliance | custom | Compare open ports against approved whitelist |
| Ping Response | nmap | ICMP reachability verification |
| MAC Vendor Lookup | nmap + OUI | Manufacturer identification from MAC address |
| HTTP→HTTPS Redirect | curl | Verify unencrypted access is disabled or redirects |
| Brute Force Protection | custom | Verify account lockout after repeated failures |
| SNMP Community Strings | nmap | Check for default SNMP community strings |
| mDNS/Bonjour Detection | nmap | Identify multicast DNS services |
| UPnP Detection | nmap | Detect Universal Plug and Play services |
| Telnet Detection | nmap | Flag insecure Telnet access |
| FTP Detection | nmap | Flag insecure FTP access |
| NTP Amplification | nmap | Check for NTP monlist amplification |
| RTSP Stream Security | custom | Verify RTSP stream authentication |
| MQTT Broker Check | custom | Check MQTT authentication and TLS |
| BACnet Discovery | nmap | Identify BACnet/IP building automation services |
| DNS Zone Transfer | nmap | Check for unauthorised zone transfers |
| IPv6 Support | nmap | Detect IPv6 capability (informational) |
| DHCP Behaviour | discovery | Verify DHCP lease acceptance |
| Switch Negotiation | discovery | Check speed/duplex auto-negotiation |
| Certificate Chain | testssl.sh | Validate full certificate chain of trust |

**15 Guided Manual Tests** — structured forms where the engineer physically verifies:

- **Network Disconnection** — pull the Ethernet cable, observe recovery behaviour
- **Password Change** — change the default password via the device web UI
- **Firmware Update** — check the firmware update mechanism and verify current version
- **Session Timeout** — wait for inactivity logout on the device web interface
- **Physical Security** — inspect for exposed reset buttons, USB ports, SD card slots
- **VLAN Isolation** — test VLAN tagging support and trunk port behaviour
- **Multicast Traffic** — monitor broadcast/multicast output on the network
- **API Authentication** — verify API endpoints require proper authentication
- **Audit Trail** — review device logging and audit trail capabilities
- **Data-at-Rest Encryption** — check whether stored data is encrypted
- **Vendor Support / EOL** — verify manufacturer support status and end-of-life dates
- **Configuration Backup** — verify device config can be exported and restored
- **Web UI HTTPS** — confirm the management web interface uses HTTPS by default
- **Default Account Removal** — verify all default/guest accounts are disabled
- **Documentation Review** — check that security hardening guides are available

Each manual test presents single-click verdict buttons (Pass / Fail / Info / N/A) plus an optional notes field — no free-text data entry required.

### 📊 Three Report Formats

- **Excel** — Uses actual Electracom client templates (`.xlsx`). Opens the original template file with openpyxl, fills in results, and saves — preserving ALL formatting, logos, merged cells, borders, colours, and conditional formatting. Supports three template variants: Pelco Camera (31 tests), EasyIO Controller (46 tests), and Generic IP Device (43 tests).
- **Word** — Professional `.docx` report with styled cover page, executive summary, colour-coded results table, detailed findings for each failure, and protocol whitelist comparison matrix.
- **PDF** — Generated from the Word report via LibreOffice headless conversion. Suitable for direct client distribution.

### 🔌 Wobbly Cable Handler

Monitors device connectivity in real time during testing. If the Ethernet cable is accidentally disconnected or the device reboots mid-test:

1. **Detects loss** after 3 consecutive ping failures
2. **Pauses** all running tests immediately
3. **Alerts** the engineer via a real-time WebSocket notification in the UI
4. **Retries** connectivity every 30 seconds
5. **Auto-resumes** testing when the connection returns (with a 10-second stability wait)
6. **Escalates** after 5 minutes of no connectivity — marks the test run as `paused_cable`

### 🖥️ Desktop Application

Packaged as an Electron app with platform-specific installers:

- **One-click installer** for Windows (`.exe` / `.msi`), macOS (`.dmg`), and Linux (`.AppImage` / `.deb`)
- **Automatic Docker management** — starts, stops, and restarts Docker containers from the app
- **System tray icon** with quick-access menu (open app, restart services, quit)
- **Splash screen** with real-time startup progress
- **Auto-update** capability via electron-updater

### 🌐 Network Scan Mode

Scan an entire subnet (e.g., `192.168.1.0/24`) to discover and fingerprint multiple devices at once. Ideal for site surveys, bulk qualification, and network audits. Discovered devices are automatically registered and ready for individual test runs.

### 📋 Custom Test Plans

Create custom test configurations that enable or disable specific tests, override their automation tier, or adjust pass/fail thresholds. Save plans as reusable templates for different device categories — for example, a "Camera" plan that skips BACnet tests, or a "Controller" plan that adds extra protocol checks.

### 🔐 Role-Based Access Control

Three roles with distinct permissions:

| Role | Capabilities |
|------|-------------|
| **Admin** | Full access — user management, template management, device profiles, system configuration |
| **Engineer** | Run tests, complete manual assessments, generate reports, manage devices |
| **Reviewer** | Review completed test runs, override any verdict with documented justification, approve reports |

### 📡 Real-Time Progress

WebSocket-powered live updates during test execution:

- **Terminal output streaming** via xterm.js — watch nmap, testssl, and other tools run in real time
- **Progress bar** with percentage completion and estimated time remaining
- **Individual test status** updates as each test starts, completes, or fails
- **Wobbly cable alerts** — instant notification if device connectivity is lost

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  DOCKER COMPOSE (engineer's laptop)                     │
│                                                         │
│  ┌──────────┐   ┌──────────┐   ┌────────────────────┐  │
│  │  NGINX   │   │ FASTAPI  │   │   TOOLS SIDECAR    │  │
│  │ (port 80)│──▶│ BACKEND  │──▶│  nmap, testssl.sh  │  │
│  │  serves  │   │ (port    │   │  ssh-audit, hydra   │  │
│  │  React   │   │  8000)   │   │  nikto              │  │
│  │  SPA     │   │          │   │  (port 8001)        │  │
│  └──────────┘   └────┬─────┘   └────────────────────┘  │
│                      │                                   │
│                 ┌────┴─────┐                             │
│                 │  SQLite  │                             │
│                 │  edq.db  │                             │
│                 └──────────┘                             │
└─────────────────────────────────────────────────────────┘
         │ Ethernet
    ┌────┴────────┐
    │   DEVICE    │
    │  UNDER TEST │
    └─────────────┘
```

**Frontend (NGINX + React SPA)** — Serves the single-page React application on port 80. NGINX proxies all `/api/*` requests to the backend and upgrades `/ws/*` connections for WebSocket communication. Adds security headers (CSP, HSTS, X-Frame-Options).

**Backend (FastAPI + Python 3.12)** — The core application server. Handles authentication (JWT in httpOnly cookies with CSRF protection), all REST API endpoints, WebSocket connections for real-time progress, database operations via SQLAlchemy 2.0 async ORM, and report generation (Excel via openpyxl, Word via python-docx, PDF via LibreOffice).

**Tools Sidecar (Ubuntu 22.04)** — A lightweight container running security scanning tools with a REST API wrapper on port 8001. The backend calls this service to execute nmap, testssl.sh, ssh-audit, hydra, and nikto scans. Requires `NET_ADMIN` and `NET_RAW` capabilities for Layer 2 network scanning. Runs in host network mode to access devices on the engineer's physical network.

**SQLite Database** — Stores all application data in WAL mode for concurrent read access. Persisted via a Docker volume at `/data/edq.db`. Schema includes 11 tables covering users, devices, test templates, test runs, test results, attachments, protocol whitelists, device profiles, report configs, audit logs, and Nessus findings.

---

## Quick Start

> **Full installation guide with Windows-specific instructions:** [INSTALL.md](INSTALL.md)

### Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (Windows, macOS, or Linux)
- Git

### Run

```bash
git clone https://github.com/Rvs006/edq.git
cd edq
docker compose up --build
```

Open [http://localhost](http://localhost) in your browser.

**Default login:** `admin@electracom.co.uk` / `Admin123!`

### Stop

```bash
docker compose down
```

### Troubleshooting

| Problem | Solution |
|---------|----------|
| Port 80 already in use | Edit `docker-compose.yml` — change `"80:80"` to `"8080:80"`, then open `http://localhost:8080` |
| Docker not running | Start Docker Desktop and wait for it to fully initialise |
| Build fails | Run `docker compose down -v && docker compose up --build` to rebuild from scratch |
| ThreatLocker blocking | Whitelist Docker Desktop in ThreatLocker, or temporarily set it to Learning Mode |
| Database locked errors | Restart the backend container: `docker compose restart backend` |
| Tools sidecar unhealthy | Check logs: `docker compose logs tools` — ensure nmap and testssl.sh are installed |
| WebSocket not connecting | Verify NGINX config includes `proxy_set_header Upgrade $http_upgrade;` |

---

## Project Structure

```
edq/
├── assets/                # Electracom branding (logo images)
├── frontend/              # React 18 + Vite + Tailwind CSS
│   ├── src/
│   │   ├── pages/         # 8 application pages
│   │   ├── components/    # Reusable UI components
│   │   ├── lib/           # API client, utilities
│   │   └── hooks/         # Custom React hooks
│   └── public/            # Static assets (logo, favicon)
├── server/backend/        # FastAPI + SQLAlchemy + SQLite
│   ├── app/
│   │   ├── models/        # SQLAlchemy ORM models (11 tables)
│   │   ├── schemas/       # Pydantic request/response schemas
│   │   ├── routes/        # API route handlers
│   │   └── services/      # Business logic layer
│   └── alembic/           # Database migrations
├── tools/                 # Security tools sidecar (nmap, testssl, etc.)
├── electron/              # Desktop app wrapper (Electron + electron-builder)
├── templates/             # Excel report templates (.xlsx)
├── docker/                # NGINX configuration
├── scripts/               # Integration test scripts
├── docs/                  # Project documentation
│   ├── PRODUCT_REQUIREMENTS.md
│   ├── ENGINEERING_SPEC.md
│   └── DESIGN_SYSTEM.md
├── docker-compose.yml
├── CONTRIBUTING.md
└── LICENSE
```

---

## Complete Test List

<details>
<summary>View all 43 tests</summary>

| ID | Name | Type | Tool | Essential |
|----|------|------|------|-----------|
| U01 | Ping Response | Auto | nmap | Yes |
| U02 | MAC Vendor Lookup | Auto | nmap + OUI | Yes |
| U03 | Switch Negotiation | Auto | discovery | No |
| U04 | DHCP Behaviour | Auto | discovery | No |
| U05 | IPv6 Support | Auto | nmap | No |
| U06 | Full TCP Port Scan | Auto | nmap | Yes |
| U07 | UDP Top-100 Scan | Auto | nmap | Yes |
| U08 | Service Detection | Auto | nmap | Yes |
| U09 | Protocol Whitelist Compliance | Auto | custom | Yes |
| U10 | TLS Version Check | Auto | testssl.sh | Yes |
| U11 | Cipher Suite Assessment | Auto | testssl.sh | Yes |
| U12 | Certificate Validity | Auto | testssl.sh | Yes |
| U13 | HSTS Header | Auto | testssl.sh | Yes |
| U14 | HTTP Security Headers | Auto | nikto | Yes |
| U15 | SSH Algorithm Audit | Auto | ssh-audit | Yes |
| U16 | Default Credentials | Auto | hydra | Yes |
| U17 | Brute Force Protection | Auto | custom | Yes |
| U18 | HTTP→HTTPS Redirect | Auto | curl | Yes |
| U19 | OS Fingerprinting | Auto | nmap | No |
| U20 | SNMP Community Strings | Auto | nmap | Yes |
| U21 | mDNS/Bonjour Detection | Auto | nmap | No |
| U22 | UPnP Detection | Auto | nmap | Yes |
| U23 | Telnet Detection | Auto | nmap | Yes |
| U24 | FTP Detection | Auto | nmap | Yes |
| U25 | NTP Amplification | Auto | nmap | Yes |
| U26 | RTSP Stream Security | Auto | custom | Yes |
| U27 | MQTT Broker Check | Auto | custom | No |
| U28 | BACnet Discovery | Auto | nmap | No |
| M01 | Network Disconnection | Manual | — | Yes |
| M02 | Password Change | Manual | — | Yes |
| M03 | Firmware Update Check | Manual | — | Yes |
| M04 | Session Timeout | Manual | — | Yes |
| M05 | Physical Security Inspection | Manual | — | Yes |
| M06 | VLAN Isolation | Manual | — | No |
| M07 | Multicast Traffic Analysis | Manual | — | No |
| M08 | API Authentication | Manual | — | Yes |
| M09 | Audit Trail Review | Manual | — | No |
| M10 | Data-at-Rest Encryption | Manual | — | No |
| M11 | Vendor Support / EOL | Manual | — | No |
| M12 | Configuration Backup | Manual | — | No |
| M13 | Web UI HTTPS Default | Manual | — | Yes |
| M14 | Default Account Removal | Manual | — | Yes |
| M15 | Documentation Review | Manual | — | No |

</details>

---

## API Reference

The backend serves interactive API documentation at:
- **Swagger UI:** [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc:** [http://localhost:8000/redoc](http://localhost:8000/redoc)

### Authentication
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/auth/login` | Authenticate and receive session cookie |
| POST | `/api/auth/logout` | Clear session cookies |
| POST | `/api/auth/register` | Create new user (admin only) |
| GET | `/api/auth/me` | Get current user info |
| POST | `/api/auth/change-password` | Change current user password |

### Devices
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/devices/` | List all registered devices (paginated) |
| POST | `/api/devices/` | Register a new device |
| GET | `/api/devices/{id}` | Get device detail |
| PUT | `/api/devices/{id}` | Update device metadata |
| DELETE | `/api/devices/{id}` | Soft-delete a device |
| POST | `/api/devices/discover` | Trigger auto-discovery scan |

### Test Runs
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/runs/` | List test runs (with filters) |
| POST | `/api/runs/` | Create a new test run |
| GET | `/api/runs/{id}` | Get run detail with all results |
| POST | `/api/runs/{id}/start` | Begin automated testing |
| POST | `/api/runs/{id}/pause` | Pause test execution |
| POST | `/api/runs/{id}/resume` | Resume paused test run |

### Test Results
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/runs/{run_id}/results` | Get all results for a run |
| PUT | `/api/runs/{run_id}/results/{test_id}` | Submit manual test verdict |
| POST | `/api/runs/{run_id}/results/{test_id}/override` | Reviewer override verdict |
| POST | `/api/runs/{run_id}/results/{test_id}/rerun` | Re-execute an automated test |

### Reports
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/runs/{run_id}/report/excel` | Generate and download Excel report |
| POST | `/api/runs/{run_id}/report/word` | Generate and download Word report |
| POST | `/api/runs/{run_id}/report/pdf` | Generate and download PDF report |
| GET | `/api/runs/{run_id}/report/preview` | Preview report data as JSON |

### Nessus Integration
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/runs/{run_id}/nessus/upload` | Upload `.nessus` XML file |
| GET | `/api/runs/{run_id}/nessus/findings` | List parsed vulnerability findings |

### Administration
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/admin/users` | List all users |
| PUT | `/api/admin/users/{id}` | Update user role or status |
| GET | `/api/admin/audit-logs` | View audit trail |
| GET | `/api/admin/stats` | Dashboard statistics |

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 18, Vite, Tailwind CSS, Zustand, TanStack Query, xterm.js, Recharts |
| Backend | Python 3.12, FastAPI, SQLAlchemy 2.0 (async), Pydantic v2, Alembic |
| Database | SQLite with WAL mode, persisted via Docker volume |
| Security Tools | nmap 7.94, testssl.sh 3.0, ssh-audit 3.1, hydra 9.5, nikto 2.5 |
| Reports | openpyxl (Excel), python-docx (Word), LibreOffice (PDF conversion) |
| Desktop | Electron 28, electron-builder, electron-updater |
| Infrastructure | Docker Compose, NGINX (reverse proxy + static serving) |

---

## Development

### Backend

```bash
cd server/backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
pnpm install
pnpm dev
```

### Tools Sidecar

```bash
cd tools
docker build -t edq-tools .
docker run -p 8001:8001 --cap-add NET_ADMIN --cap-add NET_RAW edq-tools
```

### Running Everything

```bash
docker compose up --build
```

---

## Compliance Mapping

EDQ tests map to controls in three major compliance frameworks:

| Framework | Coverage | Key Controls |
|-----------|----------|-------------|
| **ISO 27001:2022** | Annex A controls A.8.9 (Configuration Management), A.8.20 (Network Security), A.8.24 (Cryptography), A.8.28 (Secure Coding) | TLS checks, SSH audit, port scanning, protocol whitelist |
| **Cyber Essentials** | All five technical controls — Firewalls, Secure Configuration, Access Control, Malware Protection, Patch Management | Default credential testing, service hardening, firmware checks, access controls |
| **SOC2 Type II** | Trust Services Criteria CC6.1 (Logical Access), CC6.6 (System Boundaries), CC7.1 (Infrastructure Monitoring) | RBAC verification, network segmentation, audit logging |

Each test result in the generated report includes the relevant compliance control reference, enabling auditors to trace test coverage directly to framework requirements.

---

## License

Proprietary — Copyright 2025–2026 Electracom Projects Ltd, a Sauter Group Company. All rights reserved. See [LICENSE](LICENSE) for details.

---

## Testing

**Quick smoke test** — verifies services are up and basic auth works (~10 seconds):
```bash
./scripts/verify-app.sh
```

**Full E2E test suite** — comprehensive CRUD, lifecycle, error handling, and cleanup (~60 seconds):
```bash
./scripts/e2e-test.sh              # default: http://localhost
./scripts/e2e-test.sh http://host:port   # custom target
```

The E2E suite covers: infrastructure health, authentication flow, device CRUD, test templates & library, test run lifecycle (create → execute → complete), protocol whitelists, device profiles, report generation, admin endpoints, network scans, test plans, discovery, agents, and error handling. All test data is cleaned up automatically.

---

## Author

Developed by **Rajesh Shinde, Dhilen Patel & Jon Hubbard** for **Electracom Projects Ltd**.

Electracom Projects Ltd is a Sauter Group company specialising in building management systems, security integration, and smart building solutions across the United Kingdom.
