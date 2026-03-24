# Testing EDQ App Locally

## Devin Secrets Needed
- None required for local testing (default login: admin / Admin123!)

## Local Setup

### Backend (FastAPI)
```bash
cd server/backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
nohup python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 > /tmp/backend.log 2>&1 &
```
Verify: `curl -s http://localhost:8000/api/health` should return `{"status":"ok",...}`

Note: The `tools_sidecar` will show as `unreachable` — this is expected locally since nmap/testssl aren't running.

### Frontend (Vite + React)
```bash
cd frontend
npx vite --port 5174 --host 0.0.0.0
```
Note: If port 5174 is taken, Vite will auto-increment (5175, 5176, etc.). Check the terminal output for the actual port.

### Login
- URL: http://localhost:{frontend_port}
- Username: `admin`
- Password: `Admin123!`
- The app auto-redirects to login if not authenticated

## Key Pages & Routes

| Page | Route | Sidebar Section |
|------|-------|----------------|
| Dashboard | `/` | Main |
| Devices | `/devices` | Main |
| Device Profiles | `/device-profiles` | Main |
| Test Runs | `/test-runs` | Main |
| Network Scan | `/network-scan` | Main |
| Templates | `/templates` | Tools |
| Test Plans | `/test-plans` | Tools |
| Whitelists | `/whitelists` | Tools |
| Reports | `/reports` | Tools |
| Agents | `/agents` | System |
| Review Queue | `/review` | Admin |
| Users | `/admin` | Admin |
| Audit Log | `/audit-log` | Admin |
| Settings | `/settings` | Admin |

## Settings Sub-Tabs
Settings page has 5 tabs: Profile, Security, Appearance, Report Branding, System Status

## Theme Testing
- **ThemeToggle** is in the sidebar footer (Light / System / Dark buttons)
- **Settings > Appearance** has the same 3 options as larger cards
- Both controls use the same `ThemeContext` and `edq-theme` localStorage key
- Changing theme in one place should immediately update the other
- Dark mode adds `dark` class to `<html>` element

## Agent Fleet Testing
- The Agents page (`/agents`) uses demo data when the backend has no registered agents
- Demo data shows 4 agents with different statuses (2 online, 1 busy/scanning, 1 offline)
- Heartbeat simulation updates every 5 seconds for online/busy agents
- Alex-Dell shows an amber version warning badge (0.9.8 vs 1.0.0)
- WebSocket connection to `/ws/agents` — might show connection errors in console (expected if WS endpoint isn't available)

## Device Profiles Testing
- 5 profiles: IP Camera (15 tests), Access Controller (10), IoT Gateway (11), Intercom/VoIP (10), Generic (6)
- Clicking a profile shows its included test IDs in a detail panel below
- Clicking again deselects and returns to empty state
- Each profile has a color-coded card (blue, purple, green, amber, zinc)

## Features That Require Real Data (Hard to Test Locally)
- **Keyboard navigation (j/k)**: Needs a test run with results in the TestSidebar
- **CSV export**: Needs test run results on TestRunDetailPage
- **SmartPrompt banner**: Needs guided_manual test results
- **Progressive discovery animation**: Needs nmap scan (tools sidecar)
- **Network scan**: Needs tools sidecar running
- **Windows .ico icon**: Needs Electron build to verify

## Running Tests
```bash
cd frontend
pnpm run test        # or: npx vitest run
pnpm run build       # verify production build
```

## Common Issues
- If `venv` doesn't exist, create it with `python3 -m venv venv`
- Frontend port may differ from expected — always check Vite output
- The `edq.db` SQLite database is auto-created on first backend start via `init_db()`
- WebSocket errors in console are expected when no WS server is available
