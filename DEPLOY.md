# EDQ Deployment Guide

Quick-reference for deploying and operating EDQ (Electracom Device Qualifier).

---

## System Requirements

- **Docker Desktop** with at least **4 GB RAM** allocated
- **Git** for cloning the repository
- **Network access** to devices under test (e.g., 192.168.1.x subnet)
- Ports **80** (web UI) and **8000/8001** (backend/tools, localhost only)

---

## First-Time Setup

```bash
# 1. Clone and enter the project
git clone https://github.com/Rvs006/edq.git
cd edq

# 2. Create .env from template
cp .env.example .env

# 3. Generate secrets (Linux/macOS)
sed -i "s/CHANGE_ME_JWT_SECRET/$(openssl rand -hex 32)/" .env
sed -i "s/CHANGE_ME_REFRESH/$(openssl rand -hex 32)/" .env
sed -i "s/CHANGE_ME_SECRET/$(openssl rand -hex 16)/" .env
sed -i "s/CHANGE_ME_TOOLS/$(openssl rand -hex 16)/" .env

# On Windows (PowerShell) — edit .env manually or use setup.bat
.\setup.bat

# 4. Start all services
docker compose up --build -d
```

Services take ~60 seconds to become healthy on first build.

---

## Accessing the App

| What | URL |
|------|-----|
| Web UI | `http://<server-ip>` (or `http://localhost`) |
| API health check | `http://localhost:8000/api/health` |

### Default Admin Login

- **Username:** `admin`
- **Password:** Set via `INITIAL_ADMIN_PASSWORD` in `.env`

---

## Day-to-Day Operations

### Start / Stop / Rebuild

```bash
# Start (detached)
docker compose up -d

# Stop (data is preserved)
docker compose down

# Rebuild after code changes
docker compose up --build -d

# View logs
docker logs edq-backend --tail 50
docker logs edq-frontend --tail 50
docker logs edq-tools --tail 50
```

### Adding Devices and Running Tests

1. Navigate to **Devices** in the sidebar
2. Click **Add Device** — enter IP address, hostname, and category
3. Go to **Test Runs** → **New Test Run**
4. Select device, choose test template, and start
5. Monitor progress via the live progress bar

### Generating Reports

1. Open a **completed** test run
2. Click the **Reports** dropdown
3. Choose format: **Excel**, **Word**, or **PDF**
4. Report downloads automatically

### Creating Engineer Accounts

1. Log in as **admin**
2. Go to **Admin** → **Users**
3. Click **Add User**
4. Fill in: username, full name, role (`engineer` / `reviewer`), password

---

## Data Persistence

EDQ uses Docker named volumes — data survives `docker compose down` and rebuilds.

| Volume | Contents |
|--------|----------|
| `edq-data` | SQLite database (`edq.db`) |
| `edq-uploads` | Uploaded files and attachments |
| `edq-reports` | Generated report files |

**Warning:** Running `docker compose down -v` or `docker volume rm` **deletes all data**.

---

## Network Scanning

1. Go to **Network Scan** in the sidebar
2. Enter a subnet (e.g., `192.168.1.0/24`)
3. Click **Scan** — radar animation shows during discovery
4. Discovered devices appear in grid/tree view with services and OS info
5. Select devices to start batch testing directly from scan results

---

## Troubleshooting

### Reset Admin Password

```bash
docker exec edq-backend python -c "
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from app.security.auth import hash_password
async def reset():
    new_hash = hash_password('NEW_PASSWORD_HERE')
    engine = create_async_engine('sqlite+aiosqlite:///./data/edq.db')
    async with engine.begin() as conn:
        await conn.execute(text('UPDATE users SET password_hash = :h WHERE username = :u'), {'h': new_hash, 'u': 'admin'})
    print('Password reset OK')
asyncio.run(reset())
"
```

### Check Container Health

```bash
docker compose ps
curl http://localhost/api/health
```

### Common Issues

| Problem | Fix |
|---------|-----|
| Port 80 already in use | Stop IIS/Apache/nginx or change port in `docker-compose.yml` |
| Backend unhealthy | Check `.env` exists and secrets are set. Run `docker logs edq-backend` |
| Tools sidecar unhealthy | Run `docker logs edq-tools` — check nmap/testssl installed |
| PDF generation fails | Rebuild backend: `docker compose up --build -d backend` |
| Database locked errors | Restart backend: `docker compose restart backend` |
| Permission denied (Docker) | Run Docker Desktop as administrator, or add user to `docker` group |

### Full Reset (Destroys All Data)

```bash
docker compose down -v
docker compose up --build -d
```

---

## Architecture

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Frontend    │────▶│  Backend    │────▶│  Tools      │
│  (nginx:80) │     │  (FastAPI)  │     │  (nmap,ssl) │
└─────────────┘     └─────────────┘     └─────────────┘
                          │
                    ┌─────┴─────┐
                    │  SQLite   │
                    │  (edq.db) │
                    └───────────┘
```

- **Frontend**: React + Vite, served by nginx with reverse proxy to backend
- **Backend**: FastAPI + SQLAlchemy, handles auth, tests, reports
- **Tools**: Ubuntu sidecar with nmap, testssl.sh, ssh-audit, hydra, nikto
