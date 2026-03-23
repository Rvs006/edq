# EDQ — Electracom Device Qualifier

> Automated cybersecurity qualification testing for smart building IP devices.

[![License](https://img.shields.io/badge/license-Proprietary-blue.svg)]()
[![Docker](https://img.shields.io/badge/docker-compose-2496ED.svg)]()
[![Python](https://img.shields.io/badge/python-3.12-3776AB.svg)]()
[![React](https://img.shields.io/badge/react-18-61DAFB.svg)]()

---

## What is EDQ?

EDQ automates the security qualification of IP-connected smart building devices — cameras, HVAC controllers, intercoms, access control systems, and IoT sensors. It replaces a manual process that takes a full working day per device with an automated workflow that completes in 1–2 hours.

**Key capabilities:**
- **43 security tests** mapped to ISO 27001, Cyber Essentials, and SOC2
- **28 automated tests** via nmap, testssl.sh, ssh-audit, hydra, nikto
- **15 guided manual tests** with structured single-click forms
- **3 report formats** — Excel (template-based), Word, PDF
- **3 verdict levels** — Pass, Qualified Pass, Fail
- **100% offline** — runs entirely on a test laptop via Docker
- **Desktop app** — Electron wrapper with system tray and auto-updater

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

## Quick Start

### Prerequisites
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (Windows/macOS/Linux)
- Git

### Run
```bash
git clone https://github.com/Rvs006/edq.git
cd edq
docker compose up --build
```

Open `http://localhost` in your browser.

**Default login:** `admin@electracom.co.uk` / `Admin123!`

### Stop
```bash
docker compose down
```

## Project Structure

```
edq/
├── frontend/          # React 18 + Vite + Tailwind CSS
├── server/backend/    # FastAPI + SQLAlchemy + SQLite
├── tools/             # Security tools sidecar (nmap, testssl, etc.)
├── electron/          # Desktop app wrapper
├── templates/         # Excel report templates (.xlsx)
├── docker/            # nginx config
├── scripts/           # Integration test scripts
├── docker-compose.yml
├── PRD.md             # Product Requirements Document
├── ENGINEERING_SPEC.md # Technical specification
└── DESIGN_SYSTEM.md   # UI design tokens
```

## Features

### Security Testing
- Full TCP port scan (all 65535 ports)
- UDP top-100 port scan
- TLS version and cipher suite assessment
- SSH algorithm analysis
- Default credential checking
- HTTP security header verification
- Protocol whitelist compliance
- Nessus vulnerability scan import (.nessus)

### Reporting
- **Excel** — Template-based, preserves original Electracom formatting (Pelco, EasyIO, Generic)
- **Word** — Styled cover page, executive summary, colour-coded results
- **PDF** — Generated via LibreOffice headless conversion

### Desktop App
- Electron-based installer for Windows/macOS/Linux
- Automatic Docker container management
- System tray with service controls
- Splash screen with startup status

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 18, Vite, Tailwind CSS, Zustand, TanStack Query, xterm.js |
| Backend | Python 3.12, FastAPI, SQLAlchemy 2.0, Pydantic |
| Database | SQLite (WAL mode) |
| Tools | nmap, testssl.sh, ssh-audit, hydra, nikto |
| Desktop | Electron, electron-builder |
| Infra | Docker Compose, nginx |

## API Documentation

The backend serves interactive API docs at:
- **Swagger UI:** `http://localhost:8000/docs`
- **ReDoc:** `http://localhost:8000/redoc`

## Development

### Backend
```bash
cd server/backend
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

## License

Proprietary — Electracom Projects Ltd, a Sauter Group Company.

## Author

Developed by Rajesh Shinde for Electracom Projects Ltd.
