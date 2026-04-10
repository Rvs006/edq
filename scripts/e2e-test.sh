#!/bin/bash
# ============================================================================
# EDQ API Regression Script
# ============================================================================
# Authenticated API regression checks for a live EDQ deployment.
# Uses curl + python3 only.
#
# Usage: ./scripts/e2e-test.sh [BASE_URL]
# Default: http://localhost:3000
#
# For a quick smoke test, use ./scripts/verify-app.sh instead.
# ============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BASE_URL="${1:-http://localhost:3000}"
API="$BASE_URL/api"
ADMIN_USER="${EDQ_ADMIN_USER:-admin}"
COOKIE=$(mktemp)
CSRF_TOKEN=""
LAST_RESULT=""
TOTAL=0 PASS=0 FAIL=0 SKIP=0

GREEN='\033[32m' RED='\033[31m' YELLOW='\033[33m' CYAN='\033[36m' BOLD='\033[1m' NC='\033[0m'

CREATED_DEVICE_IDS=()
CREATED_RUN_IDS=()
CREATED_WHITELIST_IDS=()
RUN_SUFFIX=$(( ( $(date +%s) + $$ ) % 1000 ))
CRUD_DEVICE_IP="10.99.99.$((100 + (RUN_SUFFIX % 100)))"
RUN_DEVICE_IP_VALUE="10.99.98.$((100 + (RUN_SUFFIX % 100)))"
WHITELIST_NAME="E2E Test Whitelist ${RUN_SUFFIX}"
PROFILE_NAME="E2E Test Profile ${RUN_SUFFIX}"
PLAN_NAME="E2E Test Plan ${RUN_SUFFIX}"

resolve_admin_password() {
  if [ -n "${EDQ_ADMIN_PASS:-}" ]; then
    printf '%s\n' "$EDQ_ADMIN_PASS"
    return 0
  fi

  if [ -f "$REPO_ROOT/.env" ]; then
    grep -E '^INITIAL_ADMIN_PASSWORD=' "$REPO_ROOT/.env" | head -1 | cut -d= -f2- | tr -d '\r'
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
  rm -f "$COOKIE"
}
trap cleanup EXIT

json_get() {
  python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
except:
    sys.exit(1)
keys = '$1'.split('.')
for k in keys:
    if isinstance(d, list):
        d = d[int(k)] if k.isdigit() else None
        if d is None: break
    elif isinstance(d, dict):
        d = d.get(k)
        if d is None: break
    else:
        d = None
        break
if d is None:
    sys.exit(1)
print(d)
"
}

json_len() {
  python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
except:
    print(0); sys.exit(0)
if isinstance(d, list):
    print(len(d))
elif isinstance(d, dict) and 'items' in d:
    print(len(d['items']))
elif isinstance(d, dict) and 'total' in d:
    print(d['total'])
else:
    print(0)
"
}

json_find_id() {
  python3 -c "
import sys, json
field = '$1'
value = '$2'
try:
    d = json.load(sys.stdin)
except:
    sys.exit(1)
items = d if isinstance(d, list) else d.get('items', [])
for item in items:
    if str(item.get(field, '')) == value:
        print(item['id'])
        sys.exit(0)
sys.exit(1)
"
}

test_case() {
  local name="$1"
  shift
  TOTAL=$((TOTAL + 1))
  printf "  %-52s " "$name"
  if [ "${1:-}" = "bash" ] && [ "${2:-}" = "-c" ]; then
    shift 2
    if result=$(eval "$1" 2>/dev/null); then
      LAST_RESULT="$result"
      printf "${GREEN}PASS${NC}  %s\n" "$result"
      PASS=$((PASS + 1))
      return 0
    fi
  else
    if result=$("$@" 2>/dev/null); then
      LAST_RESULT="$result"
      printf "${GREEN}PASS${NC}  %s\n" "$result"
      PASS=$((PASS + 1))
      return 0
    fi
  fi
  printf "${RED}FAIL${NC}\n"
  FAIL=$((FAIL + 1))
  return 1
}

skip_case() {
  local name="$1" reason="$2"
  TOTAL=$((TOTAL + 1))
  SKIP=$((SKIP + 1))
  printf "  %-52s ${YELLOW}SKIP${NC}  %s\n" "$name" "$reason"
}

section() {
  echo ""
  printf "${CYAN}${BOLD}--- %s ---${NC}\n" "$1"
}

api_get() {
  curl -sf -b "$COOKIE" -c "$COOKIE" "$API$1"
}

api_post() {
  local args=(-sf -b "$COOKIE" -c "$COOKIE" -X POST -H "Content-Type: application/json")
  if [ -n "${CSRF_TOKEN:-}" ]; then
    args+=(-H "X-CSRF-Token: $CSRF_TOKEN")
  fi
  curl "${args[@]}" -d "$2" "$API$1"
}

api_patch() {
  local args=(-sf -b "$COOKIE" -c "$COOKIE" -X PATCH -H "Content-Type: application/json")
  if [ -n "${CSRF_TOKEN:-}" ]; then
    args+=(-H "X-CSRF-Token: $CSRF_TOKEN")
  fi
  curl "${args[@]}" -d "$2" "$API$1"
}

api_put() {
  local args=(-sf -b "$COOKIE" -c "$COOKIE" -X PUT -H "Content-Type: application/json")
  if [ -n "${CSRF_TOKEN:-}" ]; then
    args+=(-H "X-CSRF-Token: $CSRF_TOKEN")
  fi
  curl "${args[@]}" -d "$2" "$API$1"
}

api_delete() {
  local args=(-sf -b "$COOKIE" -c "$COOKIE" -X DELETE)
  if [ -n "${CSRF_TOKEN:-}" ]; then
    args+=(-H "X-CSRF-Token: $CSRF_TOKEN")
  fi
  curl "${args[@]}" -o /dev/null -w "%{http_code}" "$API$1"
}

api_status() {
  curl -s -b "$COOKIE" -c "$COOKIE" -o /dev/null -w "%{http_code}" "$@" "$API$1"
}

echo ""
echo "======================================================"
echo "  EDQ API Regression Script"
echo "======================================================"
printf "  Target: %s\n" "$BASE_URL"
printf "  Date:   %s\n" "$(date '+%Y-%m-%d %H:%M:%S')"

section "1. Infrastructure Health"

test_case "1.1 Backend health endpoint" bash -c "
  api_get '/health' | json_get 'status'
" || true

test_case "1.2 Health payload matches current contract" bash -c "
  resp=\$(api_get '/health')
  echo \"\$resp\" | python3 -c \"
import sys, json
d = json.load(sys.stdin)
if d.get('status') in {'ok', 'degraded'} and 'database' in d:
    print('status=' + d['status'])
else:
    sys.exit(1)
\"
" || true

test_case "1.3 Health endpoint returns JSON" bash -c "
  api_get '/health' | python3 -c \"
import sys, json
d = json.load(sys.stdin)
print(type(d).__name__)
\"
" || true

test_case "1.4 Tool versions requires authentication" bash -c "
  status=\$(curl -s -o /dev/null -w '%{http_code}' '$API/health/tools/versions')
  if [ \"\$status\" = '401' ]; then
    echo 'HTTP 401'
  else
    exit 1
  fi
" || true

section "2. Authentication"

test_case "2.1 Login as admin" bash -c "
  payload=\$(python3 -c 'import json, os; print(json.dumps({\"username\": os.environ[\"EDQ_LOGIN_USER\"], \"password\": os.environ[\"EDQ_LOGIN_PASS\"]}))')
  resp=\$(curl -sf -X POST '$API/auth/login' \
    -H 'Content-Type: application/json' \
    -d \"\$payload\" \
    -b '$COOKIE' -c '$COOKIE')
  echo \"\$resp\" | python3 -c 'import sys,json; print(json.load(sys.stdin)[\"csrf_token\"])' > /tmp/edq_e2e_csrf
  echo 'logged in'
" && CSRF_TOKEN=$(cat /tmp/edq_e2e_csrf 2>/dev/null || echo "") || true

test_case "2.2 Current user uses username auth model" bash -c "
  api_get '/auth/me' | python3 -c \"
import sys, json
d = json.load(sys.stdin)
assert d.get('username') == '$ADMIN_USER'
print(d['username'])
\"
" || true

rm -f /tmp/edq_e2e_csrf

echo ""
echo "======================================================"
printf "  Results: ${GREEN}%d passed${NC}, ${RED}%d failed${NC}, ${YELLOW}%d skipped${NC}\n" "$PASS" "$FAIL" "$SKIP"
echo "======================================================"

if [ "$FAIL" -gt 0 ]; then
  exit 1
fi
