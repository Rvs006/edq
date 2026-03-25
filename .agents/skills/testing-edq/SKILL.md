# Testing EDQ Application

## Overview
EDQ (Electracom Device Qualifier) is a cybersecurity qualification testing platform for smart building IP devices. It runs as a 3-service Docker Compose stack: backend (FastAPI), frontend (React + nginx), and tools sidecar (security tools).

## Devin Secrets Needed
No external secrets needed. The app uses default seeded credentials.

## Quick Start
```bash
cd /home/ubuntu/repos/edq
cp .env.example .env
docker compose up --build -d
# Wait ~60-120s for all services to become healthy
docker compose ps  # Verify all 3 services show 'healthy'
```

## Default Credentials
- **Username**: `admin` (NOT the email)
- **Password**: `Admin123!`
- **Login endpoint**: POST `/api/auth/login` with JSON body `{"username": "admin", "password": "Admin123!"}`
- The backend uses cookie-based auth with CSRF tokens (not Bearer tokens)

## Service Ports
- Frontend: http://localhost (port 80)
- Backend API: http://localhost:8000 (also proxied via nginx at `/api/`)
- Tools Sidecar: http://localhost:8001

## Frontend Navigation Structure
The sidebar has 4 sections with 15 navigation items:
- **Main**: Dashboard, Devices, Device Profiles, Test Runs, Network Scan
- **Tools**: Templates, Test Plans, Scan Schedules, Whitelists, Reports
- **System**: Agents
- **Admin**: Review Queue, Users, Audit Log, Settings

## Key Testing Flows
1. **Device CRUD**: Devices > Add Device > fill form > submit. Device appears in table and detail page.
2. **Dark Mode**: Toggle Light/System/Dark in sidebar footer or Settings > Appearance.
3. **Templates**: View seeded templates (4) and Universal Test Library (43 tests).
4. **Settings**: 5 tabs - Profile, Security, Appearance, Report Branding, System Status.
5. **Admin**: Users tab (user management) and System tab (version info, security tools).
6. **Audit Log**: Shows system events with filter pills and CSV export.
7. **Reports**: Generate Excel/Word/PDF from completed test runs.
8. **Logout/Login**: User menu dropdown > Sign Out > Landing page > Sign In.

## Known Issues & Workarounds
- **Empty string validation**: The frontend may send empty strings (`""`) for optional form fields, which can fail backend Pydantic validators (e.g., MAC address regex). Fixed in PR #37 by filtering empty strings before API calls. If similar issues appear in other forms, apply the same pattern: `Object.fromEntries(Object.entries(form).filter(([, v]) => v !== ''))`.
- **Whitelists may not be seeded**: Depending on database state, whitelists might show empty. The init_db.py seeds them on first run only.
- **Security tools on System tab**: The Admin > System tab may show tools as "Not Found" because they're installed in the tools sidecar container, not the backend container. The Settings > System Status tab correctly queries the sidecar and shows tool versions.

## Rebuilding After Code Changes
```bash
# Rebuild only the changed service
docker compose up --build -d frontend  # or backend, tools
# Full rebuild
docker compose up --build -d
```

## Health Verification
```bash
curl http://localhost:8000/api/health
# Expected: {"status": "ok", "database": "connected", "tools_sidecar": "healthy"}
curl -s -o /dev/null -w "%{http_code}" http://localhost
# Expected: 200
```

## CI Pipeline
GitHub Actions runs 3 jobs: `frontend-build`, `backend-lint-test`, `docker-build`. All must pass before merging.
