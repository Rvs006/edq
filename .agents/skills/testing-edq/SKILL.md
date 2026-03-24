# EDQ App Testing

## Local Setup

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

### Default Login
Use the seeded admin credentials printed in the backend startup logs.

## Port Conflicts
If port 8000 is already in use:
```bash
fuser -k 8000/tcp
```
Note: `lsof` may not be available on the system; use `fuser` instead.

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
- Some sidebar items are small and close together. If clicking doesn't navigate to the right page, use the URL bar directly (e.g., `localhost:5175/test-runs`, `localhost:5175/review-queue`)
- The sidebar scrolls if the window is short — scroll down to find the theme toggle

## Devin Secrets Needed
No additional secrets required beyond the default seeded credentials (printed in backend startup logs).

## Known Limitations
- Discovery scan requires nmap/tools sidecar (not available locally)
- SmartPrompt only shows when test run data with guided_manual tests exists
- Windows .ico icon verification requires Electron build
- Agent heartbeat uses demo data when backend WebSocket agents endpoint has no real agents
