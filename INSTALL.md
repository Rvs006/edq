# EDQ Installation Guide

## Prerequisites

### Required Software
1. **Docker Desktop** (Windows/macOS/Linux)
   - Download: https://www.docker.com/products/docker-desktop/
   - During installation, enable **WSL 2 backend** (Windows)
   - Minimum 4GB RAM allocated to Docker (Settings → Resources → Memory)

2. **Git** (for cloning the repository)
   - Download: https://git-scm.com/download/win

### Corporate Environment (ThreatLocker / Endpoint Protection)
If your organisation uses ThreatLocker or similar endpoint protection:
1. Request IT to whitelist: `Docker Desktop.exe`, `com.docker.backend.exe`, `vpnkit.exe`, `wsl.exe`
2. Enable **Learning Mode** during first install
3. You will need **administrator rights** for Docker installation

---

## Quick Start (5 Minutes)

### 1. Clone the Repository
```powershell
git clone https://github.com/Rvs006/edq.git
cd edq
```

### 2. Configure Environment
```powershell
copy .env.example .env
```
Edit `.env` and set all required secrets:
```
JWT_SECRET=<generate-with: openssl rand -hex 64>
JWT_REFRESH_SECRET=<generate-with: openssl rand -hex 64>
SECRET_KEY=<generate-with: openssl rand -hex 32>
TOOLS_API_KEY=<generate-with: openssl rand -hex 32>
INITIAL_ADMIN_PASSWORD=<your-strong-admin-password>
```
> **Tip:** If you use the Electron desktop app, these are auto-generated on first launch.

### 3. Build and Start
```powershell
docker compose up --build -d
```
First build takes **5-10 minutes** (downloads base images, installs dependencies).

### 4. Verify
```powershell
docker compose ps
```
All 3 services should show `healthy` or `running`.

Open http://localhost in your browser.

---

## Default Login Credentials

| Field | Value |
|-------|-------|
| Username | `admin` |
| Password | Value of `INITIAL_ADMIN_PASSWORD` from your `.env` file |

If `INITIAL_ADMIN_PASSWORD` was not set, a random password is printed to the backend container logs on first start:
```powershell
docker compose logs backend | findstr "INITIAL_ADMIN_PASSWORD"
```

**Change this password immediately after first login via your profile settings.**

---

## Testing Checklist

After installation, verify these flows work:

| # | Test | Expected Result |
|---|------|----------------|
| 1 | Open http://localhost | Login page with Electracom branding |
| 2 | Login with admin credentials | Dashboard with statistics cards |
| 3 | Navigate to Devices → Add Device | Enter any IP (e.g. 192.168.1.1) |
| 4 | Start a Test Run on a device | Automated tests begin, terminal shows output |
| 5 | Complete manual tests | Pass/Fail buttons work with notes |
| 6 | Generate Excel report | .xlsx downloads with correct template formatting |
| 7 | Network Scan page | Enter subnet CIDR, discover devices |
| 8 | Admin → User Management | Create/edit users with roles |

---

## Connecting a Real Device

1. Connect the device under test via **Cat6 Ethernet cable** to the laptop
2. Ensure the laptop and device are on the **same subnet** (e.g. 192.168.1.x)
3. In EDQ, create a new device with the device's IP address
4. Start a test run — automated scans will execute via the tools sidecar container
5. If the device is not connected yet, EDQ will **pause before tests begin** and wait for the cable or device to come back
6. If the Cat6 cable comes loose during testing, the **Wobbly Cable Handler** will pause the run automatically and resume when the device is reachable again

---

## Common Issues

| Problem | Solution |
|---------|----------|
| Port 80 already in use | Run `netstat -ano \| findstr :80` to find the conflicting service. Stop it, or edit `docker-compose.yml` to use port 8080 instead |
| ThreatLocker blocks Docker | Whitelist Docker executables (see Prerequisites above) |
| Tools sidecar unhealthy | Run `docker compose logs tools` — nmap needs NET_RAW capability (already configured in docker-compose.yml) |
| "Database locked" error | Normal under heavy concurrent load — SQLite WAL mode handles it, just retry the operation |
| Build fails on Windows | Ensure `.gitattributes` has `* text=auto eol=lf` (already configured) |
| Frontend shows blank page | Run `docker compose logs frontend` — check nginx proxy configuration |

---

## Daily Operations

### Start EDQ
```powershell
cd edq
docker compose up -d
```

### Stop EDQ
```powershell
docker compose down
```

### View Logs
```powershell
# All services
docker compose logs -f

# Specific service
docker compose logs -f backend
docker compose logs -f tools
docker compose logs -f frontend
```

### Update to Latest Version
```powershell
git switch main
git pull --ff-only origin main
docker compose up --build -d
```

Or on Windows:

```powershell
.\update.bat
```

On macOS / Linux:

```bash
./update.sh
```

### Reset Database
```powershell
docker compose down
del data\edq.db
docker compose up -d
```
This recreates the database with default seed data.

---

## Database Migrations (Alembic)

EDQ uses [Alembic](https://alembic.sqlalchemy.org/) for database schema migrations. This is relevant when updating to a new version that changes the database schema.

### Apply Pending Migrations
```powershell
docker compose exec backend alembic upgrade head
```

### Check Current Migration Status
```powershell
docker compose exec backend alembic current
```

### Create a New Migration (Developers)
```powershell
cd server/backend
alembic revision --autogenerate -m "describe_your_change"
alembic upgrade head
```

For fresh installs, the database is automatically created with seed data on first startup. Alembic is only needed for incremental schema changes after the initial deployment.

---

## API Documentation

When EDQ is running, interactive API documentation is available at:
- **Swagger UI:** http://localhost:8000/docs
- **ReDoc:** http://localhost:8000/redoc

---

## Architecture Overview

EDQ runs as 3 Docker containers:

| Container | Port | Purpose |
|-----------|------|---------|
| `frontend` (nginx) | 80 | Serves React SPA, proxies /api/* to backend |
| `backend` (FastAPI) | 8000 | REST API, WebSocket, database, reports |
| `tools` (Ubuntu) | 8001 | Security scanning tools (nmap, testssl.sh, ssh-audit, hydra, nikto) |

Data is stored in a SQLite database mounted at `./data/edq.db`.

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
