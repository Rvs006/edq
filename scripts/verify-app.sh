#!/bin/bash
# EDQ integration verification script (quick smoke test)
# Run after docker compose up.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ADMIN_USER="${EDQ_ADMIN_USER:-admin}"
COOKIE_FILE=$(mktemp)
PASS=0
FAIL=0
SKIP=0

read_root_env() {
  local key="$1"
  if [ ! -f "$REPO_ROOT/.env" ]; then
    return 0
  fi
  grep -E "^${key}=" "$REPO_ROOT/.env" | head -1 | cut -d= -f2- | tr -d '\r' || true
}

DEFAULT_PUBLIC_PORT="${EDQ_PUBLIC_PORT:-$(read_root_env EDQ_PUBLIC_PORT)}"
DEFAULT_PUBLIC_PORT="${DEFAULT_PUBLIC_PORT:-3000}"
DEFAULT_PUBLIC_URL="${EDQ_PUBLIC_URL:-$(read_root_env EDQ_PUBLIC_URL)}"
DEFAULT_PUBLIC_URL="${DEFAULT_PUBLIC_URL:-http://localhost:${DEFAULT_PUBLIC_PORT}}"
BASE_URL="${EDQ_URL:-$DEFAULT_PUBLIC_URL}"
API_URL="$BASE_URL/api"

resolve_admin_password() {
  if [ -n "${EDQ_ADMIN_PASS:-}" ]; then
    printf '%s\n' "$EDQ_ADMIN_PASS"
    return 0
  fi

  if [ -f "$REPO_ROOT/.env" ]; then
    grep -E '^INITIAL_ADMIN_PASSWORD=' "$REPO_ROOT/.env" | head -1 | cut -d= -f2- | tr -d '\r' || true
    return 0
  fi

  return 1
}

ADMIN_PASS="$(resolve_admin_password || true)"
if [ -z "$ADMIN_PASS" ] || [[ "$ADMIN_PASS" == CHANGE_ME* ]] || [[ "$ADMIN_PASS" == change-me* ]]; then
  echo "ERROR: Set EDQ_ADMIN_PASS or configure INITIAL_ADMIN_PASSWORD in $REPO_ROOT/.env" >&2
  exit 1
fi
export EDQ_LOGIN_USER="$ADMIN_USER"
export EDQ_LOGIN_PASS="$ADMIN_PASS"

cleanup() {
  rm -f "$COOKIE_FILE"
}
trap cleanup EXIT

check() {
  local label="$1"
  shift
  printf "  %-35s " "$label"
  if result=$("$@" 2>/dev/null); then
    echo -e "\033[32mOK\033[0m  $result"
    PASS=$((PASS + 1))
  else
    echo -e "\033[31mFAIL\033[0m"
    FAIL=$((FAIL + 1))
  fi
}

skip() {
  local label="$1"
  local reason="$2"
  printf "  %-35s \033[33mSKIP\033[0m  %s\n" "$label" "$reason"
  SKIP=$((SKIP + 1))
}

echo ""
echo "====================================="
echo "  EDQ Integration Verification"
echo "====================================="
echo ""
echo "Target: $BASE_URL"
echo ""

echo "--- Backend Health ---"
check "API health" bash -c "curl -sf '$API_URL/health' | python3 -c \"import sys,json; d=json.load(sys.stdin); assert d['status']=='ok'; print(d['status'])\""

echo ""
echo "--- Authentication ---"
check "Login (admin)" bash -c "curl -sf -X POST '$API_URL/auth/login' \
  -H 'Content-Type: application/json' \
  -d \"\$(python3 -c 'import json, os; print(json.dumps({\"username\": os.environ[\"EDQ_LOGIN_USER\"], \"password\": os.environ[\"EDQ_LOGIN_PASS\"]}))')\" \
  -c '$COOKIE_FILE' | python3 -c \"import sys,json; d=json.load(sys.stdin); print('token received')\""

check "Get current user" bash -c "curl -sf '$API_URL/auth/me' -b '$COOKIE_FILE' | python3 -c \"import sys,json; d=json.load(sys.stdin); print(d.get('username',''))\""

echo ""
echo "--- Core Resources ---"
check "List devices" bash -c "curl -sf '$API_URL/devices/' -b '$COOKIE_FILE' | python3 -c \"import sys,json; d=json.load(sys.stdin); print(f'{len(d) if isinstance(d,list) else d.get(\\\"total\\\",0)} devices')\""

check "List test runs" bash -c "curl -sf '$API_URL/test-runs/' -b '$COOKIE_FILE' | python3 -c \"import sys,json; d=json.load(sys.stdin); print(f'{len(d) if isinstance(d,list) else 0} runs')\""

check "List templates" bash -c "curl -sf '$API_URL/test-templates/' -b '$COOKIE_FILE' | python3 -c \"import sys,json; d=json.load(sys.stdin); print(f'{len(d) if isinstance(d,list) else 0} templates')\""

check "List whitelists" bash -c "curl -sf '$API_URL/whitelists/' -b '$COOKIE_FILE' | python3 -c \"import sys,json; d=json.load(sys.stdin); print(f'{len(d) if isinstance(d,list) else 0} whitelists')\""

echo ""
echo "--- Tools Sidecar ---"
check "Tool versions" bash -c "curl -sf '$API_URL/health/tools/versions' -b '$COOKIE_FILE' | python3 -c \"import sys,json; d=json.load(sys.stdin); tools=d.get('tools',d.get('versions',{})); print(f'{len(tools)} tools')\""

echo ""
echo "--- Frontend ---"
check "Frontend serves HTML" bash -c "curl -sf '$BASE_URL/' | grep -qi 'edq\|device qualifier' && echo 'HTML OK'"

check "Static assets (JS)" bash -c "curl -sf '$BASE_URL/' | python3 -c \"import re, sys; html = sys.stdin.read(); assert re.search(r'src=\\\"[^\\\"]+\\\\.js\\\"', html); print('JS bundle linked')\""

echo ""
echo "--- WebSocket ---"
check "WebSocket upgrade" bash -c "
python3 - <<'PY'
import json
import os
import sys
import urllib.request

import websockets.sync.client

base_url = os.environ.get('EDQ_URL') or '${BASE_URL}'
api_url = f\"{base_url.rstrip('/')}/api\"
admin_user = os.environ['EDQ_LOGIN_USER']
admin_pass = os.environ['EDQ_LOGIN_PASS']

login_request = urllib.request.Request(
    f\"{api_url}/auth/login\",
    data=json.dumps({\"username\": admin_user, \"password\": admin_pass}).encode(),
    headers={\"Content-Type\": \"application/json\"},
    method=\"POST\",
)
with urllib.request.urlopen(login_request, timeout=10) as resp:
    payload = json.loads(resp.read().decode())
    cookies = resp.headers.get_all('Set-Cookie') or []
    if not payload.get('csrf_token'):
        raise SystemExit('missing csrf token')

session_cookie = None
for header in cookies:
    for part in header.split(';'):
        part = part.strip()
        if part.startswith('edq_session='):
            session_cookie = part
            break
    if session_cookie:
        break
if not session_cookie:
    raise SystemExit('missing edq_session cookie')

with urllib.request.urlopen(f\"{api_url}/test-runs/\", timeout=10) as resp:
    runs = json.loads(resp.read().decode())
if not runs:
    raise SystemExit('no test runs available')
run_id = runs[0]['id']

ws_url = base_url.rstrip('/').replace('http://', 'ws://').replace('https://', 'wss://') + f'/api/ws/test-run/{run_id}'
with websockets.sync.client.connect(
    ws_url,
    additional_headers={
        'Origin': base_url.rstrip('/'),
        'Cookie': session_cookie,
    },
    open_timeout=10,
) as ws:
    print(f'connected to run {run_id}')
PY
"

echo ""
echo "====================================="
printf "  Results: \033[32m%d passed\033[0m, \033[31m%d failed\033[0m, \033[33m%d skipped\033[0m\n" "$PASS" "$FAIL" "$SKIP"
echo "====================================="
echo ""

if [ "$FAIL" -gt 0 ]; then
  exit 1
fi
