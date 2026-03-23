# ELECTRACOM DEVICE QUALIFIER (EDQ) — Complete Implementation PRD

**V1.2 — Full Technical Specification for Development (Final)**

| Field | Value |
|---|---|
| Document Version | 1.2.0 |
| Status | Approved for Development |
| Classification | Internal — Confidential |
| Last Updated | 2026-02-23 |
| Target Release | V1.0 — 12 Weeks |

### Revision History

| Version | Date | Changes |
|---|---|---|
| 1.0.0 | 2026-02-23 | Initial implementation PRD |
| 1.1.0 | 2026-02-23 | Integrated 11 operational & safety gaps: privilege escalation, device safety profiles, TLS tooling strategy, agent version management, network crash recovery, hardcoded static IP handling, AI data anonymisation, offline DB key management, PDF worker queue, interface selection, unknown IP scanning |
| 1.2.0 | 2026-02-23 | Final gap closure: DHCP server mode, APIPA fallback, iproute2 Linux commands, OUI sync, complete U04–U25 test definitions with eval rules, sslyze parser specification, sync conflict merge algorithm, Npcap driver requirement for Windows |

---

## Table of Contents

1. [Product Overview](#1-product-overview)
2. [Repository Structure](#2-repository-structure)
3. [Technology Stack](#3-technology-stack)
4. [Database Schema](#4-database-schema)
5. [Authentication & Authorisation](#5-authentication--authorisation)
6. [API Specification](#6-api-specification)
7. [Auto-Discovery Pipeline](#7-auto-discovery-pipeline)
8. [Three-Tier Test Engine](#8-three-tier-test-engine)
9. [Universal Test Library](#9-universal-test-library)
10. [Device Profiles](#10-device-profiles)
11. [Template System](#11-template-system)
12. [Guided Manual Test Workflow](#12-guided-manual-test-workflow)
13. [Wobbly Cable Resilience Handler](#13-wobbly-cable-resilience-handler)
14. [Nessus Integration](#14-nessus-integration)
15. [Report Generation Engine](#15-report-generation-engine)
16. [AI Synopsis Generator](#16-ai-synopsis-generator)
17. [Agent Architecture](#17-agent-architecture)
18. [Offline Architecture](#18-offline-architecture)
19. [Sync Protocol](#19-sync-protocol)
20. [WebSocket Real-Time Streaming](#20-websocket-real-time-streaming)
21. [Frontend Application](#21-frontend-application)
22. [Security Controls](#22-security-controls)
23. [Deployment & Infrastructure](#23-deployment--infrastructure)
24. [Error Handling & Logging](#24-error-handling--logging)
25. [Testing Strategy](#25-testing-strategy)

---

## 1. Product Overview

### 1.1 What EDQ Does

EDQ is an automated network security testing platform that qualifies smart building IP devices for enterprise network deployment. It supports any IP-connected device — cameras, HVAC controllers, intercoms, access panels, lighting controllers, IoT sensors, meters — through a modular, device-agnostic architecture.

### 1.2 The Problem

Each device qualification currently takes one full working day of manual work per device: running CLI security tools, transcribing results into Excel, writing narrative reports. With 30+ devices per month across 10 engineers, this is unsustainable.

### 1.3 The Solution

EDQ reduces qualification to 1–2 hours per device through: zero-input auto-discovery that fingerprints devices automatically, a three-tier test engine that automates 60–65% of tests and structures the remaining manual tests as single-click decisions, and template-based report generation that produces pixel-perfect client deliverables.

### 1.4 Key Design Principles

1. **Zero Unnecessary Input:** The engineer enters an IP address (or lets the system find it) and clicks one button. Everything else is automatic or structured single-click.
2. **Device Agnostic:** Any IP device works. Known devices get optimised templates. Unknown devices get the universal security assessment.
3. **Offline First:** Full testing capability without internet. Results sync when connectivity returns.
4. **Deterministic Security Verdicts:** All pass/fail decisions are rule-based and auditable. No AI in the decision pipeline.
5. **Pixel-Perfect Reports:** Generated reports are indistinguishable from hand-crafted originals.
6. **Device Safety First:** Scanning must never crash, brick, or disrupt the device under test. Safe scan intensity is the universal default.
7. **Crash-Safe Networking:** The agent must never leave the engineer's laptop in a broken network state, regardless of how the agent exits.
8. **Client Data Privacy:** Vulnerability data is classified as CONFIDENTIAL. No unredacted client data leaves the organisation's infrastructure without explicit policy approval.

### 1.5 Users

| Role | Count | Access | Capabilities |
|---|---|---|---|
| Test Engineer | 10 | Web UI + Desktop Agent | Run tests, complete manual assessments, generate reports |
| Reviewer / QA Lead | 2–3 | Web UI only (no agent) | Review results, override verdicts, approve reports |
| Admin / Developer | 1 | Web UI + Server access | Manage users, create templates, manage device profiles, system config |

### 1.6 Architecture Summary

```
┌─────────────────────────────────────────────────────────┐
│  CENTRAL SERVER (Azure VM / On-Prem)                    │
│  ┌────────┐ ┌──────────┐ ┌────────┐ ┌────────┐         │
│  │ Nginx  │ │ FastAPI  │ │SQLite  │ │ Redis  │         │
│  │ +React │ │ Backend  │ │  DB    │ │ Queue  │         │
│  │  SPA   │ │ (Py3.12) │ │        │ │        │         │
│  └───┬────┘ └────┬─────┘ └───┬────┘ └───┬────┘         │
│      │           │           │           │              │
│      └───────────┴───────────┴───────────┘              │
│                                                         │
│  ┌──────────────────┐                                   │
│  │ PDF Worker       │  (Separate process, Redis queue)  │
│  │ (LibreOffice)    │                                   │
│  └──────────────────┘                                   │
└──────────────────────┬──────────────────────────────────┘
                       │ HTTPS (TLS 1.3)
          ┌────────────┼────────────┐
          │            │            │
   ┌──────┴──────┐ ┌──┴───────┐ ┌──┴──────────┐
   │ Agent       │ │ Agent    │ │ Reviewer    │
   │ (Win/Mac)   │ │ (Win/Mac)│ │ (Browser    │
   │ Runs as     │ │ Eng #2   │ │  only)      │
   │ ADMIN/ROOT  │ │          │ │             │
   └──────┬──────┘ └──┬───────┘ └─────────────┘
          │ Cat6      │ Cat6
   ┌──────┴──────┐ ┌──┴───────┐
   │ Device      │ │ Device   │
   │ Under Test  │ │ Under    │
   │ (Any IP)    │ │ Test     │
   └─────────────┘ └──────────┘
```

---

## 2. Repository Structure

```
edq/
├── ENGINEERING_SPEC.md                # Technical specification
├── README.md                          # Quick start guide
├── .env.example                       # Environment variable template
├── .gitignore
│
├── server/                            # Central server application
│   ├── docker-compose.yml             # Nginx + Backend + Redis + PDF Worker
│   ├── docker-compose.dev.yml         # Development overrides
│   ├── nginx/
│   │   ├── nginx.conf                 # Production config with TLS
│   │   └── nginx.dev.conf             # Dev config (no TLS)
│   │
│   ├── backend/
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   ├── alembic.ini                # Database migrations
│   │   ├── alembic/
│   │   │   └── versions/              # Migration scripts
│   │   │
│   │   ├── app/
│   │   │   ├── __init__.py
│   │   │   ├── main.py                # FastAPI app factory
│   │   │   ├── config.py              # Settings from env vars
│   │   │   ├── dependencies.py        # Dependency injection
│   │   │   │
│   │   │   ├── models/                # SQLAlchemy ORM models
│   │   │   │   ├── __init__.py
│   │   │   │   ├── user.py
│   │   │   │   ├── device.py
│   │   │   │   ├── test_template.py
│   │   │   │   ├── test_run.py
│   │   │   │   ├── test_result.py
│   │   │   │   ├── attachment.py
│   │   │   │   ├── agent.py
│   │   │   │   ├── audit_log.py
│   │   │   │   ├── report_config.py
│   │   │   │   ├── sync_queue.py
│   │   │   │   └── device_profile.py
│   │   │   │
│   │   │   ├── schemas/               # Pydantic request/response models
│   │   │   │   ├── __init__.py
│   │   │   │   ├── auth.py
│   │   │   │   ├── user.py
│   │   │   │   ├── device.py
│   │   │   │   ├── test_template.py
│   │   │   │   ├── test_run.py
│   │   │   │   ├── test_result.py
│   │   │   │   ├── agent.py
│   │   │   │   ├── report.py
│   │   │   │   ├── discovery.py
│   │   │   │   └── sync.py
│   │   │   │
│   │   │   ├── routes/                # API route handlers
│   │   │   │   ├── __init__.py
│   │   │   │   ├── auth.py
│   │   │   │   ├── users.py
│   │   │   │   ├── devices.py
│   │   │   │   ├── test_templates.py
│   │   │   │   ├── test_runs.py
│   │   │   │   ├── test_results.py
│   │   │   │   ├── reports.py
│   │   │   │   ├── agent_api.py       # Agent-facing endpoints
│   │   │   │   ├── discovery.py
│   │   │   │   ├── admin.py
│   │   │   │   └── websocket.py
│   │   │   │
│   │   │   ├── services/              # Business logic layer
│   │   │   │   ├── __init__.py
│   │   │   │   ├── auth_service.py
│   │   │   │   ├── device_service.py
│   │   │   │   ├── test_engine.py     # Three-tier orchestration
│   │   │   │   ├── discovery_service.py
│   │   │   │   ├── evaluation_engine.py  # Pass/fail rule engine
│   │   │   │   ├── report_service.py
│   │   │   │   ├── excel_generator.py    # Template-based Excel
│   │   │   │   ├── word_generator.py     # Template-based Word
│   │   │   │   ├── pdf_worker.py         # Redis queue consumer for PDF
│   │   │   │   ├── synopsis_service.py   # AI draft generator
│   │   │   │   ├── anonymiser.py         # Strip client data before AI API
│   │   │   │   ├── sync_service.py
│   │   │   │   ├── template_service.py
│   │   │   │   └── audit_service.py
│   │   │   │
│   │   │   ├── security/              # Security middleware & utils
│   │   │   │   ├── __init__.py
│   │   │   │   ├── csrf.py
│   │   │   │   ├── rate_limiter.py
│   │   │   │   ├── sanitiser.py       # Terminal output sanitisation
│   │   │   │   ├── file_validator.py   # Magic byte validation
│   │   │   │   └── password.py         # bcrypt hashing
│   │   │   │
│   │   │   ├── websocket/             # WebSocket handlers
│   │   │   │   ├── __init__.py
│   │   │   │   ├── manager.py         # Connection management
│   │   │   │   ├── terminal.py        # Live terminal streaming
│   │   │   │   └── events.py          # Event type definitions
│   │   │   │
│   │   │   └── utils/
│   │   │       ├── __init__.py
│   │   │       ├── oui_lookup.py      # MAC → vendor database
│   │   │       └── nessus_parser.py   # .nessus XML parser
│   │   │
│   │   ├── templates/                 # Report template files
│   │   │   ├── excel/                 # .xlsx client templates
│   │   │   │   ├── pelco_camera_rev2.xlsx
│   │   │   │   ├── easyio_fw08_v1.1.xlsx
│   │   │   │   └── universal_assessment.xlsx
│   │   │   ├── word/                  # .docx report templates
│   │   │   │   └── executive_summary.docx
│   │   │   └── cell_mappings/         # JSON cell mapping configs
│   │   │       ├── pelco_camera_rev2.json
│   │   │       └── easyio_fw08_v1.1.json
│   │   │
│   │   ├── data/
│   │   │   ├── oui_database.csv       # IEEE MAC vendor database
│   │   │   ├── default_credentials.json  # Manufacturer defaults
│   │   │   └── seed_data.py           # Initial users, profiles
│   │   │
│   │   └── tests/
│   │       ├── conftest.py
│   │       ├── test_auth.py
│   │       ├── test_discovery.py
│   │       ├── test_evaluation.py
│   │       ├── test_reports.py
│   │       ├── test_anonymiser.py
│   │       └── test_sync.py
│   │
│   ├── pdf_worker/                    # Separate PDF generation service
│   │   ├── Dockerfile                 # Includes LibreOffice headless
│   │   ├── requirements.txt
│   │   └── worker.py                  # Redis queue consumer
│   │
│   └── frontend/
│       ├── Dockerfile
│       ├── package.json
│       ├── vite.config.js
│       ├── tailwind.config.js
│       ├── index.html
│       │
│       └── src/
│           ├── main.jsx
│           ├── App.jsx
│           ├── api/                   # API client layer
│           │   ├── client.js          # Axios instance with CSRF
│           │   ├── auth.js
│           │   ├── devices.js
│           │   ├── testRuns.js
│           │   ├── reports.js
│           │   ├── agents.js
│           │   ├── templates.js
│           │   └── websocket.js       # WebSocket client
│           │
│           ├── components/
│           │   ├── layout/
│           │   │   ├── AppLayout.jsx
│           │   │   ├── Sidebar.jsx
│           │   │   ├── Header.jsx
│           │   │   └── ProtectedRoute.jsx
│           │   │
│           │   ├── devices/
│           │   │   ├── DeviceList.jsx
│           │   │   ├── DeviceCard.jsx
│           │   │   ├── DeviceDetail.jsx
│           │   │   ├── DeviceFingerprint.jsx    # Discovery card
│           │   │   └── CreateDeviceModal.jsx
│           │   │
│           │   ├── testing/
│           │   │   ├── TestSession.jsx           # Main test view
│           │   │   ├── TestProgress.jsx          # Progress tracker
│           │   │   ├── TestResultCard.jsx
│           │   │   ├── AutoTestResult.jsx        # Tier 1 display
│           │   │   ├── ManualTestForm.jsx        # Tier 2 guided form
│           │   │   ├── AutoNAResult.jsx          # Tier 3 display
│           │   │   ├── LiveTerminal.jsx          # WebSocket terminal
│           │   │   ├── WobblyCableAlert.jsx
│           │   │   ├── InterfaceSelector.jsx     # Network interface picker
│           │   │   └── NessusUpload.jsx
│           │   │
│           │   ├── reports/
│           │   │   ├── ReportGenerator.jsx
│           │   │   ├── SynopsisEditor.jsx        # AI draft + edit
│           │   │   ├── ReportPreview.jsx
│           │   │   └── BrandingConfig.jsx
│           │   │
│           │   ├── review/
│           │   │   ├── ReviewDashboard.jsx
│           │   │   ├── ResultOverrideModal.jsx
│           │   │   └── ApprovalWorkflow.jsx
│           │   │
│           │   ├── admin/
│           │   │   ├── UserManagement.jsx
│           │   │   ├── TemplateImport.jsx
│           │   │   ├── CellMappingEditor.jsx
│           │   │   ├── DeviceProfileEditor.jsx
│           │   │   └── AgentMonitor.jsx
│           │   │
│           │   └── common/
│           │       ├── StatusBadge.jsx
│           │       ├── VerdictBadge.jsx
│           │       ├── ConfirmDialog.jsx
│           │       ├── FileUpload.jsx
│           │       ├── DataTable.jsx
│           │       └── LoadingSpinner.jsx
│           │
│           ├── pages/
│           │   ├── LoginPage.jsx
│           │   ├── DashboardPage.jsx
│           │   ├── DevicesPage.jsx
│           │   ├── DeviceDetailPage.jsx
│           │   ├── TestSessionPage.jsx
│           │   ├── ReportsPage.jsx
│           │   ├── ReviewPage.jsx
│           │   └── AdminPage.jsx
│           │
│           ├── hooks/
│           │   ├── useAuth.js
│           │   ├── useWebSocket.js
│           │   ├── useTestSession.js
│           │   └── useDeviceDiscovery.js
│           │
│           ├── context/
│           │   └── AuthContext.jsx
│           │
│           └── utils/
│               ├── verdictColors.js
│               └── formatters.js
│
├── agent/                             # Desktop scanning agent
│   ├── requirements.txt
│   ├── setup.py
│   │
│   ├── edq_agent/
│   │   ├── __init__.py
│   │   ├── main.py                    # Entry point (with privilege check)
│   │   ├── config.py                  # Agent configuration
│   │   │
│   │   ├── core/
│   │   │   ├── __init__.py
│   │   │   ├── scanner.py             # Tool execution orchestrator
│   │   │   ├── tool_runner.py         # Subprocess management
│   │   │   ├── privilege_checker.py   # Admin/root verification
│   │   │   ├── wobbly_cable.py        # Connectivity handler
│   │   │   ├── interface_manager.py   # Network interface detection + selection
│   │   │   ├── network_guard.py       # Crash-safe network state manager
│   │   │   └── job_poller.py          # Server job queue polling
│   │   │
│   │   ├── tools/
│   │   │   ├── __init__.py
│   │   │   ├── nmap_runner.py         # nmap execution + args
│   │   │   ├── nmap_parser.py         # nmap output parser
│   │   │   ├── sslyze_runner.py       # Native Python TLS scanning (primary)
│   │   │   ├── sslyze_parser.py       # sslyze result parser
│   │   │   ├── testssl_runner.py      # testssl.sh (Mac/Linux enhanced, optional)
│   │   │   ├── testssl_parser.py      # testssl.sh output parser
│   │   │   ├── ssh_audit_runner.py
│   │   │   ├── ssh_audit_parser.py
│   │   │   ├── nikto_runner.py
│   │   │   ├── nikto_parser.py
│   │   │   ├── hydra_runner.py        # Credential testing
│   │   │   └── hydra_parser.py
│   │   │
│   │   ├── discovery/
│   │   │   ├── __init__.py
│   │   │   ├── fingerprinter.py       # Auto-discovery pipeline
│   │   │   ├── arp_resolver.py        # MAC address discovery
│   │   │   ├── arp_sweep.py           # Hardcoded static IP finder
│   │   │   ├── dhcp_server.py         # DHCP server for device discovery
│   │   │   ├── subnet_scanner.py      # Unknown IP network scan
│   │   │   ├── port_scanner.py        # Quick port scan
│   │   │   ├── service_detector.py    # Banner grab + fingerprint
│   │   │   ├── category_classifier.py # Rules-based device type
│   │   │   └── oui_lookup.py          # MAC → manufacturer
│   │   │
│   │   ├── evaluation/
│   │   │   ├── __init__.py
│   │   │   ├── rule_engine.py         # Pass/fail evaluation
│   │   │   ├── verdict_mapper.py      # Result → verdict mapping
│   │   │   ├── comment_generator.py   # Auto-generated comments
│   │   │   └── prereq_checker.py      # Auto-N/A prerequisite rules
│   │   │
│   │   ├── offline/
│   │   │   ├── __init__.py
│   │   │   ├── local_db.py           # Encrypted SQLite
│   │   │   ├── crypto.py             # AES-256-GCM encryption
│   │   │   ├── key_manager.py        # OS keychain + server key sync
│   │   │   ├── local_server.py       # localhost:8433 web UI
│   │   │   ├── sync_manager.py       # Upload queue management
│   │   │   └── conflict_resolver.py  # Sync conflict handling
│   │   │
│   │   ├── network/
│   │   │   ├── __init__.py
│   │   │   ├── interface_isolator.py  # OS routing isolation
│   │   │   ├── server_client.py       # HTTPS client to server
│   │   │   └── heartbeat.py           # Health check loop
│   │   │
│   │   └── ui/
│   │       ├── tray.py               # System tray icon + menu
│   │       └── assets/               # Tray icons (grey/green/blue/orange/red)
│   │
│   ├── packaging/
│   │   ├── windows/
│   │   │   ├── edq_agent.spec        # PyInstaller spec (--uac-admin)
│   │   │   ├── installer.nsi         # NSIS installer script (includes Npcap)
│   │   │   └── tools/                # Bundled tool binaries
│   │   │       ├── nmap/
│   │   │       ├── npcap/            # Npcap silent installer
│   │   │       ├── ssh-audit
│   │   │       └── nikto/
│   │   └── mac/
│   │       ├── edq_agent.spec
│   │       └── tools/
│   │           ├── nmap
│   │           ├── testssl.sh         # Native bash — no MSYS2 needed
│   │           ├── ssh-audit
│   │           └── nikto/
│   │
│   └── tests/
│       ├── conftest.py
│       ├── test_discovery.py
│       ├── test_parsers.py
│       ├── test_evaluation.py
│       ├── test_wobbly_cable.py
│       ├── test_network_guard.py
│       ├── test_arp_sweep.py
│       ├── test_dhcp_server.py
│       └── test_offline.py
│
└── shared/                            # Shared between server + agent
    ├── __init__.py
    ├── constants.py                   # Enums, verdict types, tier types
    ├── test_definitions.py            # Universal test library
    ├── device_categories.py           # Category detection rules
    └── protocol_schemas.py            # Agent ↔ server message formats
```

---

## 3. Technology Stack

### 3.1 Server

| Component | Technology | Version | Purpose |
|---|---|---|---|
| Web Framework | FastAPI | 0.109+ | REST API, WebSocket, async |
| Python | CPython | 3.12 | Runtime |
| ORM | SQLAlchemy | 2.0+ | Database abstraction |
| Migrations | Alembic | 1.13+ | Schema migrations |
| Database | SQLite | 3.45+ | Persistent storage (V1.0) |
| Cache / Queue | Redis | 7.2+ | Job queue, WebSocket pub/sub, PDF queue |
| Task Queue | rq (Redis Queue) | 1.16+ | Background PDF generation |
| Reverse Proxy | Nginx | 1.25+ | TLS termination, rate limiting, static files |
| Frontend Framework | React | 18.2+ | Single Page Application |
| Build Tool | Vite | 5.0+ | Dev server, bundling |
| CSS Framework | Tailwind CSS | 3.4+ | Utility-first styling |
| Excel Generation | openpyxl | 3.1+ | Template-based .xlsx filling |
| Word Generation | python-docx | 1.1+ | Template-based .docx filling |
| PDF Conversion | LibreOffice | 24.2+ | Headless PDF (in worker container only) |
| Template Engine | Jinja2 | 3.1+ | Word template rendering |
| XML Parsing | defusedxml | 0.7+ | Safe Nessus XML parsing |
| Password Hashing | bcrypt | 4.1+ | User credential storage |
| HTTP Client | httpx | 0.27+ | Async HTTP for agent comms |
| AI API | httpx | 0.27+ | LLM API client for synopsis drafting |

### 3.2 Agent

| Component | Technology | Version | Purpose |
|---|---|---|---|
| Runtime | Python (PyInstaller packaged) | 3.12 | Standalone executable |
| Scanning - Ports | nmap | 7.94+ | Port/service/OS scanning |
| Scanning - Ports (Windows) | Npcap | 1.79+ | **REQUIRED** packet capture driver for nmap raw sockets on Windows |
| Scanning - TLS (Primary) | sslyze | 6.0+ | Native Python TLS assessment (all platforms) |
| Scanning - TLS (Enhanced) | testssl.sh | 3.2+ | Extended TLS audit (Mac/Linux only, optional) |
| Scanning - SSH | ssh-audit | 3.1+ | SSH configuration audit |
| Scanning - Web | nikto | 2.5+ | Web vulnerability scanning |
| Scanning - Auth | hydra | 9.5+ | Credential brute force |
| DHCP Server | python-dhcp-server | 0.2+ | Assign IPs to DHCP devices during discovery |
| Encryption | cryptography | 42.0+ | AES-256-GCM for offline DB |
| Key Storage | keyring | 25.0+ | OS keychain access (Win Credential Mgr / macOS Keychain) |
| Local Database | SQLite | 3.45+ | Encrypted local storage |
| System Tray | pystray | 0.19+ | Desktop tray icon |
| Local Web UI | FastAPI (lightweight) | 0.109+ | localhost:8433 offline UI |
| HTTP Client | httpx | 0.27+ | Server communication |
| Interface Detection | psutil | 5.9+ | Network interface enumeration |

### 3.3 TLS Scanning Strategy

**Why two TLS tools:** `testssl.sh` is a bash script requiring a full bash runtime. On Windows, this means bundling MSYS2/Cygwin — which causes subprocess deadlocks, path resolution bugs, and antivirus alerts. `sslyze` is a native Python library that works identically on all platforms.

| Platform | Primary TLS Tool | Enhanced TLS Tool | Notes |
|---|---|---|---|
| Windows | sslyze | Not available | Covers protocol versions, ciphers, certificates, HSTS |
| macOS | sslyze | testssl.sh (optional) | testssl.sh adds vuln checks (ROBOT, DROWN, etc.) |
| Linux | sslyze | testssl.sh (optional) | Same as macOS |

The evaluation engine accepts output from either tool. If both run, results are merged (sslyze provides the baseline, testssl.sh adds vulnerability-specific findings). The test definitions reference a logical test ID (e.g., `U10: TLS Version Assessment`), not a specific tool — the agent picks the appropriate tool based on platform and availability.

### 3.4 Frontend Dependencies

```json
{
  "dependencies": {
    "react": "^18.2.0",
    "react-dom": "^18.2.0",
    "react-router-dom": "^6.22.0",
    "axios": "^1.6.0",
    "@tanstack/react-query": "^5.17.0",
    "zustand": "^4.5.0",
    "react-hot-toast": "^2.4.1",
    "lucide-react": "^0.311.0",
    "@xterm/xterm": "^5.3.0",
    "@xterm/addon-fit": "^0.8.0",
    "recharts": "^2.10.0",
    "date-fns": "^3.2.0"
  },
  "devDependencies": {
    "vite": "^5.0.0",
    "tailwindcss": "^3.4.0",
    "autoprefixer": "^10.4.0",
    "postcss": "^8.4.0"
  }
}
```

### 3.5 Npcap Driver Requirement (Windows Only)

**Critical:** nmap on Windows requires the Npcap packet capture driver for raw socket operations (SYN scans, ARP resolution, OS fingerprinting). Without Npcap, nmap silently falls back to TCP connect scans (`-sT`) which are slower, noisier, and produce different results than SYN scans (`-sS`). This means test verdicts would differ between Windows and Mac agents for the same device — a compliance problem.

**Installation strategy:**

```
Option A (Recommended): Bundle Npcap silent installer with agent installer
  - EDQ Agent NSIS installer runs: npcap-1.79.exe /S /winpcap_mode=yes
  - Requires: Npcap OEM license for silent redistribution ($0 for internal use)
  - User sees single "Install EDQ Agent" prompt, Npcap installs automatically

Option B (Fallback): Check on startup, prompt if missing
  - Agent startup checks: does "npcap" service exist?
  - If not: show modal "EDQ Agent requires Npcap for network scanning. 
    [Download Npcap] [Continue without raw sockets (limited)]"
  - If continuing without: all nmap commands fall back to -sT (TCP connect)
  - Flag in test results: "scan_mode": "tcp_connect" vs "syn_scan"
  - Report includes note: "Tests executed with TCP connect scans (reduced accuracy)"
```

**Startup verification (all platforms):**

```python
class ToolVerifier:
    """Verify all scanning tools are functional at startup."""

    def verify_nmap_raw_sockets(self) -> tuple[bool, str]:
        """Test if nmap can do SYN scans (requires Npcap on Windows, root on Unix)."""
        try:
            result = subprocess.run(
                ["nmap", "-sS", "-p", "1", "--max-retries", "0", "127.0.0.1"],
                capture_output=True, text=True, timeout=10
            )
            if "requires root" in result.stderr.lower() or \
               "requires privileged" in result.stderr.lower() or \
               "dnet: Failed to open" in result.stderr.lower():
                if sys.platform == "win32":
                    return False, "Npcap driver not installed. SYN scans unavailable."
                else:
                    return False, "Root privileges required for SYN scans."
            return True, "SYN scans available."
        except FileNotFoundError:
            return False, "nmap not found in PATH."

    def verify_all(self) -> dict[str, tuple[bool, str]]:
        return {
            "nmap_raw": self.verify_nmap_raw_sockets(),
            "nmap_basic": self._check_tool_exists("nmap"),
            "sslyze": self._check_python_module("sslyze"),
            "ssh_audit": self._check_tool_exists("ssh-audit"),
            "nikto": self._check_tool_exists("nikto"),
        }
```

---

## 4. Database Schema

### 4.1 Users

```sql
CREATE TABLE users (
    id TEXT PRIMARY KEY,                        -- UUID v4
    email TEXT NOT NULL UNIQUE,
    full_name TEXT NOT NULL,
    password_hash TEXT NOT NULL,                 -- bcrypt, cost factor 12
    role TEXT NOT NULL CHECK (role IN ('admin', 'tester', 'reviewer')),
    is_active BOOLEAN NOT NULL DEFAULT 1,
    last_login TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

### 4.2 Devices

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
    fingerprint JSON,                           -- Full discovery results
    template_id TEXT REFERENCES test_templates(id),
    profile_id TEXT REFERENCES device_profiles(id),
    created_by TEXT NOT NULL REFERENCES users(id),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMP
);

CREATE INDEX idx_devices_category ON devices(device_category);
CREATE INDEX idx_devices_created_by ON devices(created_by);
```

### 4.3 Device Profiles

```sql
CREATE TABLE device_profiles (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,                         -- "IP Camera", "Building Controller"
    category TEXT NOT NULL UNIQUE,              -- camera, controller, intercom, iot_sensor
    description TEXT,
    detection_rules JSON NOT NULL,              -- Rules for auto-detection from discovery
    additional_tests JSON NOT NULL,             -- Profile-specific test definitions
    scan_policy JSON NOT NULL DEFAULT '{
        "intensity": "safe",
        "blocked_tools": [],
        "nmap_rate_limit": "--max-rate 200",
        "concurrent_connections": 2,
        "request_delay_ms": 200
    }',
    -- scan_policy.intensity: "safe" (default for all), "normal", "aggressive"
    -- "safe": rate-limited nmap, no nikto, no hydra, sequential tests
    -- "normal": standard nmap, nikto allowed, hydra with short wordlist
    -- "aggressive": full-speed nmap, all tools, parallel execution
    -- Admin can override per-profile, engineer can downgrade (never upgrade) per-session
    is_active BOOLEAN NOT NULL DEFAULT 1,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

**Default profiles and their scan policies:**

```json
[
  {
    "category": "camera",
    "intensity": "safe",
    "blocked_tools": [],
    "nmap_rate_limit": "--max-rate 500",
    "concurrent_connections": 3,
    "request_delay_ms": 100,
    "notes": "Most cameras handle moderate scanning"
  },
  {
    "category": "controller",
    "intensity": "safe",
    "blocked_tools": ["nikto", "hydra"],
    "nmap_rate_limit": "--max-rate 100",
    "concurrent_connections": 1,
    "request_delay_ms": 500,
    "notes": "Legacy BACnet/Modbus controllers crash under load"
  },
  {
    "category": "iot_sensor",
    "intensity": "safe",
    "blocked_tools": ["nikto", "hydra"],
    "nmap_rate_limit": "--max-rate 50",
    "concurrent_connections": 1,
    "request_delay_ms": 1000,
    "notes": "Minimal CPU/RAM, extremely fragile"
  },
  {
    "category": "intercom",
    "intensity": "safe",
    "blocked_tools": [],
    "nmap_rate_limit": "--max-rate 200",
    "concurrent_connections": 2,
    "request_delay_ms": 200,
    "notes": "SIP stacks can be fragile"
  },
  {
    "category": "generic",
    "intensity": "safe",
    "blocked_tools": ["nikto", "hydra"],
    "nmap_rate_limit": "--max-rate 100",
    "concurrent_connections": 1,
    "request_delay_ms": 500,
    "notes": "Unknown device — be cautious"
  }
]
```

### 4.4 Test Templates

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
    test_definitions JSON NOT NULL,
    cell_mappings JSON,
    is_active BOOLEAN NOT NULL DEFAULT 1,
    created_by TEXT REFERENCES users(id),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_templates_category ON test_templates(device_category);
CREATE INDEX idx_templates_manufacturer ON test_templates(manufacturer_match);
```

### 4.5 Test Runs

```sql
CREATE TABLE test_runs (
    id TEXT PRIMARY KEY,
    device_id TEXT NOT NULL REFERENCES devices(id),
    user_id TEXT NOT NULL REFERENCES users(id),
    agent_id TEXT REFERENCES agents(id),
    template_id TEXT NOT NULL REFERENCES test_templates(id),
    template_version TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'selecting_interface', 'discovering',
                          'running', 'paused_manual', 'paused_cable',
                          'awaiting_review', 'complete', 'error', 'syncing')),
    discovery_results JSON,
    scan_interface TEXT,                         -- Which network interface was used
    start_time TIMESTAMP,
    end_time TIMESTAMP,
    overall_verdict TEXT CHECK (overall_verdict IN ('pass', 'fail', 'advisory', 'incomplete')),
    synopsis_text TEXT,
    synopsis_ai_draft TEXT,
    synopsis_ai_drafted BOOLEAN NOT NULL DEFAULT 0,
    sync_status TEXT NOT NULL DEFAULT 'local'
        CHECK (sync_status IN ('local', 'synced', 'conflict', 'pending_sync')),
    created_offline BOOLEAN NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_runs_device ON test_runs(device_id);
CREATE INDEX idx_runs_user ON test_runs(user_id);
CREATE INDEX idx_runs_status ON test_runs(status);
```

### 4.6 Test Results

```sql
CREATE TABLE test_results (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES test_runs(id),
    test_number TEXT NOT NULL,
    test_name TEXT NOT NULL,
    tier TEXT NOT NULL CHECK (tier IN ('automatic', 'guided_manual', 'auto_na')),
    tool_used TEXT,
    tool_command TEXT,
    raw_stdout TEXT,
    raw_stderr TEXT,
    parsed_findings JSON,
    verdict TEXT NOT NULL DEFAULT 'pending'
        CHECK (verdict IN ('pass', 'fail', 'advisory', 'na', 'info',
                           'pending', 'error', 'skipped_safe_mode')),
    auto_comment TEXT,
    engineer_selection TEXT,
    engineer_notes TEXT,
    is_overridden BOOLEAN NOT NULL DEFAULT 0,
    override_reason TEXT,
    overridden_by TEXT REFERENCES users(id),
    override_timestamp TIMESTAMP,
    original_verdict TEXT,
    execution_time_ms INTEGER,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(run_id, test_number)
);

CREATE INDEX idx_results_run ON test_results(run_id);
CREATE INDEX idx_results_verdict ON test_results(verdict);
```

### 4.7 Attachments

```sql
CREATE TABLE attachments (
    id TEXT PRIMARY KEY,
    result_id TEXT NOT NULL REFERENCES test_results(id),
    file_name TEXT NOT NULL,
    original_name TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    file_path TEXT NOT NULL,
    file_size_bytes INTEGER NOT NULL,
    sha256_hash TEXT NOT NULL,
    upload_source TEXT NOT NULL DEFAULT 'manual'
        CHECK (upload_source IN ('manual', 'auto_screenshot', 'nessus_import')),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_attachments_result ON attachments(result_id);
```

### 4.8 Agents

```sql
CREATE TABLE agents (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    user_id TEXT NOT NULL REFERENCES users(id),
    api_key_hash TEXT NOT NULL,
    os_type TEXT NOT NULL,                      -- "windows", "macos", "linux"
    os_version TEXT,
    agent_version TEXT NOT NULL,
    hostname TEXT,
    last_heartbeat TIMESTAMP,
    status TEXT NOT NULL DEFAULT 'offline'
        CHECK (status IN ('online', 'offline', 'scanning', 'syncing',
                           'error', 'update_required')),
    ip_address TEXT,
    ethernet_interface TEXT,
    pending_sync_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_agents_user ON agents(user_id);
CREATE INDEX idx_agents_status ON agents(status);
```

### 4.9 Audit Logs

```sql
CREATE TABLE audit_logs (
    id TEXT PRIMARY KEY,
    timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    user_id TEXT REFERENCES users(id),
    agent_id TEXT REFERENCES agents(id),
    action TEXT NOT NULL,
    resource_type TEXT,
    resource_id TEXT,
    ip_address TEXT,
    user_agent TEXT,
    details JSON,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_audit_timestamp ON audit_logs(timestamp);
CREATE INDEX idx_audit_user ON audit_logs(user_id);
CREATE INDEX idx_audit_action ON audit_logs(action);
```

### 4.10 Report Configs

```sql
CREATE TABLE report_configs (
    id TEXT PRIMARY KEY,
    client_name TEXT NOT NULL,
    project_name TEXT,
    logo_path TEXT,
    logo_mime_type TEXT,
    compliance_standards JSON NOT NULL DEFAULT '["iso27001", "soc2", "cyber_essentials"]',
    branding_colours JSON,
    header_text TEXT,
    footer_text TEXT,
    ai_synopsis_enabled BOOLEAN NOT NULL DEFAULT 1,  -- Per-client AI toggle
    created_by TEXT REFERENCES users(id),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

### 4.11 Sync Queue

```sql
CREATE TABLE sync_queue (
    id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL REFERENCES agents(id),
    run_id TEXT NOT NULL,
    operation TEXT NOT NULL CHECK (operation IN ('create_run', 'update_run',
                                                  'create_result', 'update_result',
                                                  'upload_attachment')),
    payload JSON NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'syncing', 'synced', 'failed', 'conflict')),
    retry_count INTEGER NOT NULL DEFAULT 0,
    max_retries INTEGER NOT NULL DEFAULT 5,
    error_message TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    synced_at TIMESTAMP
);

CREATE INDEX idx_sync_agent ON sync_queue(agent_id);
CREATE INDEX idx_sync_status ON sync_queue(status);
```

### 4.12 Server Configuration

```sql
CREATE TABLE server_config (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Required keys:
-- 'min_agent_version'        → '1.0.0' (minimum compatible agent version)
-- 'ai_synopsis_global'       → 'true' (global AI toggle)
-- 'default_scan_intensity'   → 'safe'
```

---

## 5. Authentication & Authorisation

### 5.1 Authentication Flow

```
1. POST /api/auth/login { email, password }
   → Validate credentials against bcrypt hash
   → Generate session token (UUID v4)
   → Set httpOnly cookie: edq_session={token}; Secure; SameSite=Strict; Path=/; Max-Age=86400
   → Set CSRF cookie: edq_csrf={random}; Secure; SameSite=Strict; Path=/; Max-Age=86400
   → Store session in Redis: session:{token} → {user_id, role, created_at, last_activity}
   → Generate offline database key (see Section 18.3) and include in response for agent caching
   → Return: { user: { id, email, full_name, role } }

2. All subsequent requests:
   → Middleware reads edq_session cookie
   → Looks up session in Redis
   → If valid and last_activity < 15 min ago: update last_activity, proceed
   → If expired: delete session, return 401
   → For POST/PUT/DELETE: also validate X-CSRF-Token header matches edq_csrf cookie

3. POST /api/auth/logout
   → Delete session from Redis
   → Clear cookies
```

### 5.2 Agent Authentication

```
1. Agent registration (one-time, via web UI):
   → Admin generates agent API key via POST /api/admin/agents
   → Key format: edq_agent_{uuid4} (displayed once, never stored in plaintext)
   → bcrypt hash of key stored in agents.api_key_hash

2. Agent requests:
   → Authorization: Bearer edq_agent_{key}
   → Server validates: bcrypt.checkpw(key, stored_hash)

3. Heartbeat version check:
   → Agent sends agent_version in heartbeat
   → Server compares to server_config.min_agent_version
   → Response includes: { "version_status": "compatible" | "deprecated" | "incompatible" }
   → "deprecated": warning banner, all features work
   → "incompatible": block new job polling, allow offline testing, show update prompt
   → NEVER lock out the agent entirely — offline capability must be preserved
```

### 5.3 Role Permissions

| Endpoint Group | Admin | Tester | Reviewer |
|---|---|---|---|
| View dashboard | ✅ | ✅ | ✅ |
| Create/manage devices | ✅ | ✅ | ❌ |
| Start test runs | ✅ | ✅ | ❌ |
| Complete manual tests | ✅ | ✅ | ❌ |
| Override test verdicts | ✅ | ❌ | ✅ |
| Approve synopses | ✅ | ❌ | ✅ |
| Generate reports | ✅ | ✅ | ✅ |
| Manage users | ✅ | ❌ | ❌ |
| Manage templates | ✅ | ❌ | ❌ |
| Manage device profiles | ✅ | ❌ | ❌ |
| Manage report configs | ✅ | ❌ | ✅ |
| View audit logs | ✅ | ❌ | ✅ |
| Register agents | ✅ | ✅ | ❌ |
| Toggle AI synopsis | ✅ | ❌ | ❌ |

### 5.4 Password Requirements

- Minimum 12 characters
- At least one uppercase, one lowercase, one digit, one special character
- bcrypt cost factor: 12

---

## 6. API Specification

### 6.1 Auth Endpoints

```
POST   /api/auth/login
POST   /api/auth/logout
GET    /api/auth/me
POST   /api/auth/change-password
```

### 6.2 User Management (Admin only)

```
GET    /api/users
POST   /api/users
GET    /api/users/{id}
PUT    /api/users/{id}
DELETE /api/users/{id}
```

### 6.3 Device Endpoints

```
GET    /api/devices
POST   /api/devices
GET    /api/devices/{id}
PUT    /api/devices/{id}
DELETE /api/devices/{id}
POST   /api/devices/{id}/discover        # Trigger auto-discovery
GET    /api/devices/{id}/runs
```

### 6.4 Discovery Endpoints

```
POST   /api/discovery/scan-network        # Scan subnet for all devices
POST   /api/discovery/find-device         # ARP sweep for hardcoded static IP device
GET    /api/discovery/{job_id}
```

### 6.5 Test Template Endpoints

```
GET    /api/templates
POST   /api/templates
GET    /api/templates/{id}
PUT    /api/templates/{id}
DELETE /api/templates/{id}
POST   /api/templates/import              # Upload Excel → create template draft
POST   /api/templates/{id}/cell-mapping
GET    /api/templates/match               # Auto-match by category + manufacturer
```

### 6.6 Test Run Endpoints

```
GET    /api/runs
POST   /api/runs
GET    /api/runs/{id}
PUT    /api/runs/{id}/status
POST   /api/runs/{id}/pause
POST   /api/runs/{id}/resume
GET    /api/runs/{id}/results
GET    /api/runs/{id}/progress
```

### 6.7 Test Result Endpoints

```
GET    /api/results/{id}
PUT    /api/results/{id}/manual           # Submit guided manual test
PUT    /api/results/{id}/override         # Override verdict (reviewer only)
POST   /api/results/{id}/attachments      # Upload evidence
GET    /api/results/{id}/attachments
GET    /api/attachments/{id}/download
```

### 6.8 Report Endpoints

```
POST   /api/reports/excel/{run_id}        # Generate Excel (synchronous)
POST   /api/reports/word/{run_id}         # Generate Word (synchronous)
POST   /api/reports/pdf/{run_id}          # Queue PDF generation (async, returns job_id)
GET    /api/reports/pdf-status/{job_id}   # Poll PDF job status
GET    /api/reports/download/{token}      # Download report (time-limited token)
GET    /api/report-configs
POST   /api/report-configs
PUT    /api/report-configs/{id}
POST   /api/report-configs/{id}/logo
```

### 6.9 Synopsis Endpoints

```
POST   /api/synopsis/{run_id}/draft       # Generate AI draft (if enabled)
GET    /api/synopsis/{run_id}/draft
PUT    /api/synopsis/{run_id}/approve
```

### 6.10 Agent Communication Endpoints

```
POST   /api/agent/register
POST   /api/agent/heartbeat               # Includes version check response
GET    /api/agent/jobs/{agent_id}
POST   /api/agent/discovery-result
POST   /api/agent/scan-result
POST   /api/agent/scan-complete
POST   /api/agent/stream
POST   /api/agent/attachment
GET    /api/agent/interfaces/{agent_id}   # Get available network interfaces
```

### 6.11 Sync Endpoints

```
POST   /api/sync/upload
GET    /api/sync/status/{agent_id}
GET    /api/sync/conflicts
POST   /api/sync/resolve/{id}
```

### 6.12 Admin Endpoints

```
GET    /api/admin/agents
POST   /api/admin/agents
DELETE /api/admin/agents/{id}
GET    /api/admin/audit-logs
GET    /api/admin/system-health
GET    /api/admin/device-profiles
POST   /api/admin/device-profiles
PUT    /api/admin/device-profiles/{id}
GET    /api/admin/config                  # Get server config (min_agent_version, etc.)
PUT    /api/admin/config                  # Update server config
```

### 6.13 WebSocket Endpoints

```
WS     /api/ws/terminal/{run_id}
WS     /api/ws/progress/{run_id}
WS     /api/ws/agent-status
WS     /api/ws/pdf-status/{job_id}       # Notify when PDF is ready
```

### 6.14 Standard Response Formats

**Success:**
```json
{ "status": "success", "data": { } }
```

**Paginated list:**
```json
{
  "status": "success",
  "data": [ ],
  "pagination": { "page": 1, "page_size": 25, "total_items": 142, "total_pages": 6 }
}
```

**Error:**
```json
{
  "status": "error",
  "error": { "code": "VALIDATION_ERROR", "message": "Human-readable description", "details": { } }
}
```

**Error codes:** `VALIDATION_ERROR`, `AUTH_REQUIRED`, `FORBIDDEN`, `NOT_FOUND`, `CONFLICT`, `RATE_LIMITED`, `AGENT_OFFLINE`, `AGENT_UPDATE_REQUIRED`, `SYNC_CONFLICT`, `TEMPLATE_MISMATCH`, `FILE_INVALID`, `GENERATION_FAILED`, `AI_DISABLED`, `SAFE_MODE_BLOCKED`, `INTERNAL_ERROR`

---

## 7. Auto-Discovery Pipeline

### 7.1 Trigger

Discovery starts when:
- Engineer creates a new device via `POST /api/devices` with an IP address
- Engineer clicks "Re-discover" on an existing device
- Agent performs subnet scan via `POST /api/discovery/scan-network`
- Agent performs ARP sweep via `POST /api/discovery/find-device` (for unknown/static IP devices)

### 7.2 Interface Selection (Mandatory First Step)

**Before any scanning begins, the engineer must select which network interface to use.**

A laptop may have: WiFi (corporate network), Ethernet (device under test), USB-C dock ethernet, VPN adapter. Auto-detection will guess wrong and either scan the corporate network (security incident) or scan nothing.

```
┌─────────────────────────────────────────────────────┐
│  SELECT SCANNING INTERFACE                          │
│                                                      │
│  Which network interface is connected to the device? │
│                                                      │
│  ○ Ethernet (Intel I219-V)     - Link UP             │
│      192.168.1.100 / 255.255.255.0                   │
│                                                      │
│  ○ Wi-Fi (Intel AX201)         - Link UP             │
│      10.50.2.45 / 255.255.0.0                        │
│      ⚠️ Warning: This appears to be a corporate      │
│         network. Scanning this interface may          │
│         trigger security alerts.                     │
│                                                      │
│  ○ USB Ethernet (Realtek)      - Link DOWN           │
│      No IP assigned                                  │
│                                                      │
│  [Continue with selected interface]                  │
└─────────────────────────────────────────────────────┘
```

**Implementation:**

```python
class InterfaceManager:
    def list_interfaces(self) -> list[NetworkInterface]:
        """List all network interfaces with status."""
        interfaces = []
        for iface_name, addrs in psutil.net_if_addrs().items():
            stats = psutil.net_if_stats().get(iface_name)
            iface = NetworkInterface(
                name=iface_name,
                display_name=self._get_friendly_name(iface_name),
                is_up=stats.isup if stats else False,
                speed_mbps=stats.speed if stats else 0,
                ipv4=None,
                subnet_mask=None,
                mac_address=None,
                is_wireless=self._is_wireless(iface_name),
                warning=None
            )
            for addr in addrs:
                if addr.family == socket.AF_INET:
                    iface.ipv4 = addr.address
                    iface.subnet_mask = addr.netmask
                if addr.family == psutil.AF_LINK:
                    iface.mac_address = addr.address

            # Warning if this looks like a corporate/internet network
            if iface.ipv4 and not iface.ipv4.startswith(('192.168.', '10.', '172.16.')):
                iface.warning = "This appears to be a public-facing interface."
            elif iface.is_wireless:
                iface.warning = "This is a wireless interface. Scanning via WiFi is not recommended."

            interfaces.append(iface)
        return interfaces
```

The selected interface is stored in `test_runs.scan_interface` and used for all subsequent tool commands.

### 7.3 Device IP Detection

Three modes, tried in sequence if the engineer doesn't provide an IP:

**Mode 1: Engineer provides IP address.** Skip to fingerprinting (Section 7.4).

**Mode 2: DHCP Server (for devices that request an IP via DHCP).**

The agent does NOT just listen for DHCP — it actively runs a lightweight DHCP server that hands the device an IP address. Without this, a DHCP-enabled device plugged directly into the laptop will never get onto the network.

```python
from python_dhcp_server import DHCPServer

class DeviceDHCPServer:
    """Lightweight DHCP server that assigns IPs to devices during discovery.
    
    When a device with DHCP enabled is plugged into the laptop, it sends a
    DHCP DISCOVER broadcast. This server responds with a DHCP OFFER, assigning
    the device an IP address on a private subnet. The agent then fingerprints
    the assigned IP.
    
    The DHCP server runs ONLY during discovery and is shut down immediately
    after the device is identified.
    """

    SUBNET = "192.168.88.0/24"
    SERVER_IP = "192.168.88.1"
    POOL_START = "192.168.88.50"
    POOL_END = "192.168.88.99"
    LEASE_TIME = 300  # 5 minutes

    def __init__(self, interface: str, network_guard: 'NetworkGuard'):
        self.interface = interface
        self.network_guard = network_guard
        self.assigned_ips = {}  # MAC → IP mapping
        self._server = None

    async def start_and_wait(self, timeout: int = 30) -> str | None:
        """Assign interface a static IP, start DHCP server, wait for first client.
        
        Returns the IP assigned to the device, or None if timeout.
        """
        # 1. Set our interface to the server IP (via NetworkGuard for crash safety)
        self.network_guard.modify_interface(
            self.interface, self.SERVER_IP, "255.255.255.0"
        )

        # 2. Start DHCP server
        self._server = DHCPServer(
            interface=self.interface,
            server_ip=self.SERVER_IP,
            pool_start=self.POOL_START,
            pool_end=self.POOL_END,
            subnet_mask="255.255.255.0",
            lease_time=self.LEASE_TIME,
            on_lease=self._on_lease
        )
        self._server.start()

        # 3. Wait for first lease (device connecting)
        try:
            async with asyncio.timeout(timeout):
                while not self.assigned_ips:
                    await asyncio.sleep(0.5)
        except asyncio.TimeoutError:
            self._server.stop()
            return None

        # 4. Return the first assigned IP
        device_ip = list(self.assigned_ips.values())[0]
        # Keep DHCP server running during the test (device may renew lease)
        return device_ip

    def _on_lease(self, mac: str, ip: str):
        """Callback when DHCP lease is granted."""
        self.assigned_ips[mac] = ip

    def stop(self):
        if self._server:
            self._server.stop()
```

**Mode 3: ARP Sweep (for devices with hardcoded static IPs and APIPA fallback).**

If no DHCP request is received within the Mode 2 timeout, the agent assumes the device has a hardcoded static IP. It sweeps common default subnets:

```python
class ARPSweeper:
    """Finds devices with hardcoded static IPs that never send DHCP."""

    DEFAULT_SUBNETS = [
        ("192.168.1.0/24",  "192.168.1.200"),   # Most common IoT default
        ("192.168.0.0/24",  "192.168.0.200"),
        ("10.0.0.0/24",     "10.0.0.200"),
        ("172.16.0.0/24",   "172.16.0.200"),
        ("192.168.2.0/24",  "192.168.2.200"),
        ("169.254.0.0/16",  "169.254.1.1"),      # APIPA: device fell back to link-local
    ]

    async def sweep(self, interface: str, network_guard: 'NetworkGuard') -> list[DiscoveredDevice]:
        """Try each default subnet. Assign self an IP, ARP broadcast, listen."""
        found_devices = []

        for subnet, self_ip in self.DEFAULT_SUBNETS:
            # Temporarily assign ourselves an IP on this subnet (crash-safe)
            subnet_mask = "255.255.255.0"
            if subnet.startswith("169.254."):
                subnet_mask = "255.255.0.0"  # /16 for APIPA

            network_guard.modify_interface(interface, self_ip, subnet_mask)
            await asyncio.sleep(2)  # Let ARP tables settle

            # ARP broadcast
            result = await self.nmap_runner.execute(
                f"-sn -PR --send-eth {subnet}",
                interface=interface, timeout=20
            )
            devices = self.nmap_parser.parse_hosts(result.stdout)

            if devices:
                found_devices.extend(devices)
                break  # Found something, stop sweeping

        return found_devices
```

**Combined discovery flow:**

```python
class DeviceDiscovery:
    """Orchestrates all three IP detection modes."""

    async def find_device(self, interface: str, ip_address: str = None) -> DiscoveryResult:
        if ip_address:
            # Mode 1: Direct IP provided
            return await self.fingerprinter.fingerprint(ip_address, interface)

        # Mode 2: Try DHCP server first (30 second timeout)
        dhcp = DeviceDHCPServer(interface, self.network_guard)
        device_ip = await dhcp.start_and_wait(timeout=30)

        if device_ip:
            result = await self.fingerprinter.fingerprint(device_ip, interface)
            result.discovery_method = "dhcp_server"
            return result

        # Mode 3: No DHCP response — try ARP sweep of default subnets + APIPA
        dhcp.stop()
        sweeper = ARPSweeper()
        devices = await sweeper.sweep(interface, self.network_guard)

        if devices:
            # Pick the first device found
            device = devices[0]
            result = await self.fingerprinter.fingerprint(device.ip, interface)
            result.discovery_method = "arp_sweep"
            return result

        # Nothing found
        raise DeviceNotFoundError(
            "No device detected on this interface. "
            "Please check the cable connection and try again, "
            "or enter the device IP address manually."
        )
```

**UI for all three modes:**

```
┌──────────────────────────────────────────────┐
│  DEVICE DISCOVERY                            │
│                                               │
│  How would you like to find the device?       │
│                                               │
│  [Enter IP Address]  [Scan Network]  [Auto]  │
│                                               │
│  "Auto" will try DHCP server first,           │
│  then sweep common default subnets + APIPA.   │
│  Takes up to 60 seconds.                     │
└──────────────────────────────────────────────┘
```

### 7.4 Fingerprinting Sequence (After IP is Known)

Executes automatically in 30–60 seconds, respecting the device profile's scan policy:

```python
class DeviceFingerprinter:
    async def fingerprint(self, ip: str, interface: str, scan_policy: dict) -> DiscoveryResult:
        result = DiscoveryResult(ip=ip)
        rate_limit = scan_policy.get("nmap_rate_limit", "--max-rate 200")

        # Step 1: ARP Resolution (2-3 seconds)
        result.mac_address = await self.arp_resolve(ip, interface)
        result.vendor = self.oui_lookup(result.mac_address)

        # Step 2: Port Scan (15-30 seconds, rate-limited per scan_policy)
        nmap_result = await self.nmap_runner.execute(
            f"-sS -sV --top-ports 1000 -p 47808,502,554,1883,5060,5061,5683,8883 "
            f"-O --osscan-limit {rate_limit} {ip}",
            interface=interface, timeout=60
        )
        result.open_ports = self.nmap_parser.parse_ports(nmap_result.stdout)
        result.os_guess = self.nmap_parser.parse_os(nmap_result.stdout)

        # Step 3: Service Fingerprinting (5-10 seconds per service)
        for port_info in result.open_ports:
            if port_info.service in ('http', 'https', 'ssl/http'):
                result.http_info = await self.grab_http_headers(ip, port_info.port)
            if port_info.service in ('ssl', 'https', 'ssl/http'):
                result.tls_info = await self.sslyze_quick_scan(ip, port_info.port)
            if port_info.service == 'ssh':
                result.ssh_info = await self.grab_ssh_banner(ip, port_info.port)

        # Step 4: Device Category Inference
        result.device_category = self.category_classifier.classify(result)

        # Step 5: Template Matching (done server-side)
        return result
```

### 7.5 Category Classification Rules

```python
CLASSIFICATION_RULES = [
    {
        "category": "camera",
        "rules": [
            {"type": "port_service", "port": 554, "service": "rtsp"},
            {"type": "port_path", "port": 80, "path": "/onvif/device_service"},
            {"type": "banner_contains", "values": ["Hikvision", "Dahua", "Pelco", "Axis", "Bosch"]},
            {"type": "mac_prefix", "values": ["00:04:7D", "28:57:BE", "4C:BD:8F"]},
        ],
        "min_confidence": 1
    },
    {
        "category": "controller",
        "rules": [
            {"type": "port_service", "port": 47808, "service": "bacnet"},
            {"type": "port_service", "port": 502, "service": "modbus"},
            {"type": "banner_contains", "values": ["BACnet", "EasyIO", "Sauter", "Siemens"]},
        ],
        "min_confidence": 1
    },
    {
        "category": "intercom",
        "rules": [
            {"type": "port_service", "port": 5060, "service": "sip"},
            {"type": "port_service", "port": 5061, "service": "sips"},
            {"type": "banner_contains", "values": ["2N", "Aiphone", "Doorbird"]},
        ],
        "min_confidence": 1
    },
    {
        "category": "iot_sensor",
        "rules": [
            {"type": "port_service", "port": 1883, "service": "mqtt"},
            {"type": "port_service", "port": 8883, "service": "mqtt/ssl"},
            {"type": "port_service", "port": 5683, "service": "coap"},
        ],
        "min_confidence": 1
    },
    { "category": "generic", "rules": [], "min_confidence": 0 }
]
```

### 7.6 Discovery Result Schema

```json
{
  "ip_address": "192.168.1.50",
  "mac_address": "00:04:7D:D7:D1:58",
  "vendor": "Motorola Solutions Inc.",
  "manufacturer_guess": "Pelco",
  "device_category": "camera",
  "category_confidence": "high",
  "discovery_method": "direct_ip",
  "open_ports": [
    {"port": 22, "protocol": "tcp", "state": "open", "service": "ssh", "version": "OpenSSH 8.2"},
    {"port": 80, "protocol": "tcp", "state": "open", "service": "http", "version": "lighttpd/1.4.55"},
    {"port": 443, "protocol": "tcp", "state": "open", "service": "ssl/http", "version": "lighttpd/1.4.55"},
    {"port": 554, "protocol": "tcp", "state": "open", "service": "rtsp", "version": ""}
  ],
  "os_guess": "Linux 4.15 - 5.8",
  "http_info": {
    "server": "lighttpd/1.4.55",
    "headers": { "X-Frame-Options": "SAMEORIGIN", "Content-Security-Policy": null, "Strict-Transport-Security": null },
    "title": "Pelco Camera Web Interface"
  },
  "tls_info": {
    "versions_supported": ["TLSv1.2", "TLSv1.3"],
    "certificate": { "subject": "CN=camera.local", "issuer": "CN=camera.local", "valid_from": "2024-01-01", "valid_to": "2025-01-01", "self_signed": true },
    "scan_tool": "sslyze"
  },
  "ssh_info": { "version": "OpenSSH_8.2p1", "key_types": ["ssh-ed25519", "ssh-rsa"] },
  "scan_duration_seconds": 42,
  "scan_policy_used": "safe"
}
```

---

## 8. Three-Tier Test Engine

### 8.1 Orchestration Flow

```
START
  │
  ├─ 1. Interface Selection (engineer picks ethernet interface)
  ├─ 2. Device IP Detection (entered, DHCP server, or ARP sweep)
  ├─ 3. Load device fingerprint (from discovery)
  ├─ 4. Load scan_policy from device profile
  ├─ 5. Load template test definitions + profile extensions
  │
  ├─ 6. TIER 3: Auto-N/A Pass
  │     For each test: check prereq_rules against fingerprint
  │     If prereqs not met → stamp N/A with auto_comment
  │
  ├─ 7. SAFE MODE CHECK
  │     For each remaining automatic test:
  │       If scan_policy blocks the test's tool → stamp as "skipped_safe_mode"
  │       Comment: "Test skipped: Device profile requires safe mode. Tool {tool} is
  │                 blocked for {category} devices to prevent device instability."
  │
  ├─ 8. TIER 1: Automatic Execution (respecting scan_policy rate limits)
  │     For each remaining automatic test:
  │       a. Connectivity check (Wobbly Cable)
  │       b. Execute tool with scan_policy rate limits
  │       c. Parse output → structured findings
  │       d. Evaluate findings against rules → verdict
  │       e. Generate comment from template
  │       f. Stream progress to WebSocket
  │
  ├─ 9. Status → paused_manual
  │
  ├─ 10. TIER 2: Guided Manual (engineer single-click decisions)
  │
  ├─ 11. Calculate overall_verdict
  │
  ├─ 12. Status → awaiting_review OR complete
  │
  └─ 13. Report generation available
```

### 8.2 Scan Policy Enforcement

```python
class ScanPolicyEnforcer:
    """Checks if a tool/test is allowed under the device's scan policy."""

    def can_execute(self, test: TestDefinition, policy: dict) -> tuple[bool, str]:
        tool = test.tool
        blocked = policy.get("blocked_tools", [])

        if tool in blocked:
            return False, f"Tool '{tool}' blocked by scan policy for this device category."

        return True, ""

    def get_nmap_args(self, base_args: str, policy: dict) -> str:
        """Inject rate limiting into nmap commands."""
        rate_limit = policy.get("nmap_rate_limit", "--max-rate 200")
        if "--max-rate" not in base_args and "--min-rate" not in base_args:
            base_args += f" {rate_limit}"
        return base_args

    def get_delay(self, policy: dict) -> float:
        """Inter-test delay in seconds."""
        return policy.get("request_delay_ms", 200) / 1000.0
```

### 8.3 Prerequisite Rules for Auto-N/A

```json
[
  {"prereq_type": "port_open", "port": 22, "comment_if_na": "SSH service not detected."},
  {"prereq_type": "service_detected", "service": "rtsp", "comment_if_na": "RTSP not running."},
  {"prereq_type": "category_match", "categories": ["controller"], "comment_if_na": "Not applicable to this device category."},
  {"prereq_type": "file_uploaded", "file_type": "nessus", "comment_if_na": "Nessus scan not performed."},
  {"prereq_type": "tls_detected", "comment_if_na": "No TLS/SSL service detected."}
]
```

### 8.4 Verdict Calculation

```python
def calculate_overall_verdict(results: list[TestResult]) -> str:
    has_pending = any(r.verdict == "pending" for r in results)
    has_essential_fail = any(r.verdict == "fail" and r.essential_pass for r in results)
    has_non_essential_fail = any(r.verdict == "fail" and not r.essential_pass for r in results)
    has_advisory = any(r.verdict == "advisory" for r in results)

    if has_pending:
        return "incomplete"
    if has_essential_fail:
        return "fail"
    if has_non_essential_fail or has_advisory:
        return "advisory"
    return "pass"
```

---

## 9. Universal Test Library

25 tests that apply to every IP device. Each test below includes: tool, exact arguments, parser field references, evaluation rules with explicit pass/fail/advisory criteria, auto-generated comment templates, and prerequisites.

**Notation:**
- `{ip}` = device IP address
- `{rate_limit}` = filled from scan_policy (e.g., `--max-rate 200`)
- `{interface}` = selected network interface name
- `{open_ports}` = comma-separated list from discovery
- `{tls_port}` = first discovered TLS port (443, 8443, etc.)
- `{ssh_port}` = discovered SSH port (usually 22)
- `{http_port}` = discovered HTTP port (80, 8080, etc.)

---

#### U01: Ping Response

```json
{
  "test_id": "U01",
  "name": "Ping Response",
  "description": "Verify device responds to ICMP echo requests",
  "tier": "automatic",
  "essential_pass": true,
  "tool": "nmap",
  "tool_args": "-sn -PE {ip}",
  "timeout_seconds": 10,
  "parser": "nmap_ping",
  "eval_rules": {
    "type": "field_equals",
    "field": "parsed.host_status",
    "pass_value": "up",
    "fail_value": "down"
  },
  "comment_template": {
    "pass": "Device at {ip} responded to ICMP ping. Host is up. Latency: {parsed.latency}ms.",
    "fail": "Device at {ip} did not respond to ICMP ping. Host appears down or ICMP is blocked."
  },
  "prereq_rules": null,
  "compliance_map": ["Baseline"],
  "requires_safe_mode_override": false
}
```

#### U02: MAC Address Vendor Lookup

```json
{
  "test_id": "U02",
  "name": "MAC Address Vendor Lookup",
  "description": "Identify device manufacturer via IEEE OUI database",
  "tier": "automatic",
  "essential_pass": true,
  "tool": "nmap",
  "tool_args": "-sn -PR {ip}",
  "timeout_seconds": 10,
  "parser": "nmap_arp",
  "eval_rules": {
    "type": "field_not_empty",
    "field": "parsed.vendor",
    "pass_verdict": "pass",
    "fail_verdict": "advisory"
  },
  "comment_template": {
    "pass": "MAC: {parsed.mac_address}. Vendor: {parsed.vendor}. OUI database version: {oui_version}.",
    "advisory": "MAC: {parsed.mac_address}. Vendor not found in IEEE OUI database. May indicate a newly registered or locally administered MAC."
  },
  "prereq_rules": null,
  "compliance_map": ["ISO 27001 A.12.6"],
  "requires_safe_mode_override": false
}
```

#### U03: Switch Negotiation (Speed/Duplex)

```json
{
  "test_id": "U03",
  "name": "Switch Negotiation (Speed/Duplex)",
  "description": "Verify ethernet link negotiation parameters",
  "tier": "automatic",
  "essential_pass": false,
  "tool": "ethtool_or_wmic",
  "tool_args_linux": "ethtool {interface}",
  "tool_args_windows": "wmic nic where \"NetConnectionID='{interface}'\" get Speed,Name",
  "timeout_seconds": 5,
  "parser": "link_speed",
  "eval_rules": {
    "type": "field_in_set",
    "field": "parsed.speed",
    "pass_values": ["1000Mb/s", "2500Mb/s", "10000Mb/s", "1000000000", "2500000000"],
    "advisory_values": ["100Mb/s", "100000000"],
    "fail_values": ["10Mb/s", "10000000"]
  },
  "comment_template": {
    "pass": "Link negotiated at {parsed.speed} {parsed.duplex} duplex. Auto-negotiation: {parsed.autoneg}.",
    "advisory": "Link negotiated at {parsed.speed}. Speed is 100Mbps — acceptable but may limit throughput.",
    "fail": "Link negotiated at {parsed.speed}. 10Mbps is suboptimal for modern IP devices."
  },
  "prereq_rules": null,
  "compliance_map": ["Baseline"],
  "requires_safe_mode_override": false
}
```

#### U04: DHCP Behaviour

```json
{
  "test_id": "U04",
  "name": "DHCP Behaviour",
  "description": "Determine if device uses DHCP or static IP assignment",
  "tier": "automatic",
  "essential_pass": false,
  "tool": "discovery_metadata",
  "tool_args": null,
  "timeout_seconds": 0,
  "parser": "discovery_method",
  "eval_rules": {
    "type": "field_in_set",
    "field": "discovery.discovery_method",
    "pass_values": ["dhcp_server", "direct_ip"],
    "info_values": ["arp_sweep"]
  },
  "comment_template": {
    "pass": "Device obtained IP via DHCP. Dynamic addressing supported.",
    "info": "Device has a hardcoded static IP ({ip}). Found via ARP sweep on subnet {parsed.subnet}. Static IP configuration may complicate network integration."
  },
  "prereq_rules": null,
  "compliance_map": ["Baseline"],
  "requires_safe_mode_override": false
}
```

#### U05: IPv6 Support Detection

```json
{
  "test_id": "U05",
  "name": "IPv6 Support Detection",
  "description": "Check if device has an IPv6 address or responds to IPv6",
  "tier": "automatic",
  "essential_pass": false,
  "tool": "nmap",
  "tool_args": "-6 -sn --script=targets-ipv6-multicast-echo {rate_limit} {interface_flag}",
  "timeout_seconds": 15,
  "parser": "nmap_ipv6",
  "eval_rules": {
    "type": "ipv6_detection",
    "ipv6_found": "info",
    "ipv6_not_found": "info"
  },
  "comment_template": {
    "info_found": "Device has IPv6 enabled. Link-local address: {parsed.ipv6_address}. Dual-stack operation detected. Ensure IPv6 firewall rules are configured.",
    "info_not_found": "No IPv6 address detected on this device. IPv4 only."
  },
  "prereq_rules": null,
  "compliance_map": ["ISO 27001 A.13.1.1"],
  "requires_safe_mode_override": false
}
```

#### U06: Full TCP Port Scan

```json
{
  "test_id": "U06",
  "name": "Full TCP Port Scan (All 65535 Ports)",
  "description": "Discover all open TCP ports on the device",
  "tier": "automatic",
  "essential_pass": true,
  "tool": "nmap",
  "tool_args": "-sS -p- {rate_limit} {ip}",
  "timeout_seconds": 300,
  "parser": "nmap_ports",
  "eval_rules": {
    "type": "port_count_threshold",
    "max_expected_ports": 20,
    "pass_condition": "open_port_count <= max_expected_ports",
    "advisory_condition": "open_port_count > max_expected_ports",
    "always_pass": true,
    "note": "This test always passes but flags advisory if unusually many ports are open. The port list feeds into U09 whitelist check."
  },
  "comment_template": {
    "pass": "{parsed.open_port_count} open TCP ports detected: {parsed.port_list}.",
    "advisory": "{parsed.open_port_count} open TCP ports detected (unusually high). Full list: {parsed.port_list}. Review for unnecessary services."
  },
  "prereq_rules": null,
  "compliance_map": ["ISO 27001 A.13.1.1", "Cyber Essentials"],
  "requires_safe_mode_override": false
}
```

#### U07: UDP Top-100 Port Scan

```json
{
  "test_id": "U07",
  "name": "UDP Top-100 Port Scan",
  "description": "Discover open UDP services",
  "tier": "automatic",
  "essential_pass": false,
  "tool": "nmap",
  "tool_args": "-sU --top-ports 100 {rate_limit} {ip}",
  "timeout_seconds": 180,
  "parser": "nmap_ports",
  "eval_rules": {
    "type": "port_list_report",
    "always_pass": true,
    "note": "UDP scan is informational. Feeds into whitelist check (U09)."
  },
  "comment_template": {
    "pass": "{parsed.open_udp_count} open/filtered UDP ports detected: {parsed.udp_port_list}."
  },
  "prereq_rules": null,
  "compliance_map": ["ISO 27001 A.13.1.1"],
  "requires_safe_mode_override": false
}
```

#### U08: Service Version Detection

```json
{
  "test_id": "U08",
  "name": "Service Version Detection",
  "description": "Identify software versions on all open ports",
  "tier": "automatic",
  "essential_pass": false,
  "tool": "nmap",
  "tool_args": "-sV -p {open_ports} {rate_limit} {ip}",
  "timeout_seconds": 120,
  "parser": "nmap_services",
  "eval_rules": {
    "type": "service_version_check",
    "always_pass": true,
    "note": "Informational. Records software versions for the report."
  },
  "comment_template": {
    "pass": "Service versions identified: {parsed.service_summary}."
  },
  "prereq_rules": null,
  "compliance_map": ["ISO 27001 A.12.6"],
  "requires_safe_mode_override": false
}
```

#### U09: Protocol Whitelist Compliance

```json
{
  "test_id": "U09",
  "name": "Protocol Whitelist Compliance",
  "description": "Compare discovered ports/services against template-defined expected services",
  "tier": "automatic",
  "essential_pass": false,
  "tool": "custom_rules",
  "tool_args": null,
  "timeout_seconds": 0,
  "parser": "whitelist_comparator",
  "eval_rules": {
    "type": "whitelist_match",
    "input_a": "parsed.all_open_ports",
    "input_b": "template.expected_ports",
    "pass_condition": "no unexpected ports found",
    "advisory_condition": "unexpected ports found but not high-risk",
    "fail_condition": "unexpected high-risk ports found (telnet:23, ftp:21, tftp:69, snmp_default:161)"
  },
  "comment_template": {
    "pass": "All open ports match the expected service profile for this device category. No unexpected services detected.",
    "advisory": "Unexpected ports detected: {parsed.unexpected_ports}. These services are not in the expected profile for {device_category} devices. Review with manufacturer.",
    "fail": "HIGH RISK: Unexpected insecure services detected: {parsed.unexpected_ports}. Services such as Telnet, FTP, or TFTP represent significant security risks."
  },
  "prereq_rules": null,
  "compliance_map": ["ISO 27001 A.13.1.1", "Cyber Essentials", "SOC2 CC6.1"],
  "requires_safe_mode_override": false
}
```

#### U10: TLS Version Assessment

```json
{
  "test_id": "U10",
  "name": "TLS Version Assessment",
  "description": "Check supported TLS/SSL protocol versions",
  "tier": "automatic",
  "essential_pass": true,
  "tool": "sslyze",
  "tool_args": "--tlsv1_0 --tlsv1_1 --tlsv1_2 --tlsv1_3 --sslv2 --sslv3 {ip}:{tls_port}",
  "timeout_seconds": 60,
  "parser": "sslyze_protocols",
  "eval_rules": {
    "type": "tls_version_policy",
    "fail_if_any": ["SSLv2", "SSLv3"],
    "advisory_if_any": ["TLSv1.0", "TLSv1.1"],
    "pass_if_all_in": ["TLSv1.2", "TLSv1.3"],
    "best_if": ["TLSv1.3"]
  },
  "comment_template": {
    "pass": "Supported TLS versions: {parsed.versions_list}. All versions meet current security standards.",
    "advisory": "Supported TLS versions: {parsed.versions_list}. WARNING: Legacy protocols detected ({parsed.legacy_versions}). These should be disabled. TLS 1.2+ recommended.",
    "fail": "CRITICAL: Obsolete protocols detected: {parsed.obsolete_versions}. SSLv2/SSLv3 are fundamentally broken and must be disabled immediately."
  },
  "prereq_rules": {"prereq_type": "tls_detected"},
  "compliance_map": ["ISO 27001 A.14.1.2", "Cyber Essentials", "SOC2 CC6.7"],
  "requires_safe_mode_override": false
}
```

#### U11: Cipher Suite Strength

```json
{
  "test_id": "U11",
  "name": "Cipher Suite Strength",
  "description": "Evaluate cipher suites for weak or insecure algorithms",
  "tier": "automatic",
  "essential_pass": false,
  "tool": "sslyze",
  "tool_args": "--tlsv1_2 --tlsv1_3 {ip}:{tls_port}",
  "timeout_seconds": 60,
  "parser": "sslyze_ciphers",
  "eval_rules": {
    "type": "cipher_policy",
    "fail_ciphers": ["RC4", "DES", "3DES", "NULL", "EXPORT", "anon"],
    "advisory_ciphers": ["CBC"],
    "pass_ciphers": ["AESGCM", "CHACHA20", "AES256-GCM", "AES128-GCM"]
  },
  "comment_template": {
    "pass": "All cipher suites use strong algorithms. Strongest: {parsed.strongest_cipher}. {parsed.cipher_count} suites accepted.",
    "advisory": "Weak cipher suites detected: {parsed.weak_ciphers}. CBC mode ciphers are vulnerable to padding oracle attacks. Recommend GCM mode exclusively.",
    "fail": "CRITICAL: Insecure cipher suites detected: {parsed.insecure_ciphers}. RC4, DES, NULL, EXPORT, and anonymous ciphers must be disabled."
  },
  "prereq_rules": {"prereq_type": "tls_detected"},
  "compliance_map": ["ISO 27001 A.14.1.2", "Cyber Essentials"],
  "requires_safe_mode_override": false
}
```

#### U12: Certificate Validity

```json
{
  "test_id": "U12",
  "name": "Certificate Validity",
  "description": "Check certificate chain, expiry, and trust",
  "tier": "automatic",
  "essential_pass": false,
  "tool": "sslyze",
  "tool_args": "--certinfo {ip}:{tls_port}",
  "timeout_seconds": 30,
  "parser": "sslyze_certificate",
  "eval_rules": {
    "type": "certificate_checks",
    "checks": {
      "expired": {"condition": "parsed.days_until_expiry < 0", "verdict": "fail"},
      "expiring_soon": {"condition": "parsed.days_until_expiry < 30", "verdict": "advisory"},
      "self_signed": {"condition": "parsed.is_self_signed == true", "verdict": "advisory"},
      "weak_signature": {"condition": "parsed.signature_algorithm in ['sha1WithRSAEncryption', 'md5WithRSAEncryption']", "verdict": "fail"},
      "short_key": {"condition": "parsed.key_size < 2048", "verdict": "fail"}
    }
  },
  "comment_template": {
    "pass": "Certificate valid. Subject: {parsed.subject_cn}. Expires: {parsed.expiry_date} ({parsed.days_until_expiry} days). Key: {parsed.key_type} {parsed.key_size}-bit. Signature: {parsed.signature_algorithm}.",
    "advisory": "Certificate concerns: {parsed.advisory_reasons}. Subject: {parsed.subject_cn}. Self-signed certificates are expected on IoT devices but should be documented.",
    "fail": "Certificate FAILED: {parsed.fail_reasons}. {parsed.detail}."
  },
  "prereq_rules": {"prereq_type": "tls_detected"},
  "compliance_map": ["ISO 27001 A.14.1.2"],
  "requires_safe_mode_override": false
}
```

#### U13: HSTS Header Presence

```json
{
  "test_id": "U13",
  "name": "HSTS Header Presence",
  "description": "Check for HTTP Strict Transport Security header",
  "tier": "automatic",
  "essential_pass": false,
  "tool": "sslyze",
  "tool_args": "--http_headers {ip}:{tls_port}",
  "timeout_seconds": 15,
  "parser": "sslyze_headers",
  "eval_rules": {
    "type": "header_presence",
    "header": "Strict-Transport-Security",
    "present_verdict": "pass",
    "absent_verdict": "advisory"
  },
  "comment_template": {
    "pass": "HSTS header present: {parsed.hsts_value}. Max-age: {parsed.hsts_max_age}s.",
    "advisory": "HSTS header not present. Browser connections may be vulnerable to downgrade attacks. Recommended: Strict-Transport-Security: max-age=31536000"
  },
  "prereq_rules": {"prereq_type": "tls_detected"},
  "compliance_map": ["ISO 27001 A.14.1.2", "Cyber Essentials"],
  "requires_safe_mode_override": false
}
```

#### U14: HTTP Security Headers

```json
{
  "test_id": "U14",
  "name": "HTTP Security Headers",
  "description": "Audit HTTP security headers (X-Frame-Options, CSP, X-Content-Type-Options, etc.)",
  "tier": "automatic",
  "essential_pass": false,
  "tool": "nikto",
  "tool_args": "-h {ip} -p {http_port} -Format json -output {output}",
  "timeout_seconds": 120,
  "parser": "nikto_headers",
  "eval_rules": {
    "type": "header_checklist",
    "required_headers": {
      "X-Frame-Options": {"missing_verdict": "advisory"},
      "X-Content-Type-Options": {"missing_verdict": "advisory"},
      "Content-Security-Policy": {"missing_verdict": "info"}
    },
    "dangerous_headers": {
      "Server": {"detailed_version": "advisory", "note": "Server header reveals software version"}
    },
    "overall": "worst_of_individual"
  },
  "comment_template": {
    "pass": "All recommended HTTP security headers present. {parsed.header_summary}.",
    "advisory": "Missing security headers: {parsed.missing_headers}. {parsed.recommendations}.",
    "info": "Limited security headers detected. {parsed.header_summary}. This is common on embedded device web interfaces."
  },
  "prereq_rules": {"prereq_type": "port_open", "port": [80, 443, 8080, 8443]},
  "compliance_map": ["ISO 27001 A.14.1.2", "Cyber Essentials"],
  "requires_safe_mode_override": true
}
```

#### U15: SSH Algorithm Assessment

```json
{
  "test_id": "U15",
  "name": "SSH Algorithm Assessment",
  "description": "Audit SSH key exchange, host key, cipher, and MAC algorithms",
  "tier": "automatic",
  "essential_pass": false,
  "tool": "ssh-audit",
  "tool_args": "-j {ip}:{ssh_port}",
  "timeout_seconds": 30,
  "parser": "ssh_audit_json",
  "eval_rules": {
    "type": "ssh_policy",
    "fail_algorithms": {
      "kex": ["diffie-hellman-group1-sha1", "diffie-hellman-group-exchange-sha1"],
      "key": ["ssh-dss"],
      "enc": ["3des-cbc", "arcfour", "arcfour128", "arcfour256"],
      "mac": ["hmac-md5", "hmac-md5-96", "hmac-sha1-96"]
    },
    "advisory_algorithms": {
      "kex": ["diffie-hellman-group14-sha1"],
      "enc": ["aes128-cbc", "aes192-cbc", "aes256-cbc"],
      "mac": ["hmac-sha1"]
    },
    "pass_algorithms": {
      "kex": ["curve25519-sha256", "diffie-hellman-group16-sha512", "diffie-hellman-group18-sha512"],
      "key": ["ssh-ed25519", "rsa-sha2-256", "rsa-sha2-512"],
      "enc": ["chacha20-poly1305@openssh.com", "aes256-gcm@openssh.com", "aes128-gcm@openssh.com", "aes256-ctr"],
      "mac": ["hmac-sha2-256-etm@openssh.com", "hmac-sha2-512-etm@openssh.com"]
    }
  },
  "comment_template": {
    "pass": "SSH server: {parsed.ssh_version}. All algorithms meet current security standards. Key types: {parsed.host_key_types}.",
    "advisory": "SSH server: {parsed.ssh_version}. Weak algorithms detected: {parsed.weak_algorithms}. Recommend disabling CBC mode ciphers and SHA-1 MACs.",
    "fail": "SSH server: {parsed.ssh_version}. INSECURE algorithms: {parsed.insecure_algorithms}. These must be disabled. {parsed.remediation}."
  },
  "prereq_rules": {"prereq_type": "port_open", "port": 22},
  "compliance_map": ["ISO 27001 A.14.1.2", "Cyber Essentials"],
  "requires_safe_mode_override": false
}
```

#### U16: Default Credential Check

```json
{
  "test_id": "U16",
  "name": "Default Credential Check",
  "description": "Test manufacturer default username/password combinations",
  "tier": "automatic",
  "essential_pass": true,
  "tool": "hydra",
  "tool_args": "-L {default_user_list} -P {default_pass_list} -t 2 -W 3 {ip} {service}",
  "timeout_seconds": 120,
  "parser": "hydra_results",
  "eval_rules": {
    "type": "credential_found",
    "credential_found_verdict": "fail",
    "no_credential_found_verdict": "pass",
    "connection_refused_verdict": "info"
  },
  "comment_template": {
    "pass": "No default credentials accepted on any tested service ({parsed.services_tested}). {parsed.attempts_count} combinations tested.",
    "fail": "CRITICAL: Default credentials accepted. Service: {parsed.cracked_service}. Username: {parsed.cracked_user}. This is a critical security vulnerability. Password must be changed immediately.",
    "info": "Service refused connection. Unable to test default credentials on {parsed.refused_service}."
  },
  "prereq_rules": {"prereq_type": "port_open", "port": [80, 443, 22, 554]},
  "compliance_map": ["ISO 27001 A.9.4.3", "Cyber Essentials", "SOC2 CC6.1"],
  "requires_safe_mode_override": true
}
```

#### U17: Brute Force Protection

```json
{
  "test_id": "U17",
  "name": "Brute Force Protection",
  "description": "Test if device rate-limits or locks out after repeated failed logins",
  "tier": "automatic",
  "essential_pass": false,
  "tool": "custom_brute_test",
  "tool_args": "10 rapid failed attempts against {http_port} with wrong password",
  "timeout_seconds": 60,
  "parser": "brute_force_detector",
  "eval_rules": {
    "type": "lockout_detection",
    "responses_analysed": 10,
    "lockout_detected_verdict": "pass",
    "rate_limit_detected_verdict": "pass",
    "no_protection_verdict": "advisory",
    "detection_method": "Compare response times and status codes. If attempt 6+ returns 429/403 or takes >5s longer: protection detected."
  },
  "comment_template": {
    "pass": "Brute force protection active. After {parsed.lockout_threshold} failed attempts, device responded with {parsed.lockout_response}.",
    "advisory": "No brute force protection detected. All 10 rapid failed login attempts accepted without rate limiting or lockout. Recommend implementing account lockout policy."
  },
  "prereq_rules": {"prereq_type": "port_open", "port": [80, 443]},
  "compliance_map": ["ISO 27001 A.9.4.2", "Cyber Essentials"],
  "requires_safe_mode_override": true
}
```

#### U18: HTTP vs HTTPS Availability

```json
{
  "test_id": "U18",
  "name": "HTTP vs HTTPS Redirect",
  "description": "Check if HTTP (port 80) redirects to HTTPS (port 443)",
  "tier": "automatic",
  "essential_pass": false,
  "tool": "curl",
  "tool_args": "-s -o /dev/null -w '%{http_code} %{redirect_url}' -L --max-redirs 3 http://{ip}/",
  "timeout_seconds": 15,
  "parser": "http_redirect",
  "eval_rules": {
    "type": "redirect_check",
    "http_redirects_to_https_verdict": "pass",
    "http_serves_content_verdict": "advisory",
    "http_closed_https_open_verdict": "pass",
    "both_closed_verdict": "na"
  },
  "comment_template": {
    "pass": "HTTP correctly redirects to HTTPS ({parsed.redirect_url}). Plain-text web access is not available.",
    "advisory": "HTTP (port 80) serves content without redirecting to HTTPS. Unencrypted web administration is available. Recommend disabling HTTP or enforcing HTTPS redirect."
  },
  "prereq_rules": {"prereq_type": "port_open", "port": [80]},
  "compliance_map": ["ISO 27001 A.14.1.2", "Cyber Essentials"],
  "requires_safe_mode_override": false
}
```

#### U19: OS Fingerprinting

```json
{
  "test_id": "U19",
  "name": "OS Fingerprinting",
  "description": "Identify operating system and kernel version",
  "tier": "automatic",
  "essential_pass": false,
  "tool": "nmap",
  "tool_args": "-O --osscan-limit {rate_limit} {ip}",
  "timeout_seconds": 30,
  "parser": "nmap_os",
  "eval_rules": {
    "type": "os_report",
    "always_pass": true,
    "note": "Informational. Records OS for the report. Known EOL OS versions flagged as advisory."
  },
  "comment_template": {
    "pass": "OS detected: {parsed.os_name} (confidence: {parsed.os_accuracy}%). {parsed.os_detail}.",
    "advisory": "OS detected: {parsed.os_name}. WARNING: This OS version has reached end-of-life and no longer receives security updates."
  },
  "prereq_rules": null,
  "compliance_map": ["ISO 27001 A.12.6"],
  "requires_safe_mode_override": false
}
```

#### U20–U25: Guided Manual Tests

```json
[
  {
    "test_id": "U20",
    "name": "Network Disconnection Behaviour",
    "tier": "guided_manual",
    "essential_pass": false,
    "instruction": "Disconnect the Cat6 ethernet cable from the device for 30 seconds, then reconnect. Observe the device behaviour.",
    "question": "What happened when you reconnected the cable?",
    "options": [
      {"id": "resumed", "label": "Device resumed normal operation", "verdict": "pass", "comment": "Device at {ip} resumed normal operation after network disconnection and reconnection. No manual intervention required."},
      {"id": "no_resume", "label": "Did not resume — required power cycle", "verdict": "fail", "comment": "Device at {ip} did not resume normal operation after network reconnection. Manual power cycle was required to restore functionality."},
      {"id": "poe", "label": "Device lost power (PoE powered)", "verdict": "na", "comment": "Device is PoE-powered. Disconnecting ethernet removes both connectivity and power. Test not applicable."},
      {"id": "partial", "label": "Partially resumed — some features unavailable", "verdict": "advisory", "comment": "Device at {ip} partially resumed after reconnection. Some features unavailable until manual intervention."},
      {"id": "other", "label": "Other (describe below)", "verdict": "info", "comment": null, "requires_notes": true}
    ],
    "evidence_required": false,
    "compliance_map": ["Baseline"]
  },
  {
    "test_id": "U21",
    "name": "Web Interface Password Change",
    "tier": "guided_manual",
    "essential_pass": true,
    "instruction": "Log into the device's web interface. Navigate to the user/password settings. Change the admin password to a strong password (12+ chars, mixed case, numbers, symbols).",
    "question": "Were you able to change the admin password?",
    "options": [
      {"id": "changed", "label": "Password changed successfully", "verdict": "pass", "comment": "Admin password changed successfully via web interface. Device enforces password change capability."},
      {"id": "no_option", "label": "No password change option available", "verdict": "fail", "comment": "CRITICAL: Device web interface provides no option to change the admin password. Device is permanently vulnerable to default credential attacks."},
      {"id": "failed", "label": "Password change option exists but failed", "verdict": "advisory", "comment": "Password change interface exists but the change operation failed. Error: {engineer_notes}."},
      {"id": "weak_policy", "label": "Changed but device accepts weak passwords", "verdict": "advisory", "comment": "Password changed, but device accepted a weak password (e.g., '1234'). No password complexity enforcement."}
    ],
    "prereq_rules": {"prereq_type": "port_open", "port": [80, 443]},
    "evidence_required": false,
    "compliance_map": ["ISO 27001 A.9.4.3", "Cyber Essentials"]
  },
  {
    "test_id": "U22",
    "name": "Firmware Update Mechanism",
    "tier": "guided_manual",
    "essential_pass": false,
    "instruction": "Check if the device supports firmware updates. Look for an update option in the web interface or manufacturer documentation.",
    "question": "How are firmware updates delivered?",
    "options": [
      {"id": "https", "label": "Encrypted update (HTTPS/signed packages)", "verdict": "pass", "comment": "Firmware updates delivered via encrypted channel (HTTPS) and/or digitally signed packages."},
      {"id": "http", "label": "Unencrypted update (HTTP/TFTP)", "verdict": "fail", "comment": "CRITICAL: Firmware updates delivered via unencrypted channel (HTTP/TFTP). Updates can be intercepted and modified (man-in-the-middle). Manufacturer should provide HTTPS update mechanism."},
      {"id": "manual", "label": "Manual file upload only", "verdict": "advisory", "comment": "Firmware updates require manual file download from manufacturer and upload to device. No automatic update mechanism."},
      {"id": "none", "label": "No update mechanism found", "verdict": "advisory", "comment": "No firmware update mechanism found in web interface or documentation. Device may not be updateable."}
    ],
    "prereq_rules": {"prereq_type": "port_open", "port": [80, 443]},
    "evidence_required": false,
    "compliance_map": ["ISO 27001 A.12.6.1", "Cyber Essentials"]
  },
  {
    "test_id": "U23",
    "name": "Session Timeout Validation",
    "tier": "guided_manual",
    "essential_pass": false,
    "instruction": "Log into the device's web interface. Leave the session idle (no clicks or navigation) for 15 minutes. After 15 minutes, try to perform an action.",
    "question": "Did the session expire after 15 minutes of inactivity?",
    "options": [
      {"id": "expired", "label": "Session expired — redirected to login", "verdict": "pass", "comment": "Web session expired after 15 minutes of inactivity. User was redirected to the login page."},
      {"id": "still_active", "label": "Session still active after 15 minutes", "verdict": "advisory", "comment": "Web session remained active after 15+ minutes of inactivity. No session timeout configured. Recommend configuring session timeout to 15 minutes or less."},
      {"id": "no_auth", "label": "Device has no authentication", "verdict": "fail", "comment": "CRITICAL: Device web interface has no authentication. Any user on the network can access the management interface without credentials."}
    ],
    "prereq_rules": {"prereq_type": "port_open", "port": [80, 443]},
    "evidence_required": false,
    "compliance_map": ["ISO 27001 A.9.4.2"]
  },
  {
    "test_id": "U24",
    "name": "Physical Security (Reset/USB)",
    "tier": "guided_manual",
    "essential_pass": false,
    "instruction": "Physically inspect the device. Look for: hardware reset button, USB ports, serial/console ports, SD card slots, exposed circuit boards.",
    "question": "What physical interfaces are accessible?",
    "options": [
      {"id": "none", "label": "No accessible physical interfaces", "verdict": "pass", "comment": "No externally accessible reset buttons, USB ports, serial ports, or removable media slots found on device housing."},
      {"id": "reset_only", "label": "Recessed reset button only", "verdict": "pass", "comment": "Recessed hardware reset button present (requires pin/tool to activate). No other physical interfaces exposed. This is acceptable."},
      {"id": "usb_or_serial", "label": "USB or serial port accessible", "verdict": "advisory", "comment": "Accessible {engineer_notes} port found on device. Physical access to debug/console ports could allow configuration bypass. Recommend physical access controls."},
      {"id": "open_board", "label": "Exposed circuit board or debug headers", "verdict": "fail", "comment": "CRITICAL: Exposed circuit board or JTAG/debug headers accessible without opening the device enclosure. Physical tampering is trivial."}
    ],
    "evidence_required": true,
    "evidence_prompt": "Take a photo of the device showing any accessible ports or reset buttons.",
    "compliance_map": ["ISO 27001 A.11.2.1"]
  },
  {
    "test_id": "U25",
    "name": "Manufacturer Security Documentation",
    "tier": "guided_manual",
    "essential_pass": false,
    "instruction": "Check the manufacturer's website and product documentation for: security hardening guide, known vulnerability disclosures (CVEs), firmware update history, end-of-life/support status.",
    "question": "What security documentation is available?",
    "options": [
      {"id": "comprehensive", "label": "Hardening guide + CVE disclosures available", "verdict": "pass", "comment": "Manufacturer provides comprehensive security documentation including hardening guide and vulnerability disclosure history."},
      {"id": "partial", "label": "Some documentation, no hardening guide", "verdict": "advisory", "comment": "Partial security documentation available. No dedicated hardening guide found. Recommend requesting from manufacturer."},
      {"id": "none", "label": "No security documentation found", "verdict": "advisory", "comment": "No security documentation, hardening guide, or CVE disclosure history found for this device. Manufacturer's security posture is unclear."},
      {"id": "eol", "label": "Device is end-of-life / unsupported", "verdict": "fail", "comment": "CRITICAL: Device has reached end-of-life. Manufacturer no longer provides security updates. Device should be replaced with a supported model."}
    ],
    "evidence_required": false,
    "compliance_map": ["ISO 27001 A.12.6.1", "Cyber Essentials"]
  }
]
```

---

### 9.1 sslyze Output Parsing

sslyze returns Python objects, not JSON files. The parser converts sslyze scan results into our internal `ParsedFindings` schema.

```python
from sslyze import (
    Scanner, ServerScanRequest, ServerScanResult,
    ServerNetworkLocation, ServerConnectivityTester,
    ScanCommand, ScanCommandAttemptStatusEnum
)

class SSLyzeParser:
    """Parse sslyze scan results into EDQ internal format.
    
    sslyze returns Python dataclass objects. This parser normalises them
    into the same JSON schema the evaluation engine expects, regardless
    of whether sslyze or testssl.sh was the source.
    """

    def parse_protocols(self, result: ServerScanResult) -> dict:
        """Extract supported TLS/SSL versions."""
        versions = []

        protocol_map = {
            ScanCommand.SSL_2_0_CIPHER_SUITES: "SSLv2",
            ScanCommand.SSL_3_0_CIPHER_SUITES: "SSLv3",
            ScanCommand.TLS_1_0_CIPHER_SUITES: "TLSv1.0",
            ScanCommand.TLS_1_1_CIPHER_SUITES: "TLSv1.1",
            ScanCommand.TLS_1_2_CIPHER_SUITES: "TLSv1.2",
            ScanCommand.TLS_1_3_CIPHER_SUITES: "TLSv1.3",
        }

        for scan_cmd, version_name in protocol_map.items():
            attempt = result.scan_result_for(scan_cmd)
            if attempt.status == ScanCommandAttemptStatusEnum.COMPLETED:
                if attempt.result.accepted_cipher_suites:
                    versions.append(version_name)

        legacy = [v for v in versions if v in ("SSLv2", "SSLv3", "TLSv1.0", "TLSv1.1")]
        obsolete = [v for v in versions if v in ("SSLv2", "SSLv3")]

        return {
            "versions_list": ", ".join(versions),
            "versions": versions,
            "legacy_versions": ", ".join(legacy) if legacy else None,
            "obsolete_versions": ", ".join(obsolete) if obsolete else None,
            "highest_version": versions[-1] if versions else None,
            "scan_tool": "sslyze"
        }

    def parse_ciphers(self, result: ServerScanResult) -> dict:
        """Extract cipher suite details."""
        all_ciphers = []
        weak_ciphers = []
        insecure_ciphers = []

        INSECURE = {"RC4", "DES", "3DES", "NULL", "EXPORT", "anon"}
        WEAK = {"CBC"}

        for scan_cmd in [ScanCommand.TLS_1_2_CIPHER_SUITES, ScanCommand.TLS_1_3_CIPHER_SUITES]:
            attempt = result.scan_result_for(scan_cmd)
            if attempt.status == ScanCommandAttemptStatusEnum.COMPLETED:
                for cipher in attempt.result.accepted_cipher_suites:
                    name = cipher.cipher_suite.name
                    all_ciphers.append(name)

                    if any(bad in name for bad in INSECURE):
                        insecure_ciphers.append(name)
                    elif any(w in name for w in WEAK):
                        weak_ciphers.append(name)

        strongest = all_ciphers[0] if all_ciphers else "None"

        return {
            "cipher_count": len(all_ciphers),
            "all_ciphers": all_ciphers,
            "strongest_cipher": strongest,
            "weak_ciphers": ", ".join(weak_ciphers) if weak_ciphers else None,
            "insecure_ciphers": ", ".join(insecure_ciphers) if insecure_ciphers else None,
            "scan_tool": "sslyze"
        }

    def parse_certificate(self, result: ServerScanResult) -> dict:
        """Extract certificate information."""
        attempt = result.scan_result_for(ScanCommand.CERTIFICATE_INFO)
        if attempt.status != ScanCommandAttemptStatusEnum.COMPLETED:
            return {"error": "Certificate scan failed"}

        cert_deployment = attempt.result.certificate_deployments[0]
        leaf_cert = cert_deployment.received_certificate_chain[0]

        from datetime import datetime
        now = datetime.utcnow()
        expiry = leaf_cert.not_valid_after_utc
        days_until_expiry = (expiry - now).days

        return {
            "subject_cn": leaf_cert.subject.rfc4514_string(),
            "issuer_cn": leaf_cert.issuer.rfc4514_string(),
            "expiry_date": expiry.strftime("%Y-%m-%d"),
            "days_until_expiry": days_until_expiry,
            "is_self_signed": cert_deployment.leaf_certificate_is_ev is False
                              and not cert_deployment.verified_certificate_chain,
            "signature_algorithm": leaf_cert.signature_algorithm_oid._name,
            "key_type": leaf_cert.public_key().__class__.__name__,
            "key_size": leaf_cert.public_key().key_size,
            "san_list": self._extract_sans(leaf_cert),
            "scan_tool": "sslyze"
        }

    def parse_headers(self, result: ServerScanResult) -> dict:
        """Extract HTTP security headers (HSTS, etc.)."""
        attempt = result.scan_result_for(ScanCommand.HTTP_HEADERS)
        if attempt.status != ScanCommandAttemptStatusEnum.COMPLETED:
            return {"error": "Header scan failed"}

        hsts = attempt.result.strict_transport_security_header
        return {
            "hsts_present": hsts is not None,
            "hsts_value": str(hsts) if hsts else None,
            "hsts_max_age": hsts.max_age if hsts else None,
            "scan_tool": "sslyze"
        }

    def run_full_scan(self, ip: str, port: int) -> dict:
        """Execute a complete sslyze scan and return all parsed results."""
        location = ServerNetworkLocation(hostname=ip, port=port)
        tester = ServerConnectivityTester()
        server_info = tester.perform(location)

        scanner = Scanner()
        request = ServerScanRequest(
            server_info=server_info,
            scan_commands={
                ScanCommand.SSL_2_0_CIPHER_SUITES,
                ScanCommand.SSL_3_0_CIPHER_SUITES,
                ScanCommand.TLS_1_0_CIPHER_SUITES,
                ScanCommand.TLS_1_1_CIPHER_SUITES,
                ScanCommand.TLS_1_2_CIPHER_SUITES,
                ScanCommand.TLS_1_3_CIPHER_SUITES,
                ScanCommand.CERTIFICATE_INFO,
                ScanCommand.HTTP_HEADERS,
            }
        )
        scanner.queue_scans([request])

        for result in scanner.get_results():
            return {
                "protocols": self.parse_protocols(result),
                "ciphers": self.parse_ciphers(result),
                "certificate": self.parse_certificate(result),
                "headers": self.parse_headers(result),
            }
```

---

## 10. Device Profiles

Camera, Controller, Intercom, IoT Sensor, Generic — each with `scan_policy` (see Section 4.3). Profile-specific additional tests extend the universal library for device-category-specific checks.

---

## 11. Template System

Template import from Excel, cell mapping format, JSON configuration. Templates define which cells in the original `.xlsx` file map to which test results, enabling pixel-perfect report reproduction.

---

## 12. Guided Manual Test Workflow

Structured single-click options, auto-generated comments, evidence prompts. Engineers see one question at a time with pre-defined answer choices that automatically generate professional comments.

---

## 13. Wobbly Cable Resilience Handler

```python
class WobblyCableHandler:
    INITIAL_INTERVAL = 2
    MAX_INTERVAL = 60
    MAX_TOTAL_WAIT = 900      # 15 minutes
    BACKOFF_FACTOR = 2

    async def check_connectivity(self, ip: str, known_port: int) -> bool:
        ping_ok = await self._icmp_ping(ip, timeout=2)
        if not ping_ok:
            return False
        return await self._tcp_syn(ip, known_port, timeout=3)

    async def wait_for_reconnection(self, ip, known_port, on_status_change) -> bool:
        interval = self.INITIAL_INTERVAL
        total_waited = 0
        on_status_change("device_unreachable", {"ip": ip})

        while total_waited < self.MAX_TOTAL_WAIT:
            await asyncio.sleep(interval)
            total_waited += interval
            if await self.check_connectivity(ip, known_port):
                on_status_change("device_reconnected", {"downtime_seconds": total_waited})
                await asyncio.sleep(3)
                return True
            interval = min(interval * self.BACKOFF_FACTOR, self.MAX_INTERVAL)

        on_status_change("device_timeout", {"ip": ip})
        return False
```

---

## 14. Nessus Integration

`defusedxml` parsing of `.nessus` XML exports, severity mapping (Critical/High/Medium/Low/Info), and template row mapping for inclusion in device qualification reports.

---

## 15. Report Generation Engine

### 15.1 Excel Generation (Template-Based)

openpyxl opens actual client `.xlsx`, fills cells per mapping. Runs synchronously in FastAPI process (Excel generation is fast, ~1-3 seconds).

### 15.2 Word Report Generation

python-docx with Jinja2. Runs synchronously (~2-5 seconds).

### 15.3 PDF Generation (Async Background Worker)

**LibreOffice does NOT run in the FastAPI container.** It runs in a dedicated `pdf_worker` container with resource limits.

```python
# server/pdf_worker/worker.py
import redis
import subprocess
import json
import os

REDIS_URL = os.environ["REDIS_URL"]
conn = redis.from_url(REDIS_URL)

def generate_pdf(job_data: dict):
    """Runs in separate container. Consumes from Redis queue."""
    source_path = job_data["source_path"]  # .xlsx or .docx
    output_dir = job_data["output_dir"]
    run_id = job_data["run_id"]

    try:
        result = subprocess.run(
            ["libreoffice", "--headless", "--convert-to", "pdf",
             "--outdir", output_dir, source_path],
            capture_output=True, timeout=120
        )

        if result.returncode != 0:
            raise Exception(f"LibreOffice failed: {result.stderr.decode()}")

        pdf_path = source_path.rsplit(".", 1)[0] + ".pdf"

        # Notify via Redis pub/sub
        conn.publish("pdf_complete", json.dumps({
            "run_id": run_id,
            "status": "complete",
            "pdf_path": pdf_path,
            "download_token": generate_download_token(pdf_path)
        }))

    except Exception as e:
        conn.publish("pdf_complete", json.dumps({
            "run_id": run_id,
            "status": "error",
            "error": str(e)
        }))

# Main worker loop
if __name__ == "__main__":
    while True:
        _, job_json = conn.blpop("pdf_queue")
        job_data = json.loads(job_json)
        generate_pdf(job_data)
```

**API flow:**
```
1. POST /api/reports/pdf/{run_id}
   → Generate Excel or Word first (if not already done)
   → Push job to Redis "pdf_queue"
   → Return: { "status": "queued", "job_id": "xxx" }

2. WebSocket /api/ws/pdf-status/{job_id}
   → Listens to Redis pub/sub "pdf_complete" channel
   → Sends: { "type": "pdf_ready", "download_url": "..." }
   → Frontend shows toast: "Your PDF is ready — click to download"

3. GET /api/reports/download/{token}
   → Validates time-limited token (15 min TTL)
   → Streams PDF file
```

---

## 16. AI Synopsis Generator

### 16.1 Feature Toggle

```python
class SynopsisService:
    async def can_generate(self, run: TestRun) -> tuple[bool, str]:
        """Check if AI synopsis is available and allowed."""
        global_enabled = await self.config.get("ai_synopsis_global") == "true"
        if not global_enabled:
            return False, "AI synopsis generation is disabled globally by administrator."

        report_config = await self.get_report_config(run)
        if report_config and not report_config.ai_synopsis_enabled:
            return False, "AI synopsis is disabled for this client due to data handling policy."

        if not self.config.ai_api_key:
            return False, "AI API key not configured."

        return True, ""
```

### 16.2 Data Anonymisation (Mandatory Before API Call)

```python
class DataAnonymiser:
    """Strip all client-identifying data before sending to external AI API.
    
    This is a compliance requirement. Vulnerability assessment data tied to specific 
    clients, IP addresses, and device identifiers must not be sent to third-party 
    services in identifiable form.
    """

    def __init__(self):
        self.token_map = {}

    def anonymise(self, run: TestRun) -> tuple[dict, dict]:
        """Returns (anonymised_data, token_map_for_reconstruction)."""
        self.token_map = {}
        counter = {"device": 0, "ip": 0, "mac": 0, "host": 0}

        anonymised = {
            "device_category": run.device.device_category,
            "overall_verdict": run.overall_verdict,
            "results": []
        }

        self._register_token("client", run.report_config.client_name if run.report_config else "Unknown", "[CLIENT_NAME]")
        device_token = f"[DEVICE_{counter['device']}]"
        self._register_token("device_name", run.device.name, device_token)
        self._register_token("ip", run.device.ip_address, "[DEVICE_IP]")
        self._register_token("mac", run.device.mac_address, "[DEVICE_MAC]")

        if run.discovery_results and run.discovery_results.get("tls_info"):
            cert = run.discovery_results["tls_info"].get("certificate", {})
            if cert.get("subject"):
                self._register_token("cert_subject", cert["subject"], "[CERT_SUBJECT]")

        for r in run.results:
            anon_result = {
                "test_number": r.test_number,
                "test_name": r.test_name,
                "verdict": r.verdict,
                "comment": self._scrub_text(r.auto_comment or r.engineer_notes or "")
            }
            anonymised["results"].append(anon_result)

        return anonymised, self.token_map

    def _scrub_text(self, text: str) -> str:
        for real_value, token in self.token_map.items():
            text = text.replace(real_value, token)
        return text

    def _register_token(self, category: str, real_value: str, token: str):
        if real_value:
            self.token_map[real_value] = token

    def deanonymise(self, ai_draft: str) -> str:
        result = ai_draft
        for real_value, token in self.token_map.items():
            result = result.replace(token, real_value)
        return result
```

### 16.3 Synopsis Generation Flow

```python
class SynopsisGenerator:
    SYSTEM_PROMPT = """You are a cybersecurity consultant writing a professional
    device security assessment synopsis for a network security qualification.

    RULES:
    - Reference ONLY the test results provided. Do not invent findings.
    - Use professional technical language.
    - Structure: 1) Executive summary, 2) Key findings by severity,
      3) Remediation recommendations in priority order.
    - Be specific: reference test IDs, port numbers, protocol versions.
    - Length: 300-500 words.
    - Note: Real device identifiers have been replaced with tokens
      (e.g., [DEVICE_IP]). Use these tokens as-is in your response."""

    async def generate_draft(self, run: TestRun) -> str:
        can_generate, reason = await self.can_generate(run)
        if not can_generate:
            raise APIError("AI_DISABLED", reason)

        anonymiser = DataAnonymiser()
        anonymised_data, token_map = anonymiser.anonymise(run)
        prompt = self._build_prompt(anonymised_data)

        response = await self.llm_client.messages.create(
            model="llm-provider-model",
            max_tokens=1024,
            system=self.SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}]
        )
        anonymised_draft = response.content[0].text
        real_draft = anonymiser.deanonymise(anonymised_draft)
        self._validate_references(real_draft, run)

        run.synopsis_ai_draft = real_draft
        run.synopsis_ai_drafted = True

        await self.audit.log("synopsis_generated", "test_run", run.id,
                              {"anonymised": True, "token_count": len(token_map)})

        return real_draft
```

---

## 17. Agent Architecture

### 17.1 Privilege Management

**The agent requires elevated privileges.** Raw socket operations (nmap SYN scans), network interface manipulation (static IP assignment), and routing table changes all require Administrator (Windows) or root (macOS/Linux).

**Windows:** PyInstaller spec includes UAC manifest:
```
exe = EXE(
    pyz, a.scripts, [],
    name='EDQ Agent',
    uac_admin=True,
    icon='assets/edq.ico',
)
```

**macOS/Linux:** Startup privilege check:
```python
class PrivilegeChecker:
    def check_and_escalate(self):
        if sys.platform == "win32":
            self._verify_with_self_test()
            return

        if os.geteuid() != 0:
            print("EDQ Agent requires root privileges for network scanning.")
            print("Please restart with: sudo edq-agent")
            if sys.platform == "darwin":
                os.execvp("osascript", [
                    "osascript", "-e",
                    'do shell script "edq-agent" with administrator privileges'
                ])
            sys.exit(1)

        self._verify_with_self_test()

    def _verify_with_self_test(self):
        """Actually test if raw sockets work, don't just check UID."""
        try:
            result = subprocess.run(
                ["nmap", "-sS", "-p", "1", "127.0.0.1"],
                capture_output=True, timeout=5
            )
            if "requires root" in result.stderr.decode().lower():
                raise PermissionError("nmap SYN scan failed — insufficient privileges")
        except PermissionError:
            self._show_error_and_exit(
                "EDQ Agent has insufficient privileges for network scanning. "
                "Please restart the application as Administrator/root."
            )
```

### 17.2 Network Guard — Platform-Specific Commands

**The most critical safety component.** If the agent crashes after setting a static IP on the engineer's ethernet adapter, the laptop loses normal network connectivity until manually fixed.

```python
import atexit
import signal
import json
import os

class NetworkGuard:
    """Ensures the network interface is ALWAYS restored, even on crash.
    
    Three layers of protection:
    1. State file written BEFORE any interface change
    2. atexit hook for clean shutdowns
    3. Startup self-heal for unclean exits (crash, kill, power loss)
    """

    STATE_FILE = os.path.expanduser("~/.edq/network_restore.json")

    def __init__(self):
        os.makedirs(os.path.dirname(self.STATE_FILE), exist_ok=True)
        atexit.register(self._restore_and_cleanup)
        signal.signal(signal.SIGINT, lambda s, f: sys.exit(0))
        signal.signal(signal.SIGTERM, lambda s, f: sys.exit(0))

    def startup_self_heal(self):
        """FIRST thing called on agent startup. Restores interface if previous crash."""
        if os.path.exists(self.STATE_FILE):
            try:
                with open(self.STATE_FILE) as f:
                    state = json.load(f)
                print(f"[NetworkGuard] Previous session did not clean up. "
                      f"Restoring interface '{state['interface']}' to DHCP...")
                self._restore_interface(state)
                os.remove(self.STATE_FILE)
                print("[NetworkGuard] Interface restored successfully.")
            except Exception as e:
                print(f"[NetworkGuard] WARNING: Failed to auto-restore: {e}")
                print(f"[NetworkGuard] Manual fix: run 'netsh interface ipv4 set address "
                      f"name=\"{state.get('interface', 'Ethernet')}\" dhcp'")

    def modify_interface(self, interface: str, ip: str, subnet: str):
        """Save current state, then modify interface."""
        current_config = self._get_current_config(interface)

        state = {
            "interface": interface,
            "original_ip": current_config.get("ip"),
            "original_subnet": current_config.get("subnet"),
            "original_gateway": current_config.get("gateway"),
            "was_dhcp": current_config.get("dhcp", True),
            "timestamp": datetime.utcnow().isoformat()
        }
        with open(self.STATE_FILE, "w") as f:
            json.dump(state, f)

        cidr = self._subnet_to_cidr(subnet)  # "255.255.255.0" → "24"

        if sys.platform == "win32":
            subprocess.run(
                f'netsh interface ipv4 set address name="{interface}" '
                f'static {ip} {subnet}', shell=True, check=True
            )
        elif sys.platform == "darwin":
            subprocess.run(
                f'ifconfig {interface} {ip} netmask {subnet}',
                shell=True, check=True
            )
        else:
            # Linux: use iproute2 (ifconfig is deprecated and often missing)
            subprocess.run(f'ip addr flush dev {interface}', shell=True, check=True)
            subprocess.run(f'ip addr add {ip}/{cidr} dev {interface}', shell=True, check=True)
            subprocess.run(f'ip link set {interface} up', shell=True, check=True)

    def _restore_and_cleanup(self):
        """atexit hook: restore interface to original state."""
        if os.path.exists(self.STATE_FILE):
            try:
                with open(self.STATE_FILE) as f:
                    state = json.load(f)
                self._restore_interface(state)
            finally:
                try:
                    os.remove(self.STATE_FILE)
                except OSError:
                    pass

    def _restore_interface(self, state: dict):
        """Restore interface to DHCP or original static config."""
        iface = state["interface"]
        if state.get("was_dhcp", True):
            if sys.platform == "win32":
                subprocess.run(f'netsh interface ipv4 set address name="{iface}" dhcp',
                               shell=True, timeout=10)
                subprocess.run(f'netsh interface ipv4 set dns name="{iface}" dhcp',
                               shell=True, timeout=10)
            elif sys.platform == "darwin":
                subprocess.run(f'ipconfig set {iface} DHCP', shell=True, timeout=10)
            else:
                # Linux: release and re-request DHCP
                subprocess.run(f'ip addr flush dev {iface}', shell=True, timeout=10)
                subprocess.run(f'dhclient {iface}', shell=True, timeout=10)
        else:
            original_ip = state.get("original_ip")
            original_subnet = state.get("original_subnet")
            if original_ip and original_subnet:
                cidr = self._subnet_to_cidr(original_subnet)
                if sys.platform == "win32":
                    subprocess.run(
                        f'netsh interface ipv4 set address name="{iface}" '
                        f'static {original_ip} {original_subnet}',
                        shell=True, timeout=10
                    )
                elif sys.platform == "darwin":
                    subprocess.run(
                        f'ifconfig {iface} {original_ip} netmask {original_subnet}',
                        shell=True, timeout=10
                    )
                else:
                    subprocess.run(f'ip addr flush dev {iface}', shell=True, timeout=10)
                    subprocess.run(f'ip addr add {original_ip}/{cidr} dev {iface}',
                                   shell=True, timeout=10)

    def _get_current_config(self, interface: str) -> dict:
        """Read current interface configuration."""
        if sys.platform == "win32":
            result = subprocess.run(
                f'netsh interface ipv4 show config name="{interface}"',
                capture_output=True, text=True, shell=True
            )
            return self._parse_netsh_output(result.stdout)
        elif sys.platform == "darwin":
            result = subprocess.run(
                f'ifconfig {interface}',
                capture_output=True, text=True, shell=True
            )
            return self._parse_ifconfig_output(result.stdout)
        else:
            result = subprocess.run(
                f'ip addr show {interface}',
                capture_output=True, text=True, shell=True
            )
            return self._parse_ip_addr_output(result.stdout)

    @staticmethod
    def _subnet_to_cidr(subnet: str) -> str:
        """Convert subnet mask to CIDR notation. '255.255.255.0' → '24'."""
        parts = subnet.split('.')
        binary = ''.join(format(int(p), '08b') for p in parts)
        return str(binary.count('1'))
```

### 17.3 Main Loop

```python
class EDQAgent:
    async def run(self):
        # 0. CRITICAL: Self-heal from previous crash FIRST
        self.network_guard = NetworkGuard()
        self.network_guard.startup_self_heal()

        # 1. Check privileges
        PrivilegeChecker().check_and_escalate()

        # 2. Verify all tools
        verifier = ToolVerifier()
        tool_status = verifier.verify_all()

        # 3. Load config
        self.config = AgentConfig.load()

        # 4. Initialise components
        self.server_client = ServerClient(self.config.server_url, self.config.api_key)
        self.key_manager = KeyManager()
        self.offline_db = OfflineDatabase(self.config.data_dir, self.key_manager)
        self.scanner = Scanner(self.config.tools_dir)
        self.tray = SystemTrayIcon()

        # 5. Check server connectivity
        online = await self.server_client.check_connection()

        if online:
            heartbeat_response = await self.register_or_update()

            if heartbeat_response.get("version_status") == "incompatible":
                self.tray.set_status("update_required")
                self._show_update_prompt(heartbeat_response.get("download_url"))
            elif heartbeat_response.get("version_status") == "deprecated":
                self._show_update_banner()

            await self.key_manager.sync_from_server(self.server_client)

            self.tray.set_status("online")
            asyncio.create_task(self.heartbeat_loop())
            asyncio.create_task(self.job_poll_loop())
            asyncio.create_task(self.sync_pending())
        else:
            self.tray.set_status("offline")
            self.local_server = LocalServer(self)
            asyncio.create_task(self.local_server.start())
            asyncio.create_task(self.connectivity_check_loop())

        # 6. Run system tray (blocks main thread)
        self.tray.run()

    async def execute_job(self, job: ScanJob):
        self.tray.set_status("scanning")
        scan_policy = job.device_profile.scan_policy
        policy_enforcer = ScanPolicyEnforcer()

        fingerprint = await self.scanner.discover(
            job.ip_address, job.interface, scan_policy
        )
        await self.server_client.upload_discovery(job.run_id, fingerprint)

        for test in job.automatic_tests:
            can_run, reason = policy_enforcer.can_execute(test, scan_policy)
            if not can_run:
                await self.server_client.upload_result(job.run_id, TestResult(
                    test_number=test.test_number,
                    verdict="skipped_safe_mode",
                    auto_comment=f"Test skipped: {reason}"
                ))
                continue

            if not await self.wobbly_cable.check(job.ip_address, job.known_port):
                ok = await self.wobbly_cable.wait_for_reconnection(
                    job.ip_address, job.known_port,
                    lambda s, d: self.server_client.stream_event(job.run_id, s, d)
                )
                if not ok:
                    await self.server_client.update_run_status(job.run_id, "paused_cable")
                    return

            adjusted_args = policy_enforcer.get_nmap_args(test.tool_args, scan_policy)
            result = await self.scanner.execute_test(test, job.ip_address, job.interface,
                                                       adjusted_args)
            await self.server_client.upload_result(job.run_id, result)
            await asyncio.sleep(policy_enforcer.get_delay(scan_policy))

        await self.server_client.update_run_status(job.run_id, "paused_manual")
        self.tray.set_status("online")
```

### 17.4 Tool Runner

```python
class ToolRunner:
    async def execute(self, tool: str, args: str, timeout: int = 60,
                       interface: str = None) -> ToolResult:
        cmd = self._build_command(tool, args, interface)

        process = await asyncio.create_subprocess_shell(
            cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )

        stdout_chunks = []
        try:
            async with asyncio.timeout(timeout):
                while True:
                    line = await process.stdout.readline()
                    if not line:
                        break
                    decoded = line.decode('utf-8', errors='replace')
                    stdout_chunks.append(decoded)
                    await self.on_output(decoded)

                await process.wait()
                stderr_data = await process.stderr.read()

        except asyncio.TimeoutError:
            process.kill()
            return ToolResult(tool=tool, exit_code=-1,
                              stdout=''.join(stdout_chunks),
                              stderr=f"Timed out after {timeout}s", timed_out=True)

        return ToolResult(tool=tool, exit_code=process.returncode,
                          stdout=''.join(stdout_chunks),
                          stderr=stderr_data.decode('utf-8', errors='replace'),
                          timed_out=False)
```

---

## 18. Offline Architecture

### 18.1 Design Principle

Offline is not degraded. An engineer at a construction site with no internet has the same testing capability as one in the office. The only differences: reports sync later, AI synopsis unavailable.

### 18.2 Local Encrypted Database

```python
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

class OfflineDatabase:
    """AES-256-GCM encrypted SQLite for offline storage."""

    def __init__(self, data_dir: str, key_manager: 'KeyManager'):
        self.db_path = os.path.join(data_dir, "edq_offline.db.enc")
        self.key_manager = key_manager

    def open(self):
        key = self.key_manager.get_database_key()
        if not key:
            raise OfflineKeyError(
                "Offline database key not available. "
                "Please connect to the server at least once to initialise offline access."
            )

        encrypted_data = open(self.db_path, 'rb').read()
        nonce = encrypted_data[:12]
        ciphertext = encrypted_data[12:]

        try:
            aesgcm = AESGCM(key)
            plaintext = aesgcm.decrypt(nonce, ciphertext, None)
        except Exception:
            raise OfflineKeyError(
                "Failed to decrypt offline database. "
                "The encryption key may have been rotated. "
                "Connect to the server to re-sync offline access."
            )

        self.temp_path = tempfile.mktemp(suffix='.db')
        open(self.temp_path, 'wb').write(plaintext)
        self.conn = sqlite3.connect(self.temp_path)

    def save_and_encrypt(self):
        self.conn.close()
        plaintext = open(self.temp_path, 'rb').read()
        key = self.key_manager.get_database_key()
        aesgcm = AESGCM(key)
        nonce = os.urandom(12)
        ciphertext = aesgcm.encrypt(nonce, plaintext, None)
        open(self.db_path, 'wb').write(nonce + ciphertext)
        os.remove(self.temp_path)

    MAX_OFFLINE_DAYS = 7

    def purge_expired(self):
        cutoff = datetime.utcnow() - timedelta(days=self.MAX_OFFLINE_DAYS)
        self.conn.execute("DELETE FROM offline_runs WHERE created_at < ?",
                          (cutoff.isoformat(),))
```

### 18.3 Key Management (No Password-Derived Keys)

```python
import keyring

class KeyManager:
    """Manages the offline database encryption key.
    
    The encryption key is a random 256-bit value — NOT derived from the user's
    password. This avoids the desync problem where changing password on server
    invalidates the offline database.
    """

    KEYCHAIN_SERVICE = "EDQ Agent"
    KEYCHAIN_ACCOUNT = "offline_db_key"

    def get_database_key(self) -> bytes | None:
        stored = keyring.get_password(self.KEYCHAIN_SERVICE, self.KEYCHAIN_ACCOUNT)
        if stored:
            return bytes.fromhex(stored)
        return None

    def store_database_key(self, key: bytes):
        keyring.set_password(self.KEYCHAIN_SERVICE, self.KEYCHAIN_ACCOUNT, key.hex())

    async def sync_from_server(self, server_client: 'ServerClient'):
        response = await server_client.get("/api/auth/offline-key")
        key_hex = response.json()["data"]["offline_key"]
        key = bytes.fromhex(key_hex)
        self.store_database_key(key)
        return key

    def generate_new_key(self) -> bytes:
        return os.urandom(32)

    def has_key(self) -> bool:
        return self.get_database_key() is not None
```

---

## 19. Sync Protocol

### 19.1 Sync Flow

```
Agent reconnects to server
  │
  ├── 1. Authenticate (POST /api/agent/heartbeat)
  │
  ├── 2. Get pending sync items from local sync_queue (ordered by created_at ASC)
  │
  ├── 3. For each item:
  │     ├── POST /api/sync/upload with operation + payload
  │     ├── Server response:
  │     │   ├── 200 OK → mark as synced, delete local copy
  │     │   ├── 409 CONFLICT → mark as conflict, apply merge rules (Section 19.3)
  │     │   ├── 500 ERROR → increment retry_count, retry later
  │     │   └── 413 TOO LARGE → split and retry
  │     └── If connection drops: stop, resume from last checkpoint
  │
  ├── 4. Upload pending attachments
  │
  ├── 5. Download updated templates
  │     └── GET /api/templates?updated_since={last_sync_time}
  │
  ├── 6. Download updated OUI database (if newer version available)
  │     └── GET /api/data/oui-database?current_hash={local_hash}
  │     └── Response: 304 Not Modified (no change) or 200 with new CSV
  │     └── Agent replaces local oui_database.csv and reloads lookup table
  │
  └── 7. Report sync summary
```

### 19.2 Conflict Detection

A conflict exists when the server already has a test_result for the same `(device_id, test_number)` with an `updated_at` timestamp AFTER the offline result's `created_at`.

### 19.3 Conflict Merge Algorithm

```python
class SyncConflictResolver:
    """Deterministic merge rules for offline sync conflicts.
    
    Conflicts occur when two engineers test the same device offline,
    or when one tests online while another is offline.
    """

    def resolve(self, local_result: TestResult, server_result: TestResult,
                strategy: str = "auto") -> MergeDecision:
        """
        Auto-resolution rules (applied before human review):

        Rule 1: If both have the same verdict → keep server (it's already there)
        Rule 2: If local is more severe → flag for review (possible regression)
        Rule 3: If server is more severe → keep server (worst-case wins)
        Rule 4: If different runs (different run_id) → keep both (parallel tests)
        Rule 5: If same run, same test → timestamp wins (last write)
        """

        if strategy == "keep_local":
            return MergeDecision(action="overwrite_server", result=local_result)
        elif strategy == "keep_server":
            return MergeDecision(action="discard_local", result=server_result)
        elif strategy == "keep_both":
            return MergeDecision(action="create_new_run", result=local_result)

        # Auto-resolution
        if local_result.run_id != server_result.run_id:
            return MergeDecision(action="no_conflict_different_runs",
                                 result=local_result)

        if local_result.verdict == server_result.verdict:
            return MergeDecision(action="discard_local_same_verdict",
                                 result=server_result)

        local_severity = self._severity_rank(local_result.verdict)
        server_severity = self._severity_rank(server_result.verdict)

        if server_severity >= local_severity:
            return MergeDecision(action="keep_server_more_severe",
                                 result=server_result)

        return MergeDecision(
            action="requires_review",
            result=None,
            review_reason=f"Offline result ({local_result.verdict}) is more severe "
                          f"than server result ({server_result.verdict}). "
                          f"Local timestamp: {local_result.created_at}. "
                          f"Server timestamp: {server_result.updated_at}."
        )

    SEVERITY_RANK = {
        "pass": 0,
        "info": 1,
        "na": 1,
        "skipped_safe_mode": 1,
        "advisory": 2,
        "fail": 3,
        "error": 3,
    }

    def _severity_rank(self, verdict: str) -> int:
        return self.SEVERITY_RANK.get(verdict, 0)
```

**Conflict resolution UI:**

```
┌──────────────────────────────────────────────────────────┐
│  SYNC CONFLICT: Device "Pelco Camera Lobby" — Test U15   │
│                                                           │
│  Server Result (Engineer A, 14:32):                       │
│  Verdict: Pass — "All SSH algorithms meet standards"      │
│                                                           │
│  Offline Result (Engineer B, 15:10):                      │
│  Verdict: Advisory — "Weak CBC ciphers detected"          │
│                                                           │
│  [Keep Server] [Keep Offline] [Keep Both (New Run)]       │
└──────────────────────────────────────────────────────────┘
```

---

## 20. WebSocket Real-Time Streaming

Event types:

```
test_started       - Automatic test execution begun
test_progress      - Progress percentage update
test_complete      - Single test finished
terminal_output    - Live stdout/stderr from tool
discovery_started  - Fingerprinting begun
discovery_complete - Fingerprint results available
cable_disconnect   - Device unreachable (Wobbly Cable)
cable_reconnect    - Device recovered
run_status_change  - Overall run status changed
sync_started       - Offline sync begun
sync_complete      - All items synced
pdf_ready          - PDF generation complete, download URL available
```

---

## 21. Frontend Application

### 21.1 Pages & Routes

| Route | Component | Access |
|---|---|---|
| `/login` | LoginPage | Public |
| `/` | DashboardPage | All authenticated |
| `/devices` | DevicesPage | Admin, Tester |
| `/devices/:id` | DeviceDetailPage | Admin, Tester |
| `/sessions/:id` | TestSessionPage | Admin, Tester |
| `/reports` | ReportsPage | All authenticated |
| `/review` | ReviewPage | Admin, Reviewer |
| `/admin` | AdminPage | Admin only |

### 21.2 Key UI Features

**Interface Selection (before any scan):** `InterfaceSelector.jsx` component displayed before discovery begins. Dropdown of available interfaces with status (UP/DOWN), IP, and warnings.

**Safe Mode Indicator:** Test results list shows `skipped_safe_mode` verdict with distinct styling. Tooltip explains why the test was skipped.

**AI Synopsis Toggle:** "Draft Synopsis" button hidden if `ai_synopsis_enabled` is false for the client. Admin panel has global and per-client toggles.

**PDF Generation:** "Generate PDF" button shows progress state: "Queued → Generating → Ready". Toast notification if user navigates away.

### 21.3 Colour Scheme

```javascript
const VERDICT_COLOURS = {
  pass:               { bg: "bg-green-100",  text: "text-green-800",  icon: "CheckCircle" },
  fail:               { bg: "bg-red-100",    text: "text-red-800",    icon: "XCircle" },
  advisory:           { bg: "bg-amber-100",  text: "text-amber-800",  icon: "AlertTriangle" },
  na:                 { bg: "bg-gray-100",   text: "text-gray-600",   icon: "MinusCircle" },
  info:               { bg: "bg-blue-100",   text: "text-blue-800",   icon: "Info" },
  pending:            { bg: "bg-slate-50",   text: "text-slate-500",  icon: "Clock" },
  error:              { bg: "bg-red-50",     text: "text-red-600",    icon: "AlertOctagon" },
  skipped_safe_mode:  { bg: "bg-orange-50",  text: "text-orange-600", icon: "ShieldOff" },
};
```

---

## 22. Security Controls

### 22.1 File Upload Validation

```python
ALLOWED_UPLOADS = {
    "image/png":  {"magic": b"\x89PNG\r\n\x1a\n", "max_mb": 2},
    "image/jpeg": {"magic": b"\xff\xd8\xff",       "max_mb": 2},
    "application/xml":  {"magic": b"<?xml",         "max_mb": 50},
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet":
                        {"magic": b"PK\x03\x04",    "max_mb": 25},
    "text/plain": {"magic": None,                    "max_mb": 10},
}
FORBIDDEN_TYPES = {"image/svg+xml", "text/html", "application/javascript"}
```

### 22.2 Terminal Output Sanitisation

```python
class OutputSanitiser:
    DANGEROUS_PATTERNS = [
        re.compile(r'<script[^>]*>.*?</script>', re.IGNORECASE | re.DOTALL),
        re.compile(r'<iframe[^>]*>.*?</iframe>', re.IGNORECASE | re.DOTALL),
        re.compile(r'on\w+\s*=', re.IGNORECASE),
        re.compile(r'javascript:', re.IGNORECASE),
    ]
    DANGEROUS_ANSI = [
        re.compile(r'\x1b\]0;.*?\x07'),
        re.compile(r'\x1b\]2;.*?\x07'),
    ]

    def sanitise(self, text: str) -> str:
        for p in self.DANGEROUS_PATTERNS:
            text = p.sub('[STRIPPED]', text)
        for p in self.DANGEROUS_ANSI:
            text = p.sub('', text)
        return text
```

### 22.3 CSRF Middleware

```python
class CSRFMiddleware:
    async def __call__(self, request: Request, call_next):
        if request.method in {"GET", "HEAD", "OPTIONS"}:
            response = await call_next(request)
            if "edq_csrf" not in request.cookies:
                response.set_cookie("edq_csrf", secrets.token_urlsafe(32),
                                     httponly=False, secure=True, samesite="strict")
            return response

        cookie_token = request.cookies.get("edq_csrf")
        header_token = request.headers.get("X-CSRF-Token")
        if not cookie_token or not header_token or cookie_token != header_token:
            raise HTTPException(403, "CSRF validation failed")

        return await call_next(request)
```

### 22.4 Nginx Security Configuration

```nginx
server {
    listen 443 ssl http2;
    server_name edq.electracom.co.uk;

    ssl_protocols TLSv1.3;
    ssl_prefer_server_ciphers off;

    add_header X-Frame-Options "DENY" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    add_header Content-Security-Policy "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self' wss:; font-src 'self';" always;
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

    limit_req_zone $binary_remote_addr zone=api:10m rate=100r/m;
    limit_req_zone $binary_remote_addr zone=auth:10m rate=10r/m;
    limit_req_zone $binary_remote_addr zone=agent:10m rate=200r/m;

    client_max_body_size 50m;

    location /api/auth/ { limit_req zone=auth burst=5 nodelay; proxy_pass http://backend:8000; }
    location /api/agent/ { limit_req zone=agent burst=20 nodelay; proxy_pass http://backend:8000; }
    location /api/ { limit_req zone=api burst=20 nodelay; proxy_pass http://backend:8000; }

    location /api/ws/ {
        proxy_pass http://backend:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 86400;
    }

    location / {
        root /usr/share/nginx/html;
        try_files $uri $uri/ /index.html;
    }
}
```

---

## 23. Deployment & Infrastructure

### 23.1 Docker Compose (Production)

```yaml
version: "3.8"

services:
  nginx:
    image: nginx:1.25-alpine
    ports:
      - "443:443"
      - "80:80"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/conf.d/default.conf:ro
      - ./frontend/dist:/usr/share/nginx/html:ro
      - /etc/ssl/certs/edq.crt:/etc/ssl/certs/edq.crt:ro
      - /etc/ssl/private/edq.key:/etc/ssl/private/edq.key:ro
    depends_on:
      backend:
        condition: service_healthy
    restart: unless-stopped

  backend:
    build: ./backend
    environment:
      - DATABASE_URL=sqlite:////data/edq.db
      - REDIS_URL=redis://redis:6379/0
      - SECRET_KEY=${SECRET_KEY}
      - AI_API_KEY=${AI_API_KEY}
      - ALLOWED_ORIGINS=https://edq.electracom.co.uk
      - MIN_AGENT_VERSION=1.0.0
      - AI_SYNOPSIS_GLOBAL=true
    volumes:
      - edq_data:/data
      - edq_reports:/data/reports
      - edq_uploads:/data/uploads
      - ./backend/templates:/app/templates:ro
    depends_on:
      redis:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/api/health"]
      interval: 30s
      timeout: 10s
      retries: 3
    restart: unless-stopped
    deploy:
      resources:
        limits:
          memory: 2G
          cpus: "1.5"

  pdf_worker:
    build: ./pdf_worker
    environment:
      - REDIS_URL=redis://redis:6379/0
    volumes:
      - edq_reports:/data/reports
    depends_on:
      redis:
        condition: service_healthy
    restart: unless-stopped
    deploy:
      resources:
        limits:
          memory: 1G
          cpus: "1.0"

  redis:
    image: redis:7.2-alpine
    command: redis-server --maxmemory 256mb --maxmemory-policy allkeys-lru
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
    restart: unless-stopped

volumes:
  edq_data:
  edq_reports:
  edq_uploads:
  redis_data:
```

### 23.2 PDF Worker Dockerfile

```dockerfile
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    libreoffice-writer libreoffice-calc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY worker.py .

CMD ["python", "worker.py"]
```

### 23.3 Environment Variables

```bash
SECRET_KEY=<random-64-char-hex>
AI_API_KEY=<your-api-key>             # Optional — AI synopsis
DATABASE_URL=sqlite:////data/edq.db
REDIS_URL=redis://redis:6379/0
ALLOWED_ORIGINS=https://edq.electracom.co.uk
LOG_LEVEL=INFO
MIN_AGENT_VERSION=1.0.0
AI_SYNOPSIS_GLOBAL=true

ADMIN_EMAIL=admin@electracom.co.uk
ADMIN_PASSWORD=<strong-initial-password>
ADMIN_NAME=System Administrator
```

---

## 24. Error Handling & Logging

```python
# Agent-specific errors
class PrivilegeError(Exception):
    """Agent lacks admin/root privileges."""

class NetworkRestoreError(Exception):
    """Failed to restore network interface after scan."""

class OfflineKeyError(Exception):
    """Offline database key not available or invalid."""

class SafeModeBlockedError(Exception):
    """Test blocked by device safety profile."""

class AIDisabledError(Exception):
    """AI synopsis requested but disabled for this client."""

class DeviceNotFoundError(Exception):
    """No device detected during discovery."""
```

---

## 25. Testing Strategy

### 25.1 Test Categories

| Category | Tool | Coverage Target |
|---|---|---|
| Unit Tests (backend) | pytest | Services, parsers, evaluation, anonymiser |
| Unit Tests (frontend) | Vitest | Components, hooks, utilities |
| Integration Tests | pytest + httpx | API endpoints with test DB |
| Parser Tests | pytest | nmap, sslyze, testssl, ssh-audit, nikto parsers |
| Report Tests | pytest + file comparison | Excel/Word vs expected output |
| E2E Tests | Playwright | Critical user flows |
| Security Tests | OWASP ZAP + manual | CSRF, XSS, injection, file upload |
| Agent Tests | pytest | Privilege check, network guard, ARP sweep, DHCP server |
| Anonymiser Tests | pytest | Verify no client data leaks to AI API |

### 25.2 Critical Test Scenarios

1. **Full device qualification flow**: Interface selection → discovery → auto tests → manual tests → synopsis → report → PDF
2. **Offline test and sync**: Agent offline → test → store → reconnect → sync → verify
3. **Wobbly cable recovery**: Disconnect mid-scan → verify pause → reconnect → verify resume
4. **Unknown device type**: New device → universal tests → generic report
5. **Nessus import**: Upload .nessus → parse → map → verify
6. **Concurrent agents**: Two agents, different devices → no cross-contamination
7. **Report pixel-fidelity**: Generated Excel vs manually created reference
8. **Network crash recovery**: Kill agent mid-scan → restart → verify interface restored to DHCP
9. **Hardcoded static IP**: Device at 192.168.1.1, no DHCP → verify ARP sweep finds it
10. **AI anonymisation**: Generate synopsis → verify API payload contains no real IPs, MACs, or client names
11. **Safe mode enforcement**: Controller device → verify nikto and hydra are blocked
12. **Version enforcement**: Old agent version → verify "deprecated" warning, not lockout
13. **PDF worker queue**: Two simultaneous PDF requests → verify neither blocks FastAPI
14. **Privilege escalation failure**: Run agent without admin → verify clean error message
15. **DHCP server discovery**: Device with DHCP → verify agent assigns IP and discovers device
16. **APIPA fallback**: Device at 169.254.x.x → verify ARP sweep includes link-local range
17. **Sync conflict resolution**: Two engineers test same device offline → verify merge rules
18. **Npcap missing on Windows**: Agent starts without Npcap → verify graceful fallback to TCP connect scans

### 25.3 Test Data

```
server/backend/tests/fixtures/
├── nmap/
│   ├── pelco_camera_scan.xml
│   ├── easyio_controller_scan.xml
│   ├── static_ip_arp_sweep.xml
│   ├── apipa_device_scan.xml
│   └── minimal_device_scan.xml
├── sslyze/
│   ├── tls12_weak_ciphers.json
│   ├── tls13_strong.json
│   └── self_signed_cert.json
├── testssl/
│   ├── heartbleed_vulnerable.json
│   └── robot_vulnerable.json
├── ssh_audit/
│   ├── openssh_8.2.json
│   └── weak_algorithms.json
├── nikto/
│   ├── missing_headers.json
│   └── clean_scan.json
├── nessus/
│   ├── sample_camera.nessus
│   └── sample_controller.nessus
├── anonymiser/
│   ├── sample_input.json
│   ├── expected_anonymised.json
│   └── expected_deanonymised.json
└── reports/
    ├── pelco_camera_expected.xlsx
    └── easyio_controller_expected.xlsx
```

---

## Appendix A: Complete Gap Tracker

All identified operational gaps and their resolution status:

| # | Gap | Source | Section | Status |
|---|---|---|---|---|
| 1 | Privilege escalation (admin/root required) | Internal review | 17.1 | ✅ Integrated |
| 2 | Device safety profiles (fragile devices crash under scan) | Internal review | 4.3, 8.2 | ✅ Integrated |
| 3 | TLS tooling (testssl.sh bash dependency on Windows) | Internal review | 3.2, 3.3 | ✅ Integrated |
| 4 | Agent version enforcement | Internal review | 5.2 | ✅ Integrated |
| 5 | Network crash recovery (stuck static IP) | Internal review | 17.2 | ✅ Integrated |
| 6 | Hardcoded static IP devices (no DHCP) | Internal review | 7.3 | ✅ Integrated |
| 7 | AI privacy / NDA violation (client data to API) | Internal review | 16.2, 16.3 | ✅ Integrated |
| 8 | Offline DB decryption key desync | Internal review | 18.3 | ✅ Integrated |
| 9 | PDF generation deadlocks in Docker | Internal review | 15.3, 23.1 | ✅ Integrated |
| 10 | Interface selection (which ethernet to scan) | Internal review | 7.2 | ✅ Integrated |
| 11 | Unknown IP scanning (device IP not known) | Internal review | 7.3 | ✅ Integrated |
| 12 | DHCP server (active IP assignment) | Internal review | 7.3 | ✅ Integrated |
| 13 | APIPA 169.254.x.x fallback | Internal review | 7.3 | ✅ Integrated |
| 14 | Linux iproute2 (ifconfig deprecated) | Internal review | 17.2 | ✅ Integrated |
| 15 | OUI database sync | Internal review | 19.1 | ✅ Integrated |
| 16 | Full U04–U25 test definitions | Internal scoring gap | 9 | ✅ Integrated |
| 17 | sslyze parser specification | Internal scoring gap | 9.1 | ✅ Integrated |
| 18 | Sync conflict merge algorithm | Internal scoring gap | 19.3 | ✅ Integrated |
| 19 | Npcap driver for Windows | Internal scoring gap | 3.5 | ✅ Integrated |

**All identified gaps: 19 total. 19 resolved. 0 open.**

# Section 26 — Integration Testing & Real Device Validation Protocol

> **Purpose**: This section provides the test protocol for real-device integration testing. Engineers MUST follow these steps when testing against a physical device. This section is device-agnostic — the same protocol applies regardless of manufacturer, model, or device category.

---

## 26.1 Pre-Test Environment Checklist

Before connecting any physical device, the agent must verify the following prerequisites are met. The agent should run these checks programmatically where possible and prompt the user for manual confirmation where not.

### 26.1.1 Infrastructure Health Checks (Automated)

The agent should execute these commands and verify expected output:

```bash
# 1. Docker services running
docker compose ps
# Expected: 3 services (api, frontend, tools) all showing "Up"

# 2. Tools sidecar responsive
curl -s http://tools:8001/health
# Expected: {"status": "healthy", "tools": {"nmap": true, "testssl": true, "ssh_audit": true, "hydra": true}}

# 3. Backend API responsive
curl -s http://localhost:8000/api/health
# Expected: {"status": "ok", "database": "connected", "version": "1.x.x"}

# 4. Frontend accessible
curl -s -o /dev/null -w "%{http_code}" http://localhost:3000
# Expected: 200

# 5. WebSocket endpoint available
# Agent should verify /ws/ path is proxied correctly in nginx.conf

# 6. Database seeded
curl -s http://localhost:8000/api/tests/definitions | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'Test definitions loaded: {len(d)}')"
# Expected: Test definitions loaded: 25 (minimum, universal tests)
```

If any check fails, the agent must diagnose and fix the issue before proceeding. Common fixes:

| Check Failed | Likely Cause | Fix |
|---|---|---|
| Docker services not running | Docker Desktop not started | Prompt user to start Docker Desktop, wait 30s, retry |
| Tools sidecar unhealthy | Missing tool binary | Check Dockerfile, ensure `apt-get install nmap` etc. ran |
| Backend DB not connected | SQLite file missing or permissions | Check `/data/edq.db` exists, verify volume mount |
| Frontend 404/502 | nginx misconfigured or frontend not built | Run `npm run build` in frontend, check nginx.conf proxy paths |
| 0 test definitions | Seed script not run | Execute `python3 seed_data.py` |

### 26.1.2 Network Readiness Checks (User-Assisted)

The agent must ask the user the following and adapt accordingly:

**Q1: "How is the test device connected to your computer?"**

| Answer | Agent Action |
|---|---|
| Direct Ethernet cable (device → laptop) | Identify the Ethernet interface (`ip link show` on Linux, `ipconfig` on Windows). Device likely uses static IP or APIPA (169.254.x.x). May need to set static IP on test interface. |
| Through a switch/hub | Same as above but multiple devices possible. Agent should warn about scanning only the target IP. |
| On the corporate network | Warn user that scanning corporate network devices may trigger security alerts. Confirm user has authorisation. Identify correct interface. |
| Wi-Fi only | Inform user that Wi-Fi testing has limitations — no Layer 2 ARP scanning, potential firewall issues. Recommend Ethernet if possible. |

**Q2: "What is the device's IP address? If unknown, do you know the expected subnet?"**

| Answer | Agent Action |
|---|---|
| Known IP (e.g., 192.168.1.100) | Proceed directly to connectivity verification |
| Known subnet but not exact IP | Run targeted subnet scan: `nmap -sn 192.168.1.0/24` to find live hosts |
| Completely unknown | Check if device uses DHCP (run DHCP discovery), check for APIPA range, try common defaults (192.168.1.1, 192.168.0.1, 10.0.0.1) |

**Q3: "Can you ping the device from your computer?"**

The agent should instruct: `ping <device_ip>` and interpret results:

| Result | Meaning | Fix |
|---|---|---|
| Reply received | Device reachable, proceed | None needed |
| Request timed out | Device unreachable or ICMP blocked | Check cable, check IP config on test interface, try `arp -a` to see if MAC appears |
| Destination unreachable | Wrong subnet | Set static IP on test interface to match device subnet |

---

## 26.2 Generic Device Integration Testing Protocol

This is a 5-phase protocol. The agent walks the user through each phase sequentially, verifying results before proceeding. The protocol is identical for every device type.

### Phase 1: Discovery Validation

**What the agent does:** Triggers the auto-discovery pipeline against the target IP and validates each step produced correct output.

```
POST /api/discovery
Body: {"ip_address": "<device_ip>"}
```

**Validation checkpoints the agent must verify:**

| Step | Check | Pass Criteria | Failure Action |
|---|---|---|---|
| ARP Lookup | MAC address resolved | Non-empty MAC in format XX:XX:XX:XX:XX:XX | Check device is on same Layer 2 segment. If through router, ARP won't work — agent should note this and skip to port scan. |
| OUI Lookup | Manufacturer identified | Manufacturer name populated (e.g., "Pelco", "EasyIO", "Hikvision") | Unknown OUI is acceptable — device gets "Unknown Manufacturer". Agent should note this is normal for less common brands. |
| Port Scan | Open ports found | At least 1 open port detected | Check firewall on device, increase nmap timeout, try `-Pn` flag to skip host discovery |
| Service Fingerprint | Services identified on open ports | Service names populated (e.g., "https", "ssh", "rtsp") | Some devices don't respond to service probes. Agent should note which ports are open but unidentified. |
| Category Inference | Device category assigned | One of: Camera, Controller, Intercom, IoT Sensor, Network Device, Unknown | "Unknown" is a valid result — means universal tests only. Agent should ask user to confirm or correct the category. |

**Agent guidance to user:** "Discovery found [summary]. Does this look correct for your device? The manufacturer is [X], I found [N] open ports ([list]), and categorised it as a [category]. If any of this is wrong, I can adjust before we run tests."

### Phase 2: Automated Test Execution

**What the agent does:** Creates a test session and triggers automated (Tier 1) tests against the device.

```
POST /api/sessions
Body: {"device_id": "<id>", "profile": "<detected_or_selected_profile>"}

POST /api/sessions/<session_id>/run
Body: {"tier": "automatic"}
```

**Validation checkpoints:**

| Check | Pass Criteria | Failure Action |
|---|---|---|
| Session created | Session ID returned, status = "created" | Check API logs for database errors |
| Tests queued | Correct number of Tier 1 tests queued based on profile | Verify test definitions are seeded and profile mapping is correct |
| WebSocket connected | Real-time progress updates streaming | Check nginx WebSocket proxy config, verify `/ws/` path forwarding |
| Each test completes | Status transitions: queued → running → completed/failed | If stuck on "running" >5 min: check tools sidecar logs, check device still reachable |
| Tool output stored | Raw tool output (nmap XML, testssl JSON, etc.) saved | Check file storage path, check disk space |
| Results parsed | Each test has a grade (Pass/Fail/Warning/Info) and populated findings | Check parser matched expected output format — log raw output for debugging |

**Agent guidance to user:** Display real-time progress. After completion: "Automated tests complete. [X] passed, [Y] failed, [Z] warnings. Here's a summary: [list critical failures]. Want to review any specific result before we move to manual tests?"

**Common failure patterns and fixes:**

```
Symptom: nmap test completes but all ports show "filtered"
Cause:   Device firewall blocking scan, or wrong interface used
Fix:     Agent should check which network interface nmap used.
         Try: nmap -e <correct_interface> <device_ip>

Symptom: testssl.sh returns empty/error
Cause:   Device doesn't have TLS enabled, or port 443 not open
Fix:     Check port scan results first. If no TLS port found,
         mark TLS tests as N/A with reason "No TLS service detected"

Symptom: ssh-audit fails to connect
Cause:   SSH not enabled on device, or non-standard port
Fix:     Check port scan for SSH on non-standard ports.
         Try common alternatives: 2222, 22222, 8022

Symptom: hydra default credential check hangs
Cause:   Device rate-limits or blocks login attempts
Fix:     Reduce thread count, add delay between attempts.
         If device locks out, inform user and skip test.

Symptom: Test result says "parser_error"
Cause:   Tool output format doesn't match expected schema
Fix:     Agent should dump raw tool output to console,
         identify the format difference, and fix the parser.
         This is the most common issue with new device types.
```

### Phase 3: Manual Guided Test Execution

**What the agent does:** Presents each Tier 2 (guided manual) test to the user with structured prompts.

**Agent guidance to user for each manual test:**

```
"Test [ID]: [Name]
Category: [What this tests]
Instructions: [Step-by-step what to check on the device]

What did you observe?
  1. Pass — [predefined pass description]
  2. Fail — [predefined fail description]
  3. N/A — [predefined N/A reason]

You can also attach a screenshot or photo as evidence."
```

**Validation checkpoints:**

| Check | Pass Criteria | Failure Action |
|---|---|---|
| All Tier 2 tests presented | User sees every manual test for the device profile | Check test definitions include `tier: "guided_manual"` |
| Structured options shown | User selects from predefined choices, not free text | Verify UI renders radio buttons / select dropdowns |
| Evidence upload works | User can attach images/PDFs, files are stored | Check upload endpoint, verify `/data/evidence/` directory exists and is writable |
| Results saved | Each manual test has a grade and optional comment | Check database after each submission |

### Phase 4: Report Generation

**What the agent does:** Triggers report generation and validates the output against the template.

```
POST /api/sessions/<session_id>/report
Body: {"format": "excel", "template": "<auto_detected_or_selected>"}
```

**Validation checkpoints:**

| Check | Pass Criteria | Failure Action |
|---|---|---|
| Report generated | .xlsx file created in output directory | Check openpyxl logs for errors, verify template file exists |
| File opens in Excel | No corruption errors when opened | Validate with `openpyxl.load_workbook()` after generation |
| Device details populated | Device name, IP, MAC, manufacturer in correct cells | Agent should programmatically read the generated file and verify key cells are non-empty |
| Test results in correct rows | Each test result appears in the expected row | Agent should compare test IDs to row mapping |
| Grades/comments populated | Pass/Fail/Warning values and finding text present | Check for empty result cells that should be populated |
| Formatting preserved | Original template formatting intact (colours, borders, merged cells, fonts) | Compare formatting attributes of key cells between template and output |
| Logo present | Company logo appears in expected position | Check if image was copied from template |

**Automated report validation script the agent should run:**

```python
"""
Agent runs this after report generation to catch common issues.
"""
import openpyxl

def validate_report(generated_path, template_path):
    gen = openpyxl.load_workbook(generated_path)
    tmpl = openpyxl.load_workbook(template_path)
    issues = []

    for sheet_name in tmpl.sheetnames:
        if sheet_name not in gen.sheetnames:
            issues.append(f"Missing sheet: {sheet_name}")
            continue

        gs = gen[sheet_name]
        ts = tmpl[sheet_name]

        # Check merged cells match
        if gs.merged_cells.ranges != ts.merged_cells.ranges:
            issues.append(f"Sheet '{sheet_name}': Merged cells differ")

        # Check key formatting cells (first 5 rows typically header/device info)
        for row in range(1, 6):
            for col in range(1, 10):
                gc = gs.cell(row=row, column=col)
                tc = ts.cell(row=row, column=col)
                if tc.font.bold != gc.font.bold:
                    issues.append(f"Sheet '{sheet_name}' cell ({row},{col}): Font bold mismatch")
                if tc.fill.start_color != gc.fill.start_color:
                    issues.append(f"Sheet '{sheet_name}' cell ({row},{col}): Fill colour mismatch")

    if not issues:
        print("REPORT VALIDATION: ALL CHECKS PASSED")
    else:
        print(f"REPORT VALIDATION: {len(issues)} ISSUES FOUND")
        for i in issues:
            print(f"  - {i}")

    return issues
```

### Phase 5: End-to-End Result Verification

**What the agent does:** Final walkthrough with the user to confirm everything is correct.

**Agent guidance to user:**

```
"Testing complete. Here's the full session summary:

Device: [Manufacturer] [Model] at [IP]
Category: [Category]
Tests run: [X] automated, [Y] manual, [Z] auto-N/A
Results: [A] Pass, [B] Fail, [C] Warning, [D] N/A

Report generated: [filename]

Please open the report in Excel and confirm:
1. Does the device name and IP appear correctly at the top?
2. Do the test results match what you saw in the app?
3. Does the formatting look right — same colours, fonts, layout as your existing reports?
4. Are there any empty cells where you expected data?

If anything looks wrong, tell me what and where and I'll fix it."
```

---

## 26.3 Symptom-Based Troubleshooting Guide

This section is organised by **what the user sees**, not by device type. The agent should reference this when the user reports a problem during any phase.

### Network & Connectivity Issues

| Symptom | Likely Cause | Diagnostic Steps | Fix |
|---|---|---|---|
| "Device not found during discovery" | Subnet mismatch — test laptop and device on different subnets | `ip addr show` (Linux) or `ipconfig` (Windows) to check laptop's IP on test interface. Compare subnet to device's known IP. | Set static IP on test interface to same subnet as device. E.g., if device is 192.168.1.100, set laptop to 192.168.1.200/24. |
| "Discovery finds MAC but no ports" | Device has aggressive firewall or is still booting | Wait 60 seconds, retry. Try `nmap -Pn -sV <ip>` to skip ping and probe services directly. | If still no ports after 3 retries, device may have all ports filtered. Note this in report — it's actually a valid security finding. |
| "Discovery finds device but wrong manufacturer" | OUI database outdated or device uses rebranded NIC | Check MAC prefix against latest IEEE OUI database. Some devices use generic Realtek/Broadcom NICs. | Allow user to manually correct manufacturer. This doesn't affect test execution. |
| "Tests were running then suddenly all fail" | Device rebooted, cable disconnected, or IP changed | Wobbly Cable Handler should detect this. Check if handler paused the session. Ping device manually. | If device is back: resume session. If IP changed: update session, restart failed tests. If device is gone: pause and wait. |
| "Everything works but only on my PC" | Docker network interface binding or firewall specific to machine | Check if Docker is using the right network interface. Windows Defender or corporate firewall may block Docker containers from accessing physical network. | Add firewall exception for Docker, or use `--network host` for the tools container (Linux only — on Windows, use port forwarding). |

### Test Execution Issues

| Symptom | Likely Cause | Diagnostic Steps | Fix |
|---|---|---|---|
| "Test stuck on 'running' forever" | Tool process hung or timeout too generous | Check tools sidecar logs: `docker logs edq-tools-1`. Look for the specific tool process. | Kill hung process, reduce timeout value, restart test. Default timeouts: nmap 300s, testssl 120s, ssh-audit 60s, hydra 120s. |
| "Test completed but result is empty" | Parser didn't recognise tool output format | Check raw tool output in `/data/tool_output/<session_id>/`. Compare against parser's expected format. | This is the most common issue with new device types. The tool output may have unexpected fields or missing sections. Fix the parser. |
| "All TLS tests say N/A" | Device doesn't serve TLS on any port | Verify with `openssl s_client -connect <ip>:443`. Device may use HTTP only or TLS on non-standard port. | If no TLS: N/A is correct. If TLS on non-standard port: update device profile to include the correct port. |
| "Default credential test blocked/hangs" | Device rate-limiting or account lockout after N attempts | Check hydra output for "blocked" or "too many attempts" messages. | Reduce hydra threads to 1, add `-W 3` wait flag. If device locks out, reset device and skip this test. Document in report. |
| "SSH audit fails with 'connection refused'" | SSH not enabled on device | Try `nc -zv <ip> 22` to confirm port state. | If port closed: SSH test should be N/A. If port open but refused: device may require key-based auth only. Note in report. |

### Report Generation Issues

| Symptom | Likely Cause | Diagnostic Steps | Fix |
|---|---|---|---|
| "Report file is corrupted / won't open" | openpyxl error during generation | Check backend logs for Python traceback. Common: writing to merged cell, invalid cell reference. | Fix the specific openpyxl error. Usually a cell coordinate that doesn't exist or an attempt to write to a merged cell's non-primary coordinate. |
| "Report opens but cells are empty" | Result-to-cell mapping incorrect | Run validation script (Section 26.2 Phase 4). Compare expected cell coordinates against actual. | Update the template mapping configuration. Each template has a map of test_id → (sheet, row, column) that may need adjustment. |
| "Report formatting looks different from original" | Template formatting overwritten during generation | Compare specific cell formatting (font, fill, border) between template and output using openpyxl. | Ensure code reads template as read-only reference, copies formatting to output. Never modify the template file itself. |
| "Logo is missing" | Image not copied from template | openpyxl has limited image support. Check if template uses embedded vs linked images. | Copy image explicitly using `openpyxl.drawing.image.Image()`. Store logo as separate file in `/templates/assets/`. |
| "Wrong template used" | Category-to-template mapping incorrect | Check which template was selected and why. Compare device category against template mapping config. | If device category was wrong, correct it and regenerate. If mapping is wrong, fix the config. |

### WebSocket & UI Issues

| Symptom | Likely Cause | Diagnostic Steps | Fix |
|---|---|---|---|
| "Progress bar doesn't update" | WebSocket not connected or nginx not proxying | Browser console (F12) → check for WebSocket errors. Look for "WebSocket connection failed". | nginx.conf needs: `proxy_set_header Upgrade $http_upgrade; proxy_set_header Connection "upgrade";` in the `/ws/` location block. |
| "UI shows old data after test completes" | Frontend not refreshing from API after WS event | Check if WebSocket message triggers a data refetch. | Ensure WS `test_completed` event triggers `GET /api/sessions/<id>/results` to refresh the results list. |
| "Login works but redirects back to login" | Cookie not being set or CSRF mismatch | Check browser cookies (F12 → Application → Cookies). Look for `session` and `csrf_token` cookies. | Ensure backend sets cookies with `SameSite=Lax`, `Path=/`, and frontend sends credentials with `fetch(..., {credentials: 'include'})`. |

---

## 26.4 Testing a New/Unknown Device Type

When the user tests a device that has no matching device profile, the agent should guide them through this specific flow:

1. **Run discovery normally** — the device will get category "Unknown" or a best-guess category
2. **Inform the user**: "This device doesn't match any existing profile. I'll run the 25 universal tests that apply to all IP devices. These cover port scanning, TLS/SSL, SSH, default credentials, HTTP headers, and network services."
3. **Execute universal tests only** — no device-specific tests
4. **After tests complete**, ask: "Based on what we found, this device has [list of services]. Would you like me to create a new device profile for this type so future tests include device-specific checks?"
5. **If user says yes**: Create a minimal profile entry with the detected ports, services, and manufacturer. This becomes a starting point that the user can refine over time.
6. **Generate report using the universal template** (MANUFACTURER MODEL IP Device Qualification Template)

This is the core of the device-agnostic design — the app is useful from the very first device, even if that device has never been seen before.

---

## 26.5 Agent Behaviour Requirements

The following instructions define the expected workflow during integration testing.

### 26.5.1 When the User Says "I'm ready to test" or "I've connected a device"

1. **Stop all other work.** Integration testing requires focus.
2. Run the Pre-Test Environment Checklist (26.1) automatically.
3. Fix any failing checks before proceeding.
4. Ask the three network readiness questions (26.1.2).
5. Proceed through the 5-phase protocol (26.2) step by step.
6. After each phase, confirm results with the user before moving to the next.
7. If any test fails unexpectedly, consult the Troubleshooting Guide (26.3) before asking the user for help.

### 26.5.2 When Debugging a Failed Test

1. **Always check logs first** — `docker logs edq-tools-1` and `docker logs edq-api-1`
2. **Always check raw tool output** — read the actual file in `/data/tool_output/`
3. **Never assume the device is broken** — the code is more likely wrong than the device
4. **Show the user what you found** — don't just say "I fixed it", explain what was wrong
5. **If you can't diagnose within 3 attempts**, escalate the issue with documentation of what was tried, raw output snippets, and a recommendation for manual investigation.

### 26.5.3 When Generating Reports

1. **Always run the validation script** (26.2 Phase 4) after generating a report
2. **Never modify the template file** — always copy it to a new file, then populate
3. **If validation finds issues**, fix them and regenerate before showing the user
4. **Ask the user to visually verify** — the agent cannot see what the Excel looks like when opened, so the user's eyes are the final check

### 26.5.4 Escalation Protocol

If the agent encounters any of these situations, it should inform the user that additional help may be needed:

- Device uses a protocol the tools don't support (e.g., BACnet, Modbus, ZigBee) — these need custom test implementations
- Tool output format is completely unrecognisable — parser may need a rewrite, not just a fix
- Docker networking issue that persists after 3 fix attempts — may be Windows/WSL2 specific
- Report template has complex formatting that openpyxl can't replicate — may need manual Excel adjustment

In these cases, escalate to the team lead with full context of the issue and what was attempted. These scenarios may require manual intervention or custom tool development.

---

## 26.6 Validation Checklist

The agent should walk the user through this final checklist after completing all tests on their first device. Every item must be confirmed before the app is considered ready for production use.

```
FIRST DEVICE VALIDATION CHECKLIST
===================================

Discovery Pipeline
  [ ] Device detected at correct IP address
  [ ] MAC address resolved (or noted as unavailable if through router)
  [ ] Manufacturer identified (or "Unknown" acknowledged)
  [ ] Open ports match known device specifications
  [ ] Device category correctly assigned (or manually corrected)

Automated Tests (Tier 1)
  [ ] All expected automated tests executed
  [ ] No tests stuck in "running" state
  [ ] Each test has a grade (Pass/Fail/Warning/N/A)
  [ ] Raw tool output files stored and accessible
  [ ] WebSocket progress updates displayed in real-time

Manual Tests (Tier 2)
  [ ] All guided manual tests presented with structured options
  [ ] User could select Pass/Fail/N/A with predefined comments
  [ ] Evidence upload (screenshot/photo) works
  [ ] Manual results saved to database

Auto-N/A Tests (Tier 3)
  [ ] Tests with unmet prerequisites automatically marked N/A
  [ ] N/A reason clearly stated

Report Generation
  [ ] Report generated as .xlsx file
  [ ] Correct template selected (or universal template for unknown devices)
  [ ] Device details populated in correct cells
  [ ] All test results appear in correct rows
  [ ] Grades and findings text present
  [ ] Template formatting preserved (colours, fonts, borders, merged cells)
  [ ] Logo present (if applicable)
  [ ] Report opens without errors in Excel
  [ ] User confirms report matches expected format

Overall
  [ ] Full session data persisted in database
  [ ] Session can be reopened and reviewed
  [ ] All evidence files accessible from results
  [ ] Audit log contains entries for all actions
```

When all items are checked, the agent should tell the user: "First device validation complete. The app is working correctly. You can now test additional devices — the process will be the same. If you want to add a custom device profile for this device type, I can help set that up."

---

*END OF SECTION 26*

*END OF DOCUMENT — EDQ Implementation PRD v1.2 (Unified)*
