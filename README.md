# EDQ — Electracom Device Qualifier

A comprehensive network device security testing and compliance management platform. EDQ automates the qualification of smart building IP devices (cameras, controllers, access control systems, intercoms) through a structured test suite of 30 security assessments mapped to ISO 27001, Cyber Essentials, and SOC2 compliance frameworks.

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│                    EDQ Platform                          │
│                                                          │
│  ┌─────────────┐    ┌─────────────┐    ┌──────────────┐ │
│  │   React     │    │   FastAPI   │    │   SQLite     │ │
│  │   Frontend  │───▶│   Backend   │───▶│   Database   │ │
│  │   (Vite)    │    │   (Python)  │    │              │ │
│  └─────────────┘    └──────┬──────┘    └──────────────┘ │
│                            │                             │
│                     ┌──────┴──────┐                      │
│                     │  Services   │                      │
│                     │ • Reports   │                      │
│                     │ • AI Synopsis│                     │
│                     │ • WebSocket │                      │
│                     │ • Discovery │                      │
│                     └─────────────┘                      │
└──────────────────────────────────────────────────────────┘
```

## Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| Frontend | React 18 + TypeScript | Responsive SPA with mobile-first design |
| Styling | Tailwind CSS 3 | Utility-first CSS framework |
| Animations | Framer Motion | Smooth transitions and micro-interactions |
| Backend | FastAPI (Python 3.12) | Async REST API with WebSocket support |
| Database | SQLite + SQLAlchemy | Lightweight relational database |
| Auth | JWT (PyJWT + passlib) | Custom role-based authentication |
| Reports | openpyxl + python-docx | Excel and Word report generation |
| AI | OpenAI/Anthropic API | Synopsis generation (optional) |
| Deployment | Docker Compose | Container orchestration |

## Features

### Device Management
- Device discovery dashboard with auto-detection simulation
- Device profile management with manufacturer/model categorization
- Support for cameras, controllers, access control, intercoms, sensors, switches, gateways

### Test Execution
- 30 universal security tests from the EDQ test library
- Automatic tests: nmap, sslyze, ssh-audit, hydra, nikto, curl, ethtool
- Guided manual tests: physical security, firmware updates, session management
- Test templates with customizable test suites
- Real-time progress monitoring via WebSocket

### Compliance & Reporting
- Protocol whitelist configuration for compliance checking
- ISO 27001, Cyber Essentials, SOC2 compliance mapping
- Excel (.xlsx) and Word (.docx) report generation
- AI-generated narrative synopsis with human review workflow
- Audit log tracking all system actions

### Agent Management
- Distributed testing agent registration
- Agent status monitoring (online/offline/busy)
- Network segment assignment

### Security
- JWT-based authentication with role-based access control
- Three roles: Admin, Reviewer (QA Lead), Test Engineer
- Password hashing with bcrypt
- API key authentication for agents

## Quick Start

### Prerequisites
- Python 3.11+ 
- Node.js 18+
- pnpm (recommended) or npm

### Development Setup

```bash
# 1. Clone the repository
git clone <your-repo-url>
cd edq

# 2. Set up the backend
cd server/backend
cp ../../.env.example .env
# Edit .env with your settings (especially JWT_SECRET)

pip install -r requirements.txt
python init_db.py

# 3. Start the backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 4. In a new terminal, set up the frontend
cd frontend
pnpm install   # or npm install
pnpm dev       # or npm run dev
```

### Docker Deployment

```bash
# 1. Copy and configure environment
cp .env.example .env
# Edit .env with production values

# 2. Build and start
docker compose up -d --build

# 3. Access the application
# Frontend: http://localhost
# API Docs: http://localhost/api/docs
```

### Default Credentials

| Username | Password | Role |
|----------|----------|------|
| admin | admin123 | Admin |

**Important:** Change the default admin password immediately after first login.

## API Documentation

Once the backend is running, visit:
- **Swagger UI:** http://localhost:8000/docs
- **ReDoc:** http://localhost:8000/redoc

### Key API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/auth/login` | Authenticate and get JWT token |
| POST | `/api/auth/register` | Register new user |
| GET | `/api/devices/` | List all devices |
| POST | `/api/devices/` | Add a new device |
| GET | `/api/test-runs/` | List test runs |
| POST | `/api/test-runs/` | Create a test run |
| GET | `/api/test-templates/` | List test templates |
| GET | `/api/test-templates/library` | Get universal test library |
| POST | `/api/reports/generate` | Generate Excel/Word report |
| POST | `/api/synopsis/generate` | Generate AI synopsis |
| GET | `/api/whitelists/` | List protocol whitelists |
| GET | `/api/audit-logs/` | View audit trail |
| GET | `/api/agents/` | List registered agents |
| WS | `/api/ws/test-run/{run_id}` | Real-time test progress |

## Project Structure

```
edq/
├── docker-compose.yml          # Container orchestration
├── .env.example                # Environment template
├── README.md                   # This file
│
├── server/backend/
│   ├── app/
│   │   ├── main.py             # FastAPI application factory
│   │   ├── config.py           # Settings from environment
│   │   ├── models/             # SQLAlchemy ORM models
│   │   │   ├── user.py         # User model with roles
│   │   │   ├── device.py       # Device model
│   │   │   ├── device_profile.py
│   │   │   ├── test_template.py
│   │   │   ├── test_run.py
│   │   │   ├── test_result.py
│   │   │   ├── agent.py
│   │   │   ├── audit_log.py
│   │   │   ├── protocol_whitelist.py
│   │   │   ├── report_config.py
│   │   │   ├── sync_queue.py
│   │   │   └── attachment.py
│   │   ├── routes/             # API route handlers
│   │   │   ├── auth.py         # Authentication endpoints
│   │   │   ├── devices.py      # Device CRUD
│   │   │   ├── test_runs.py    # Test execution
│   │   │   ├── test_results.py # Test results
│   │   │   ├── test_templates.py
│   │   │   ├── reports.py      # Report generation
│   │   │   ├── agents.py       # Agent management
│   │   │   ├── whitelists.py   # Protocol whitelists
│   │   │   ├── discovery.py    # Device discovery
│   │   │   ├── audit_logs.py   # Audit trail
│   │   │   ├── admin.py        # Admin dashboard
│   │   │   ├── synopsis.py     # AI synopsis
│   │   │   └── websocket_routes.py
│   │   ├── schemas/            # Pydantic request/response models
│   │   ├── security/           # JWT auth & authorization
│   │   └── services/           # Business logic
│   │       ├── test_library.py # 30 universal tests
│   │       └── report_generator.py
│   ├── requirements.txt
│   ├── init_db.py              # Database initialization
│   └── Dockerfile
│
├── frontend/
│   ├── src/
│   │   ├── App.tsx             # Routes & layout
│   │   ├── main.tsx            # Entry point
│   │   ├── contexts/
│   │   │   └── AuthContext.tsx  # JWT authentication state
│   │   ├── lib/
│   │   │   └── api.ts          # Axios API client
│   │   ├── components/
│   │   │   └── layout/
│   │   │       └── DashboardLayout.tsx  # Responsive sidebar layout
│   │   └── pages/
│   │       ├── LoginPage.tsx
│   │       ├── RegisterPage.tsx
│   │       ├── DashboardPage.tsx
│   │       ├── DevicesPage.tsx
│   │       ├── DeviceDetailPage.tsx
│   │       ├── TestRunsPage.tsx
│   │       ├── TestRunDetailPage.tsx
│   │       ├── TemplatesPage.tsx
│   │       ├── WhitelistsPage.tsx
│   │       ├── ProfilesPage.tsx
│   │       ├── AgentsPage.tsx
│   │       ├── ReportsPage.tsx
│   │       ├── AuditLogPage.tsx
│   │       └── SettingsPage.tsx
│   ├── vite.config.ts
│   ├── tailwind.config.js
│   ├── Dockerfile
│   └── nginx.conf
│
└── docker/
    └── nginx.conf              # Reverse proxy config
```

## Universal Test Library (30 Tests)

The EDQ platform includes a comprehensive library of 30 security tests organized into automatic and guided manual categories:

### Automatic Tests (U01–U19)
Tests executed by scanning tools without human intervention:

| ID | Test Name | Tool | Essential |
|----|-----------|------|-----------|
| U01 | Ping Response | nmap | No |
| U02 | MAC Address Vendor Lookup | nmap | No |
| U03 | Switch Negotiation (Speed/Duplex) | ethtool | No |
| U04 | DHCP Behaviour | discovery_metadata | No |
| U05 | IPv6 Support Detection | nmap | No |
| U06 | Full TCP Port Scan (All 65535) | nmap | Yes |
| U07 | UDP Top-100 Port Scan | nmap | No |
| U08 | Service Version Detection | nmap | No |
| U09 | Protocol Whitelist Compliance | custom_rules | No |
| U10 | TLS Version Assessment | sslyze | Yes |
| U11 | Cipher Suite Strength | sslyze | No |
| U12 | Certificate Validity | sslyze | No |
| U13 | HSTS Header Presence | sslyze | No |
| U14 | HTTP Security Headers | nikto | No |
| U15 | SSH Algorithm Assessment | ssh-audit | No |
| U16 | Default Credential Check | hydra | Yes |
| U17 | Brute Force Protection | custom | No |
| U18 | HTTP vs HTTPS Redirect | curl | No |
| U19 | OS Fingerprinting | nmap | No |

### Guided Manual Tests (U20–U30)
Tests requiring human interaction and observation:

| ID | Test Name | Essential |
|----|-----------|-----------|
| U20 | Network Disconnection Behaviour | No |
| U21 | Web Interface Password Change | Yes |
| U22 | Firmware Update Mechanism | No |
| U23 | Session Timeout Validation | No |
| U24 | Physical Security (Reset/USB) | No |
| U25 | VLAN Isolation Behaviour | No |
| U26 | Multicast/Broadcast Traffic | No |
| U27 | API Authentication Check | No |
| U28 | Log Review and Audit Trail | No |
| U29 | Data-at-Rest Encryption | No |
| U30 | End-of-Life / Vendor Support | No |

## Roles & Permissions

| Role | Capabilities |
|------|-------------|
| **Admin** | Full access: user management, system configuration, all CRUD operations |
| **Reviewer** | View all data, approve/reject test results, generate reports |
| **Engineer** | Create devices, run tests, submit results |

## License

Proprietary — Electracom Ltd. All rights reserved.
