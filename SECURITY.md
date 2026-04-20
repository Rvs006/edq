# EDQ Security Notes

This document reflects the current application behavior in the repository. It is not a generic security policy.

## Authentication Model

- Login accepts either username or email.
- `POST /api/auth/login` issues:
  - an access token cookie
  - a refresh token cookie
  - a CSRF cookie
- Access tokens are stored in httpOnly cookies.
- Refresh tokens are rotated and stored server-side as hashes.
- Optional TOTP-based 2FA is enforced per account when configured.
- Optional OIDC login is available only when OIDC settings are configured.

## Current Cookie and Session Behavior

- `COOKIE_SECURE=false` is required for plain `http://localhost` testing.
- Set `COOKIE_SECURE=true` only when EDQ is served behind HTTPS.
- CSRF protection applies to mutating `/api/` requests except exempt auth and health endpoints.

## Registration and User Roles

- Public self-registration is disabled by default with `ALLOW_REGISTRATION=false`.
- Roles:
  - `engineer`: works on assigned or owned testing flows
  - `reviewer`: reviews and overrides results where allowed
  - `admin`: full administrative access

## Health and Debug Endpoints

Public endpoints:

- `GET /api/health`
- `GET /api/health/metrics`

Authenticated endpoints:

- `GET /api/health/tools/versions`
- `GET /api/health/system-status`

Interactive backend docs are available only when `DEBUG=true`.

## Current Health Contract

`GET /api/health` currently returns JSON with:

- `status`
- `database`

It does not return the older multi-service payload described in archived specs.

## Secret Handling

Required settings:

- `JWT_SECRET`
- `JWT_REFRESH_SECRET`
- `SECRET_KEY`
- `TOOLS_API_KEY`
- `INITIAL_ADMIN_PASSWORD`

Current local handoff model:

- the supported local config file is the root `.env`
- placeholder values should not be used for real runs
- setup scripts generate missing required secrets automatically for local installs

## Secret Rotation

### JWT secrets

Rotate:

- `JWT_SECRET`
- `JWT_REFRESH_SECRET`

Impact:

- existing sessions are invalidated
- users must log in again

### `SECRET_KEY`

Impact:

- CSRF tokens are invalidated

### `TOOLS_API_KEY`

Impact:

- backend-to-tools requests fail until the backend process is using the rotated key for its co-located tools sidecar integration

Recommended restart:

```bash
docker compose restart backend
```

### Initial admin password

`INITIAL_ADMIN_PASSWORD` is only used when the admin account is first seeded.

After first login, rotate the password through the app or reset the stored password hash directly if needed.

## Scan Controls

- EDQ includes active network scan tooling.
- Subnet scanning is blocked until an admin adds authorized networks in the app.
- The tools sidecar should never be exposed directly to untrusted networks.

## Incident Response Basics

Compromised user:

1. deactivate the account or change its role as admin
2. revoke sessions for that user
3. rotate the password
4. review audit logs

Compromised admin password:

1. reset the password
2. review recent admin actions
3. rotate secrets if broader compromise is suspected

Compromised tools key:

1. rotate `TOOLS_API_KEY`
2. restart backend
3. review logs around scan activity

## Production Hardening Checklist

- `DEBUG=false`
- `COOKIE_SECURE=true`
- real `CORS_ORIGINS`
- no placeholder secrets
- private network or VPN-only exposure
- authorized networks configured for scanning
- log retention and backups defined
