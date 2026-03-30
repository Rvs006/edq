# EDQ Security Documentation

## Authentication Flow

### Access Tokens
- JWT access tokens are issued on login and stored in **httpOnly, Secure, SameSite=strict** cookies
- Algorithm: HS256
- Default expiry: 60 minutes (`JWT_ACCESS_TOKEN_EXPIRE_MINUTES`)
- Claims: `sub` (user ID), `role` (user role), `exp` (expiration)

### CSRF Protection
- Double-submit cookie pattern: a `X-CSRF-Token` header must accompany all mutating requests to `/api/` endpoints
- CSRF token is returned on login and refresh
- Safe methods exempt: GET, HEAD, OPTIONS
- Exempt endpoints: `/api/auth/login`, `/api/auth/register`, `/api/auth/refresh`, `/api/health`

### Refresh Token Rotation
- Single-use refresh tokens stored in the database with a `token_family` identifier
- Each refresh generates a new token and invalidates the old one
- **Family revocation on reuse detection**: if a previously-used refresh token is presented, the entire token family is revoked immediately (committed to DB before raising the HTTP exception, so rollback cannot undo it)
- Each token includes a unique `jti` claim to prevent hash collisions
- Default expiry: 30 days (`JWT_REFRESH_TOKEN_EXPIRE_DAYS`)
- Background cleanup task runs hourly to purge expired tokens

### Account Lockout
- After **5 failed login attempts** (`ACCOUNT_LOCKOUT_ATTEMPTS`), the account is locked for **15 minutes** (`ACCOUNT_LOCKOUT_MINUTES`)
- Failed attempt counter resets on successful login or after the lockout period expires
- Locked account responses do not leak whether the account exists

---

## Authorization Model

### Roles
- **engineer** — default role on registration; can only access their own test runs, reports, and synopses
- **reviewer** — can view all test runs (read-only access to others' data)
- **admin** — full access to all resources, user management, and device management

### IDOR Prevention
- All test-run endpoints use `_get_authorized_test_run()` helper which enforces:
  - Engineers see only their own runs
  - Reviewers and admins see all runs
- `GET /test-runs/` and `/stats` are scoped: engineers see only their own runs/stats
- Report generation and synopsis generation verify test-run ownership
- Nessus upload and findings endpoints verify test-run ownership
- WebSocket `/ws/test-run/{run_id}` verifies ownership via `_authorize_test_run()` before accepting the connection
- Device PATCH is restricted to admin only; device DELETE was already admin-only
- User listing (`GET /users/`) is restricted to admin only with pagination

### Path Traversal Protection
- Branding logo upload and report download sanitize file paths to prevent directory traversal

---

## Rate Limiting

In-memory sliding-window rate limiter keyed by client IP and action.

| Endpoint | Limit | Window | Action Key |
|----------|-------|--------|------------|
| `POST /api/auth/login` | 5/min | 60s | `login` |
| `POST /api/auth/register` | 3/min | 60s | `register` |
| `POST /api/auth/refresh` | 5/min | 60s | `refresh` |
| `POST /api/auth/change-password` | 3/min | 60s | `change_password` |
| `POST /api/reports/generate` | 5/min | 60s | `report_generate` |
| `POST /api/synopsis/generate` | 3/min | 60s | `synopsis_generate` |
| `POST /api/discovery/scan` | 3/min | 60s | `discovery_scan` |
| `POST /api/network-scan/discover` | 3/min | 60s | `network_discover` |
| `POST /api/network-scan/start` | 3/min | 60s | `network_start` |

Client IP is extracted from `X-Forwarded-For` only when the request comes from a trusted proxy (127.0.0.1, ::1, Docker internal 172.x.x.x).

---

## Security Headers

Applied to all responses via `SecurityHeadersMiddleware`:

- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `X-XSS-Protection: 1; mode=block`
- `Referrer-Policy: strict-origin-when-cross-origin`
- `Strict-Transport-Security: max-age=31536000; includeSubDomains` (when `COOKIE_SECURE=True`)
- `Content-Security-Policy` — backend: `script-src 'self'` (no `unsafe-inline`), `style-src 'self' 'unsafe-inline'` (required for Tailwind); frontend nginx mirrors the same CSP
- `Permissions-Policy` (denies camera, microphone, geolocation, payment)
- `Cache-Control: no-store` on all `/api/` responses

**Frontend nginx** also sets: CSP, Permissions-Policy, Cache-Control, and all X- headers (matching the backend).

### Request ID Tracking
Every response includes an `X-Request-ID` header for tracing.

---

## Secret Rotation

### JWT_SECRET and JWT_REFRESH_SECRET
1. Generate new secrets: `openssl rand -hex 64`
2. Update the `.env` file with the new values
3. Restart the backend container
4. **Impact**: all existing access/refresh tokens are invalidated — users must re-login

### SECRET_KEY
1. Generate: `openssl rand -hex 32`
2. Update `.env` and restart
3. **Impact**: CSRF tokens are invalidated

### TOOLS_API_KEY
1. Generate a new key: `openssl rand -hex 32`
2. Update `TOOLS_API_KEY` in the backend `.env`
3. Update the same key in the tools sidecar `.env`
4. Restart both containers
5. **Impact**: tools sidecar requests fail until both services have the new key

### INITIAL_ADMIN_PASSWORD
- Only used on first database initialization (`init_db.py`)
- To rotate the admin password after init, use the change-password endpoint or update the database directly

---

## Audit Logging

### What Is Logged
All security events and CRUD operations are logged via the `edq.audit` logger:

**Security events** (`log_security_event`):
- `auth.register`, `auth.login`, `auth.login_failed`, `auth.token_refresh`, `auth.password_change`, `auth.logout`
- Captures: user ID, action, IP address, user agent (truncated to 512 chars)

**CRUD operations** (`log_action`):
- Resource creation, updates, and deletions across all endpoints
- Captures: user ID, action, resource type, resource ID, details, IP address

### Where Logs Are Stored
Logs are written to stdout via Python's logging module (logger name: `edq.audit`). In Docker, these are captured by the container runtime and can be forwarded to any log aggregation system.

### Reviewing Logs
```bash
# View audit logs from the backend container
docker compose logs backend | grep "Audit:"
docker compose logs backend | grep "Security:"

# Filter by user
docker compose logs backend | grep "user=<user_id>"
```

---

## Incident Response

### Compromised User Account
1. **Immediate**: lock the account by setting `locked_until` to a far-future date in the database
2. **Revoke tokens**: delete all rows in `refresh_tokens` for that user — existing access tokens expire within 60 minutes
3. **Reset password**: update the password hash directly or use the admin API
4. **Review audit logs**: search for the user's recent activity

### Detected Token Reuse (Refresh Token Theft)
The system automatically handles this:
- When a previously-used refresh token is presented, the entire token family is revoked
- The attacker's stolen token and all derived tokens become invalid
- The legitimate user's next refresh will also fail — they must re-login
- A `auth.token_refresh` security event is logged with details

### Compromised TOOLS_API_KEY
1. Rotate the key (see Secret Rotation above)
2. Review tools sidecar access logs for unauthorized `/scan/*` requests
3. The tools sidecar rejects all requests without a valid `X-Tools-Key` header

---

## Dependency Management

### Backend (Python)
- `pip-audit` runs in CI on every push/PR to `main` — fails on any known vulnerability
- Current clean versions: fastapi 0.121.0, python-jose 3.5.0, python-multipart 0.0.22
- To check locally: `pip-audit -r requirements.txt --skip-editable --desc`

### Frontend (Node.js)
- `pnpm audit --audit-level=high` runs in CI (strict — failures break the build)
- `picomatch` pinned to `>=4.0.4` via pnpm overrides to resolve ReDoS vulnerabilities
- To check locally: `cd frontend && pnpm audit`

### Upgrade Procedure
1. Update the version in `requirements.txt` or `package.json`
2. Run the audit command locally to verify no new vulnerabilities
3. Run the test suite (`pytest tests/ -v` / `pnpm run test`)
4. Commit and push — CI will validate

---

## Production Deployment Checklist

- [ ] `DEBUG=false`
- [ ] `COOKIE_SECURE=true` (requires HTTPS)
- [ ] `CORS_ORIGINS` set to the actual production domain (no `localhost`)
- [ ] `TOOLS_API_KEY` set to a strong random value (not empty)
- [ ] `JWT_SECRET` is a strong random value (not the default placeholder)
- [ ] `JWT_REFRESH_SECRET` is a strong random value (not the default placeholder)
- [ ] `SECRET_KEY` is a strong random value (not the default placeholder)
- [ ] `INITIAL_ADMIN_PASSWORD` is set explicitly before first run
- [ ] Frontend nginx runs as non-root user (configured in `frontend/Dockerfile`)
- [ ] `COOKIE_SAMESITE=strict` (default, no change needed)
- [ ] TLS termination configured (nginx or load balancer)
- [ ] Log aggregation configured for `edq.audit` logger output
- [ ] Nessus file upload limited to 10MB (`MAX_NESSUS_FILE_SIZE`)

---

## Tools Sidecar Security

- All `/scan/*` endpoints require the `X-Tools-Key` header matching `TOOLS_API_KEY`
- The sidecar should not be exposed to the public internet — only the backend communicates with it
- Network policy: restrict tools container to backend-only access via Docker networking

---

## WebSocket Security

- All WebSocket endpoints (`/ws/test-run/{run_id}`, `/ws/discovery/{task_id}`, `/ws/agents`) require JWT authentication via the httpOnly session cookie
- Unauthenticated connections are closed with `WS_1008_POLICY_VIOLATION`
- `/ws/test-run/{run_id}` enforces IDOR: engineers can only subscribe to their own test runs; admins and reviewers can subscribe to any
- WebSockets bypass CSRF (by design — no mutating state from WS messages), but JWT validation prevents unauthorized access

---

## File Upload Security

- Nessus XML uploads are limited to `MAX_NESSUS_FILE_SIZE` (10MB default)
- General file uploads limited to `MAX_FILE_SIZE` (50MB default)
- Nessus files are parsed with `defusedxml` to prevent XXE attacks
- Branding logo paths are sanitized to prevent directory traversal
