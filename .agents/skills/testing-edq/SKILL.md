# Testing EDQ End-to-End

## Prerequisites
- Docker Desktop installed and running
- Repository cloned with `.env` file configured (copy from `.env.example`)

## Starting the App
```bash
docker compose up --build -d
```
Wait for all 3 containers to be healthy:
- `edq-backend` (port 8000) — FastAPI backend
- `edq-frontend` (port 80) — Nginx + React frontend  
- `edq-tools` (port 8001) — Security scanning tools

Check health: `docker compose ps` — all should show "healthy" or "Up"

## Devin Secrets Needed
- No external secrets required for local testing
- Default admin credentials are seeded on first run

## Login
- **URL**: http://localhost (frontend) or http://localhost:8000 (backend API)
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

### Scan Schedules (API-only, no dedicated UI page)
- CRUD endpoints at `/api/scan-schedules/`
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

## Common Issues
- If login fails with "Invalid credentials", verify you're using `admin` (username) not `admin@electracom.co.uk` (email)
- If containers aren't starting, check Docker Desktop is running and ports 80/8000/8001 aren't in use
- Database is SQLite at `./data/edq.db` — delete this file to reset all data (admin user is re-seeded on startup)
- Backend dependencies may need rebuilding after code changes: `docker compose up --build -d`
