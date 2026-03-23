# EDQ Development & Testing Skills

## Local Development Environment

### Starting the app
```bash
cd /home/ubuntu/repos/edq
docker compose up --build -d
```
Wait for all 3 containers to be healthy: `docker compose ps`
- **frontend** (NGINX + React): port 80
- **backend** (FastAPI + Python): port 8000
- **tools** (security tools sidecar): port 8001

### Default credentials
- Username: `admin`
- Password: `Admin123!`
- Email: `admin@electracom.co.uk`
- Role: admin

The admin user is auto-seeded on first startup.

### Health check
```bash
curl http://localhost:8000/api/health
# Returns: {"status":"ok","database":"connected","tools_sidecar":"healthy"}
```

## Testing Patterns

### Running backend tests
```bash
cd server/backend
pip install -r requirements.txt
pip install pytest pytest-asyncio httpx
pytest
```

### Running lint
```bash
cd server/backend
ruff check app/
```
Note: ruff is configured to ignore E402, E501, E712, F401, F841 for pre-existing issues.

### Testing auth endpoints via API
- Login: `POST /api/auth/login` with `{"username": "...", "password": "..."}`
- Register: `POST /api/auth/register` with `{"email": "...", "username": "...", "password": "...", "full_name": "..."}`
- Rate limiter is keyed by client IP via `X-Forwarded-For` header
- To bypass rate limiting during testing, use different `X-Forwarded-For` values per request
- Login rate limit: 5 requests/minute per IP
- Register rate limit: 3 requests/minute per IP

### Testing account lockout
- Account locks after 5 failed login attempts (15 min cooldown)
- Use different `X-Forwarded-For` IPs to avoid rate limiter while testing lockout
- Reset lockout via SQLite: `docker exec edq-backend python3 -c "import sqlite3; conn = sqlite3.connect('/app/data/edq.db'); conn.execute('UPDATE users SET failed_login_attempts = 0, locked_until = NULL WHERE username = \"admin\"'); conn.commit()"`

### Password complexity requirements
- Minimum 8 characters
- At least 1 uppercase letter
- At least 1 lowercase letter
- At least 1 digit

## Known Gotchas

### SQLite datetime handling
SQLite stores naive datetimes (no timezone info). All Python datetime comparisons must use naive UTC datetimes. The `_utcnow()` helper in `auth.py` handles this: `datetime.now(timezone.utc).replace(tzinfo=None)`.

### Dependency quirks
- `pydantic[email]` extra is required (not just `pydantic`) because `EmailStr` is used in schemas
- `bcrypt` must be pinned to `4.1.3` — bcrypt 5.x is incompatible with `passlib[bcrypt]==1.7.4` (72-byte password limit issue)
- Both are in `server/backend/requirements.txt`

### Docker non-root users
- Backend runs as `edq` user
- Tools sidecar runs as `edqtools` user
- Nmap in tools container requires `NET_RAW`/`NET_ADMIN` capabilities (verify `cap_add` in docker-compose.yml)

### Database location
- SQLite database: `./data/edq.db` (mounted as Docker volume)
- WAL mode enabled with `busy_timeout=5000`, `foreign_keys=ON`, `synchronous=NORMAL`
