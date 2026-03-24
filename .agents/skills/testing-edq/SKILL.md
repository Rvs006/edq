# Testing EDQ End-to-End

## Prerequisites
- Docker Desktop installed and running
- Repository cloned with `.env` file configured (copy from `.env.example`)

## Starting the App (Docker — Recommended)
```bash
docker compose up --build -d
```
Wait for all 3 containers to be healthy:
- `edq-backend` (port 8000) — FastAPI backend
- `edq-frontend` (port 80) — Nginx + React frontend  
- `edq-tools` (port 8001) — Security scanning tools

Check health: `docker compose ps` — all should show "healthy" or "Up"

## Local Setup (Alternative — No Docker)

### Backend
```bash
source /home/ubuntu/repos/edq/server/backend/venv/bin/activate
cd /home/ubuntu/repos/edq/server/backend
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Frontend
```bash
cd /home/ubuntu/repos/edq/frontend
npm run dev -- --port 5175 --host 0.0.0.0
```

## Port Conflicts
If port 8000 is already in use:
```bash
fuser -k 8000/tcp
```
Note: `lsof` may not be available on the system; use `fuser` instead.

## Devin Secrets Needed
- No external secrets required for local testing
- Default admin credentials are seeded on first run

## Login
- **URL**: http://localhost (Docker frontend) or http://localhost:5175 (local dev) or http://localhost:8000 (backend API)
- **Username**: `admin` (NOT the email — the login form uses username field)
- **Password**: `Admin123!`
- **Important**: The login field is labeled "Username", not "Email". Use `admin`, not `admin@electracom.co.uk`.

## API Authentication
For curl-based API testing:
```bash
# Login and save cookies
curl -s -c /tmp/cookies.txt http://localhost:8000/api/auth/login \
  -X POST -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"Admin123!"}'

# Extract CSRF token from response
CSRF_TOKEN="<token from login response>"

# Use cookies + CSRF for subsequent requests
curl -s -b /tmp/cookies.txt -H "X-CSRF-Token: $CSRF_TOKEN" http://localhost:8000/api/devices/
```
- GET requests only need the cookie (`-b /tmp/cookies.txt`)
- POST/PUT/PATCH/DELETE requests also need the CSRF header (`-H "X-CSRF-Token: $CSRF_TOKEN"`)

## Key Testing Areas

### Network Topology View
- Navigate to Devices page → click the Network icon (second toggle button in top-right toolbar)
- Shows SVG with central GATEWAY node and device nodes connected by dashed lines
- Each device shows category icon, IP address, and hostname
- Status legend in bottom-left (Qualified, Tested, Testing, Failed)
- Toggle back to table view with the Grid icon (first toggle button)
- **Note**: Devices added via API may require a page refresh to appear in topology (TanStack Query caching)

### Scan Schedules
- Navigate to Scan Schedules page via sidebar (under TOOLS section)
- Full CRUD UI: create, pause/resume, delete schedules
- CRUD endpoints also at `/api/scan-schedules/`
- Requires a device ID and template ID to create a schedule
- Frequencies: `daily`, `weekly`, `monthly`
- Diff endpoint: `GET /api/scan-schedules/{id}/diff`

### Pagination
- All list endpoints accept `?skip=N&limit=N` query params
- Device list returns a plain JSON array
- Audit log list returns a paginated dict: `{items: [...], total: N, skip: N, limit: N}`
- Different response structures — check the actual response format before asserting

### Input Sanitization
- HTML tags are stripped from text fields (e.g., `<script>` removed from hostnames)
- Uses Bleach library on the backend

### API Versioning
- Both `/api/` and `/api/v1/` prefixes work identically
- All routes are dual-mounted

### Audit Log
- Navigate to Audit Log page in sidebar (under ADMIN section)
- Shows all CRUD operations with action type, user, details, and timestamp
- Filter tabs: All, device created, test run started, test run completed, report generated, user login
- Export CSV button available

## Theme / Dark Mode Testing

### How to Toggle
1. **Sidebar footer**: Three buttons at bottom — Light | System | Dark
2. **Settings > Appearance tab**: Three large cards — Light | Dark | System
   - The Appearance tab is between Security and Report Branding in the settings sidebar
   - Click precisely; Report Branding is very close below Appearance

### What to Verify in Dark Mode
- Page body backgrounds should be dark zinc (not white)
- Card backgrounds: `bg-zinc-900` (very dark)
- Text colors: light zinc (`text-zinc-100` for headings, `text-zinc-400` for secondary)
- Table headers: dark backgrounds with light text
- Borders: `border-zinc-700` or `border-zinc-800`
- No white "flash" elements on any page

### Pages to Check
All 12 page bodies need dark mode variants:
- Dashboard, Devices, Device Profiles, Test Runs, Test Run Detail
- Network Scan, Templates, Reports, Review Queue
- Audit Log, Admin/Users, Settings, Agents

### Bidirectional Toggle Test
Always verify toggling Dark > Light restores white backgrounds and dark text.
Also verify Settings Appearance tab and sidebar footer toggle stay in sync.

## Navigation Tips
- Some sidebar items are small and close together. If clicking doesn't navigate to the right page, use the URL bar directly (e.g., `localhost/test-runs`, `localhost/review-queue`)
- The sidebar scrolls if the window is short — scroll down to find the theme toggle

## Common Issues
- If login fails with "Invalid credentials", verify you're using `admin` (username) not `admin@electracom.co.uk` (email)
- If containers aren't starting, check Docker Desktop is running and ports 80/8000/8001 aren't in use
- Database is SQLite at `./data/edq.db` — delete this file to reset all data (admin user is re-seeded on startup)
- Backend dependencies may need rebuilding after code changes: `docker compose up --build -d`

## Known Limitations
- Discovery scan requires nmap/tools sidecar (not available locally without Docker)
- SmartPrompt only shows when test run data with guided_manual tests exists
- Windows .ico icon verification requires Electron build
- Agent heartbeat uses demo data when backend WebSocket agents endpoint has no real agents
