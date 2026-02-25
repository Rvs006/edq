# EDQ App Progress Notes

## Working Pages Verified
1. Login page - dark-themed branding, JWT auth works (admin/admin123)
2. Dashboard - stats cards, quick actions, compliance frameworks
3. Devices page - list, add device modal, device cards with details
4. Templates page - Universal Test Library with all 30 tests displayed in table
5. All sidebar navigation links working

## API Fix Applied
- Added trailing slashes to all API URLs in frontend api.ts to match FastAPI route patterns

## Architecture
- Backend: FastAPI on port 8000 serving both API and built frontend
- Frontend: React + Vite (built to dist, served by FastAPI)
- Database: SQLite at /home/ubuntu/edq/server/backend/edq.db
- Auth: Custom JWT (not Manus OAuth)

## Remaining Pages to Test
- Test Runs, Whitelists, Profiles, Agents, Reports, Audit Log, Settings
- Mobile responsiveness
