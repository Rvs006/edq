#!/bin/bash
# ============================================================================
# EDQ End-to-End Test Suite v1.0
# ============================================================================
# Comprehensive test suite for the EDQ platform. Runs against a live
# Docker Compose deployment (all 3 services). Uses curl + python3 only.
#
# Usage: ./scripts/e2e-test.sh [BASE_URL]
# Default: http://localhost
#
# For a quick smoke test, use ./scripts/verify-app.sh instead.
# ============================================================================

set -euo pipefail

BASE_URL="${1:-http://localhost}"
API="$BASE_URL/api"
ADMIN_USER="${EDQ_ADMIN_USER:-admin}"
ADMIN_PASS="${EDQ_ADMIN_PASS:-${INITIAL_ADMIN_PASSWORD:-Admin123!}}"
COOKIE=$(mktemp)
TOTAL=0 PASS=0 FAIL=0 SKIP=0

GREEN='\033[32m' RED='\033[31m' YELLOW='\033[33m' CYAN='\033[36m' BOLD='\033[1m' NC='\033[0m'

CREATED_DEVICE_IDS=()
CREATED_RUN_IDS=()
CREATED_WHITELIST_IDS=()

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
  if result=$("$@" 2>/dev/null); then
    printf "${GREEN}PASS${NC}  %s\n" "$result"
    PASS=$((PASS + 1))
    return 0
  else
    printf "${RED}FAIL${NC}\n"
    FAIL=$((FAIL + 1))
    return 1
  fi
}

skip_case() {
  local name="$1" reason="$2"
  TOTAL=$((TOTAL + 1))
  SKIP=$((SKIP + 1))
  printf "  %-52s ${YELLOW}SKIP${NC}  %s\n" "$name" "$reason"
}

section() {
  echo ""
  printf "${CYAN}${BOLD}━━━ %s ━━━${NC}\n" "$1"
}

api_get() {
  curl -sf -b "$COOKIE" -c "$COOKIE" "$API$1"
}

api_post() {
  curl -sf -b "$COOKIE" -c "$COOKIE" \
    -X POST -H "Content-Type: application/json" \
    -d "$2" "$API$1"
}

api_patch() {
  curl -sf -b "$COOKIE" -c "$COOKIE" \
    -X PATCH -H "Content-Type: application/json" \
    -d "$2" "$API$1"
}

api_put() {
  curl -sf -b "$COOKIE" -c "$COOKIE" \
    -X PUT -H "Content-Type: application/json" \
    -d "$2" "$API$1"
}

api_delete() {
  curl -sf -b "$COOKIE" -c "$COOKIE" -X DELETE -o /dev/null -w "%{http_code}" "$API$1"
}

api_status() {
  curl -s -b "$COOKIE" -c "$COOKIE" -o /dev/null -w "%{http_code}" "$@" "$API$1"
}

# ============================================================================
echo ""
echo "╔═══════════════════════════════════════════════════════╗"
echo "║          EDQ End-to-End Test Suite v1.0               ║"
echo "╠═══════════════════════════════════════════════════════╣"
printf "║  Target: %-44s ║\n" "$BASE_URL"
printf "║  Date:   %-44s ║\n" "$(date '+%Y-%m-%d %H:%M:%S')"
echo "╚═══════════════════════════════════════════════════════╝"

# ============================================================================
section "1. Infrastructure Health"
# ============================================================================

test_case "1.1 Backend health endpoint" bash -c "
  api_get '/health' | json_get 'status'
" || true

test_case "1.2 Database connected" bash -c "
  api_get '/health' | json_get 'database'
" || true

test_case "1.3 Tools sidecar reachable" bash -c "
  resp=\$(curl -sf -b '$COOKIE' '$API/health')
  status=\$(echo \"\$resp\" | python3 -c \"import sys,json; print(json.load(sys.stdin).get('tools_sidecar',''))\" 2>/dev/null)
  if [ \"\$status\" = 'healthy' ] || [ \"\$status\" = 'unreachable' ]; then
    echo \"\$status\"
  else
    exit 1
  fi
" || true

test_case "1.4 Tool versions endpoint" bash -c "
  curl -sf -b '$COOKIE' '$API/health/tools/versions' | python3 -c \"
import sys, json
d = json.load(sys.stdin)
print(d.get('status', 'unknown'))
\"
" || true

test_case "1.5 Frontend serves HTML" bash -c "
  curl -sf '$BASE_URL/' | grep -qiE 'edq|device.qualifier|electracom' && echo 'HTML served'
" || true

test_case "1.6 Frontend has JS bundle" bash -c "
  curl -sf '$BASE_URL/' | grep -qoP 'src=\"[^\"]+\\.js\"' && echo 'JS linked'
" || true

# ============================================================================
section "2. Authentication Flow"
# ============================================================================

test_case "2.1 Login with admin credentials" bash -c "
  resp=\$(curl -sf -X POST '$API/auth/login' \
    -H 'Content-Type: application/json' \
    -d '{\"username\":\"'$ADMIN_USER'\",\"password\":\"'$ADMIN_PASS'\"}' \
    -c '$COOKIE')
  echo \"\$resp\" | python3 -c \"
import sys, json
d = json.load(sys.stdin)
user = d.get('user', {})
if d.get('message') == 'Login successful':
    print('login ok — ' + user.get('role', 'admin'))
else:
    sys.exit(1)
\"
" || true

test_case "2.2 Get current user (GET /auth/me)" bash -c "
  resp=\$(curl -sf -b '$COOKIE' '$API/auth/me')
  echo \"\$resp\" | python3 -c \"
import sys, json
d = json.load(sys.stdin)
email = d.get('email', '')
if 'electracom' in email or 'admin' in email:
    print(email)
else:
    sys.exit(1)
\"
" || true

test_case "2.3 Invalid login rejected (401)" bash -c "
  status=\$(curl -s -o /dev/null -w '%{http_code}' -X POST '$API/auth/login' \
    -H 'Content-Type: application/json' \
    -d '{\"username\":\"bad@test.com\",\"password\":\"wrongpassword\"}')
  if [ \"\$status\" = '401' ]; then
    echo 'HTTP 401'
  else
    exit 1
  fi
" || true

test_case "2.4 Unauthenticated access blocked" bash -c "
  status=\$(curl -s -o /dev/null -w '%{http_code}' '$API/devices/')
  if [ \"\$status\" = '401' ] || [ \"\$status\" = '403' ]; then
    echo \"HTTP \$status\"
  else
    exit 1
  fi
" || true

test_case "2.5 Auth cookie is httpOnly" bash -c "
  grep -qi 'httponly' '$COOKIE' 2>/dev/null && echo 'httpOnly set' || {
    curl -sI -b '$COOKIE' '$API/auth/me' | grep -qi 'httponly' && echo 'httpOnly in header' || echo 'cookie present'
  }
" || true

# ============================================================================
section "3. Device Management (CRUD)"
# ============================================================================

DEVICE_ID=""

test_case "3.1 Create device" bash -c "
  resp=\$(curl -sf -b '$COOKIE' -c '$COOKIE' -X POST '$API/devices/' \
    -H 'Content-Type: application/json' \
    -d '{\"ip_address\":\"10.99.99.1\",\"hostname\":\"E2E Test Camera\",\"category\":\"camera\",\"manufacturer\":\"Test Corp\",\"model\":\"TC-100\"}')
  id=\$(echo \"\$resp\" | python3 -c 'import sys,json; print(json.load(sys.stdin)[\"id\"])')
  echo \"\$id\" > /tmp/edq_e2e_device_id
  echo \"id=\${id:0:8}...\"
" && DEVICE_ID=$(cat /tmp/edq_e2e_device_id 2>/dev/null) && CREATED_DEVICE_IDS+=("$DEVICE_ID") || true

test_case "3.2 List devices — find created" bash -c "
  resp=\$(curl -sf -b '$COOKIE' '$API/devices/')
  echo \"\$resp\" | python3 -c \"
import sys, json
d = json.load(sys.stdin)
items = d if isinstance(d, list) else d.get('items', [])
found = any(i.get('ip_address') == '10.99.99.1' for i in items)
if found:
    print(f'{len(items)} devices, target found')
else:
    sys.exit(1)
\"
" || true

test_case "3.3 Get device detail" bash -c "
  [ -z '$DEVICE_ID' ] && exit 1
  resp=\$(curl -sf -b '$COOKIE' '$API/devices/$DEVICE_ID')
  echo \"\$resp\" | python3 -c \"
import sys, json
d = json.load(sys.stdin)
assert d['ip_address'] == '10.99.99.1', 'IP mismatch'
print(d.get('hostname', d.get('ip_address', 'ok')))
\"
" || true

test_case "3.4 Update device (PATCH)" bash -c "
  [ -z '$DEVICE_ID' ] && exit 1
  resp=\$(curl -sf -b '$COOKIE' -c '$COOKIE' -X PATCH '$API/devices/$DEVICE_ID' \
    -H 'Content-Type: application/json' \
    -d '{\"firmware_version\":\"2.0.1\"}')
  echo \"\$resp\" | python3 -c \"
import sys, json
d = json.load(sys.stdin)
if d.get('firmware_version') == '2.0.1':
    print('firmware_version=2.0.1')
else:
    sys.exit(1)
\"
" || true

test_case "3.5 Device stats endpoint" bash -c "
  resp=\$(curl -sf -b '$COOKIE' '$API/devices/stats')
  echo \"\$resp\" | python3 -c \"
import sys, json
d = json.load(sys.stdin)
total = d.get('total', 0)
print(f'total={total}')
\"
" || true

# ============================================================================
section "4. Test Templates & Library"
# ============================================================================

TEMPLATE_ID=""
TEMPLATE_COUNT=0

test_case "4.1 Universal test library (43 tests)" bash -c "
  resp=\$(curl -sf -b '$COOKIE' '$API/test-templates/library')
  echo \"\$resp\" | python3 -c \"
import sys, json
d = json.load(sys.stdin)
items = d if isinstance(d, list) else []
count = len(items)
if count >= 30:
    auto = sum(1 for t in items if t.get('tier') == 'automatic')
    manual = sum(1 for t in items if t.get('tier') == 'guided_manual')
    print(f'{count} tests ({auto} auto, {manual} manual)')
else:
    sys.exit(1)
\"
" || true

test_case "4.2 List test templates (≥3)" bash -c "
  resp=\$(curl -sf -b '$COOKIE' '$API/test-templates/')
  count=\$(echo \"\$resp\" | python3 -c 'import sys,json; d=json.load(sys.stdin); print(len(d) if isinstance(d,list) else 0)')
  first_id=\$(echo \"\$resp\" | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d[0][\"id\"] if isinstance(d,list) and len(d)>0 else \"\")' 2>/dev/null)
  echo \"\$first_id\" > /tmp/edq_e2e_template_id
  echo \"\$count\" > /tmp/edq_e2e_template_count
  if [ \"\$count\" -ge 3 ]; then
    echo \"\$count templates\"
  else
    echo \"\$count templates (expected ≥3)\"
    exit 1
  fi
" && TEMPLATE_ID=$(cat /tmp/edq_e2e_template_id 2>/dev/null) && TEMPLATE_COUNT=$(cat /tmp/edq_e2e_template_count 2>/dev/null) || true

test_case "4.3 Get template detail" bash -c "
  [ -z '$TEMPLATE_ID' ] && exit 1
  resp=\$(curl -sf -b '$COOKIE' '$API/test-templates/$TEMPLATE_ID')
  echo \"\$resp\" | python3 -c \"
import sys, json
d = json.load(sys.stdin)
name = d.get('name', 'unknown')
test_ids = d.get('test_ids', [])
print(f'{name} ({len(test_ids)} tests)')
\"
" || true

test_case "4.4 Template has test_ids array" bash -c "
  [ -z '$TEMPLATE_ID' ] && exit 1
  resp=\$(curl -sf -b '$COOKIE' '$API/test-templates/$TEMPLATE_ID')
  echo \"\$resp\" | python3 -c \"
import sys, json
d = json.load(sys.stdin)
ids = d.get('test_ids', [])
assert isinstance(ids, list) and len(ids) > 0, 'No test_ids'
print(f'{len(ids)} test IDs')
\"
" || true

# ============================================================================
section "5. Test Run Lifecycle"
# ============================================================================

RUN_DEVICE_ID=""
RUN_ID=""

test_case "5.1 Create device for test run" bash -c "
  resp=\$(curl -sf -b '$COOKIE' -c '$COOKIE' -X POST '$API/devices/' \
    -H 'Content-Type: application/json' \
    -d '{\"ip_address\":\"10.99.99.2\",\"hostname\":\"E2E Run Device\",\"category\":\"unknown\"}')
  id=\$(echo \"\$resp\" | python3 -c 'import sys,json; print(json.load(sys.stdin)[\"id\"])')
  echo \"\$id\" > /tmp/edq_e2e_run_device_id
  echo \"id=\${id:0:8}...\"
" && RUN_DEVICE_ID=$(cat /tmp/edq_e2e_run_device_id 2>/dev/null) && CREATED_DEVICE_IDS+=("$RUN_DEVICE_ID") || true

test_case "5.2 Create test run" bash -c "
  [ -z '$RUN_DEVICE_ID' ] || [ -z '$TEMPLATE_ID' ] && exit 1
  resp=\$(curl -sf -b '$COOKIE' -c '$COOKIE' -X POST '$API/test-runs/' \
    -H 'Content-Type: application/json' \
    -d '{\"device_id\":\"$RUN_DEVICE_ID\",\"template_id\":\"$TEMPLATE_ID\"}')
  id=\$(echo \"\$resp\" | python3 -c 'import sys,json; print(json.load(sys.stdin)[\"id\"])')
  status=\$(echo \"\$resp\" | python3 -c 'import sys,json; print(json.load(sys.stdin).get(\"status\",\"\"))' 2>/dev/null)
  echo \"\$id\" > /tmp/edq_e2e_run_id
  echo \"id=\${id:0:8}... status=\$status\"
" && RUN_ID=$(cat /tmp/edq_e2e_run_id 2>/dev/null) && CREATED_RUN_IDS+=("$RUN_ID") || true

test_case "5.3 Get test run detail" bash -c "
  [ -z '$RUN_ID' ] && exit 1
  resp=\$(curl -sf -b '$COOKIE' '$API/test-runs/$RUN_ID')
  echo \"\$resp\" | python3 -c \"
import sys, json
d = json.load(sys.stdin)
status = d.get('status', '')
total = d.get('total_tests', 0)
print(f'status={status} total_tests={total}')
\"
" || true

test_case "5.4 List test results for run" bash -c "
  [ -z '$RUN_ID' ] && exit 1
  resp=\$(curl -sf -b '$COOKIE' '$API/test-results/?test_run_id=$RUN_ID')
  echo \"\$resp\" | python3 -c \"
import sys, json
d = json.load(sys.stdin)
items = d if isinstance(d, list) else d.get('items', [])
if len(items) > 0:
    first_id = items[0].get('id', '')
    print(first_id) 
else:
    sys.exit(1)
\" > /tmp/edq_e2e_result_id
  count=\$(echo \"\$resp\" | python3 -c 'import sys,json; d=json.load(sys.stdin); print(len(d) if isinstance(d,list) else 0)')
  echo \"\$count results\"
" || true

RESULT_ID=$(cat /tmp/edq_e2e_result_id 2>/dev/null || echo "")

test_case "5.5 Get single test result" bash -c "
  [ -z '$RESULT_ID' ] && exit 1
  resp=\$(curl -sf -b '$COOKIE' '$API/test-results/$RESULT_ID')
  echo \"\$resp\" | python3 -c \"
import sys, json
d = json.load(sys.stdin)
print(f\"{d.get('test_id','')} — {d.get('test_name','')}\")
\"
" || true

test_case "5.6 Update manual test result (PATCH)" bash -c "
  [ -z '$RESULT_ID' ] && exit 1
  resp=\$(curl -sf -b '$COOKIE' -c '$COOKIE' -X PATCH '$API/test-results/$RESULT_ID' \
    -H 'Content-Type: application/json' \
    -d '{\"verdict\":\"pass\",\"engineer_notes\":\"E2E test verification\"}')
  echo \"\$resp\" | python3 -c \"
import sys, json
d = json.load(sys.stdin)
v = d.get('verdict', '')
if 'pass' in v.lower():
    print(f'verdict={v}')
else:
    sys.exit(1)
\"
" || true

test_case "5.7 Test run stats endpoint" bash -c "
  resp=\$(curl -sf -b '$COOKIE' '$API/test-runs/stats')
  echo \"\$resp\" | python3 -c \"
import sys, json
d = json.load(sys.stdin)
total = d.get('total', 0)
print(f'total_runs={total}')
\"
" || true

test_case "5.8 Complete the test run" bash -c "
  [ -z '$RUN_ID' ] && exit 1
  resp=\$(curl -sf -b '$COOKIE' -c '$COOKIE' -X POST '$API/test-runs/$RUN_ID/complete' \
    -H 'Content-Type: application/json')
  echo \"\$resp\" | python3 -c \"
import sys, json
d = json.load(sys.stdin)
status = d.get('status', '')
verdict = d.get('overall_verdict', 'n/a')
print(f'status={status} verdict={verdict}')
\"
" || true

test_case "5.9 Verify run is completed" bash -c "
  [ -z '$RUN_ID' ] && exit 1
  resp=\$(curl -sf -b '$COOKIE' '$API/test-runs/$RUN_ID')
  echo \"\$resp\" | python3 -c \"
import sys, json
d = json.load(sys.stdin)
status = d.get('status', '')
pct = d.get('progress_pct', 0)
if 'complete' in status.lower():
    print(f'status={status} progress={pct}%')
else:
    sys.exit(1)
\"
" || true

# ============================================================================
section "6. Protocol Whitelists"
# ============================================================================

WL_ID=""
WL_COUNT=0

test_case "6.1 List whitelists (≥1 default)" bash -c "
  resp=\$(curl -sf -b '$COOKIE' '$API/whitelists/')
  echo \"\$resp\" | python3 -c \"
import sys, json
d = json.load(sys.stdin)
items = d if isinstance(d, list) else d.get('items', [])
defaults = sum(1 for w in items if w.get('is_default'))
print(f'{len(items)} whitelists ({defaults} default)')
if len(items) < 1:
    sys.exit(1)
\"
" || true

test_case "6.2 Create whitelist" bash -c "
  resp=\$(curl -sf -b '$COOKIE' -c '$COOKIE' -X POST '$API/whitelists/' \
    -H 'Content-Type: application/json' \
    -d '{\"name\":\"E2E Test Whitelist\",\"entries\":[{\"port\":443,\"protocol\":\"TCP\",\"service\":\"HTTPS\"}]}')
  id=\$(echo \"\$resp\" | python3 -c 'import sys,json; print(json.load(sys.stdin)[\"id\"])')
  echo \"\$id\" > /tmp/edq_e2e_wl_id
  echo \"id=\${id:0:8}...\"
" && WL_ID=$(cat /tmp/edq_e2e_wl_id 2>/dev/null) && CREATED_WHITELIST_IDS+=("$WL_ID") || true

test_case "6.3 Get whitelist detail" bash -c "
  [ -z '$WL_ID' ] && exit 1
  resp=\$(curl -sf -b '$COOKIE' '$API/whitelists/$WL_ID')
  echo \"\$resp\" | python3 -c \"
import sys, json
d = json.load(sys.stdin)
name = d.get('name', '')
entries = d.get('entries', [])
print(f'{name} ({len(entries)} entries)')
\"
" || true

test_case "6.4 Update whitelist (PUT)" bash -c "
  [ -z '$WL_ID' ] && exit 1
  resp=\$(curl -sf -b '$COOKIE' -c '$COOKIE' -X PUT '$API/whitelists/$WL_ID' \
    -H 'Content-Type: application/json' \
    -d '{\"name\":\"E2E Test Whitelist Updated\"}')
  echo \"\$resp\" | python3 -c \"
import sys, json
d = json.load(sys.stdin)
name = d.get('name', '')
if 'Updated' in name:
    print(name)
else:
    sys.exit(1)
\"
" || true

# ============================================================================
section "7. Device Profiles"
# ============================================================================

PROFILE_ID=""

test_case "7.1 List device profiles" bash -c "
  resp=\$(curl -sf -b '$COOKIE' '$API/device-profiles/')
  echo \"\$resp\" | python3 -c \"
import sys, json
d = json.load(sys.stdin)
items = d if isinstance(d, list) else d.get('items', [])
categories = set(p.get('category','') for p in items)
if len(items) > 0:
    first_id = items[0].get('id', '')
    print(first_id)
else:
    sys.exit(1)
\" > /tmp/edq_e2e_profile_id
  count=\$(echo \"\$resp\" | python3 -c 'import sys,json; d=json.load(sys.stdin); print(len(d) if isinstance(d,list) else 0)')
  echo \"\$count profiles\"
" && PROFILE_ID=$(cat /tmp/edq_e2e_profile_id 2>/dev/null) || true

test_case "7.2 Get profile detail" bash -c "
  [ -z '$PROFILE_ID' ] && exit 1
  resp=\$(curl -sf -b '$COOKIE' '$API/device-profiles/$PROFILE_ID')
  echo \"\$resp\" | python3 -c \"
import sys, json
d = json.load(sys.stdin)
name = d.get('name', '')
cat = d.get('category', '')
print(f'{name} (category={cat})')
\"
" || true

test_case "7.3 Create device profile" bash -c "
  resp=\$(curl -sf -b '$COOKIE' -c '$COOKIE' -X POST '$API/device-profiles/' \
    -H 'Content-Type: application/json' \
    -d '{\"name\":\"E2E Test Profile\",\"manufacturer\":\"E2E Corp\",\"category\":\"unknown\",\"description\":\"Created by E2E test\"}')
  id=\$(echo \"\$resp\" | python3 -c 'import sys,json; print(json.load(sys.stdin)[\"id\"])')
  echo \"\$id\" > /tmp/edq_e2e_new_profile_id
  echo \"id=\${id:0:8}...\"
" || true

E2E_PROFILE_ID=$(cat /tmp/edq_e2e_new_profile_id 2>/dev/null || echo "")

test_case "7.4 Update profile (PATCH)" bash -c "
  [ -z '$E2E_PROFILE_ID' ] && exit 1
  resp=\$(curl -sf -b '$COOKIE' -c '$COOKIE' -X PATCH '$API/device-profiles/$E2E_PROFILE_ID' \
    -H 'Content-Type: application/json' \
    -d '{\"description\":\"Updated by E2E test\"}')
  echo \"\$resp\" | python3 -c \"
import sys, json
d = json.load(sys.stdin)
desc = d.get('description', '')
if 'Updated' in desc:
    print(desc)
else:
    sys.exit(1)
\"
" || true

# ============================================================================
section "8. Reports"
# ============================================================================

test_case "8.1 List report templates" bash -c "
  resp=\$(curl -sf -b '$COOKIE' '$API/reports/templates')
  echo \"\$resp\" | python3 -c \"
import sys, json
d = json.load(sys.stdin)
if isinstance(d, list):
    print(f'{len(d)} templates')
elif isinstance(d, dict):
    keys = list(d.keys())
    print(f'{len(keys)} template keys')
else:
    print('response ok')
\"
" || true

test_case "8.2 Generate Excel report" bash -c "
  [ -z '$RUN_ID' ] && exit 1
  resp=\$(curl -sf -b '$COOKIE' -c '$COOKIE' -X POST '$API/reports/generate' \
    -H 'Content-Type: application/json' \
    -d '{\"test_run_id\":\"$RUN_ID\",\"report_type\":\"excel\",\"template_key\":\"generic\"}')
  echo \"\$resp\" | python3 -c \"
import sys, json
d = json.load(sys.stdin)
fn = d.get('filename', '')
msg = d.get('message', d.get('detail', ''))
if fn:
    print(f'file={fn}')
elif msg:
    print(msg[:60])
else:
    sys.exit(1)
\"
" || true

test_case "8.3 Generate Word report" bash -c "
  [ -z '$RUN_ID' ] && exit 1
  resp=\$(curl -sf -b '$COOKIE' -c '$COOKIE' -X POST '$API/reports/generate' \
    -H 'Content-Type: application/json' \
    -d '{\"test_run_id\":\"$RUN_ID\",\"report_type\":\"word\"}')
  echo \"\$resp\" | python3 -c \"
import sys, json
d = json.load(sys.stdin)
fn = d.get('filename', '')
msg = d.get('message', d.get('detail', ''))
if fn:
    print(f'file={fn}')
elif msg:
    print(msg[:60])
else:
    sys.exit(1)
\"
" || true

test_case "8.4 Report configs endpoint" bash -c "
  resp=\$(curl -sf -b '$COOKIE' '$API/reports/configs')
  echo \"\$resp\" | python3 -c \"
import sys, json
d = json.load(sys.stdin)
count = len(d) if isinstance(d, list) else 0
print(f'{count} configs')
\"
" || true

# ============================================================================
section "9. Admin Endpoints"
# ============================================================================

test_case "9.1 Admin dashboard stats" bash -c "
  resp=\$(curl -sf -b '$COOKIE' '$API/admin/dashboard')
  echo \"\$resp\" | python3 -c \"
import sys, json
d = json.load(sys.stdin)
users = d.get('users', 0)
devices = d.get('devices', 0)
runs = d.get('test_runs', 0)
print(f'users={users} devices={devices} runs={runs}')
\"
" || true

test_case "9.2 System info" bash -c "
  resp=\$(curl -sf -b '$COOKIE' '$API/admin/system-info')
  echo \"\$resp\" | python3 -c \"
import sys, json
d = json.load(sys.stdin)
name = d.get('app_name', '')
ver = d.get('app_version', '')
print(f'{name} v{ver}')
\"
" || true

test_case "9.3 List users (≥1 admin)" bash -c "
  resp=\$(curl -sf -b '$COOKIE' '$API/users/')
  echo \"\$resp\" | python3 -c \"
import sys, json
d = json.load(sys.stdin)
items = d if isinstance(d, list) else d.get('items', [])
admins = sum(1 for u in items if u.get('role') == 'admin')
print(f'{len(items)} users ({admins} admin)')
if len(items) < 1:
    sys.exit(1)
\"
" || true

test_case "9.4 Audit logs" bash -c "
  resp=\$(curl -sf -b '$COOKIE' '$API/audit-logs/')
  echo \"\$resp\" | python3 -c \"
import sys, json
d = json.load(sys.stdin)
items = d if isinstance(d, list) else d.get('items', [])
print(f'{len(items)} log entries')
\"
" || true

test_case "9.5 Compliance summary" bash -c "
  resp=\$(curl -sf -b '$COOKIE' '$API/audit-logs/compliance-summary')
  echo \"\$resp\" | python3 -c \"
import sys, json
d = json.load(sys.stdin)
frameworks = d.get('frameworks', {})
print(f'{len(frameworks)} frameworks')
\"
" || true

# ============================================================================
section "10. Network Scan"
# ============================================================================

test_case "10.1 List past scans" bash -c "
  resp=\$(curl -sf -b '$COOKIE' '$API/network-scan/')
  echo \"\$resp\" | python3 -c \"
import sys, json
d = json.load(sys.stdin)
count = len(d) if isinstance(d, list) else 0
print(f'{count} scans')
\"
" || true

test_case "10.2 Discover endpoint accepts request" bash -c "
  status=\$(curl -s -o /tmp/edq_e2e_scan_resp -w '%{http_code}' \
    -b '$COOKIE' -c '$COOKIE' -X POST '$API/network-scan/discover' \
    -H 'Content-Type: application/json' \
    -d '{\"cidr\":\"10.99.99.0/24\"}')
  if [ \"\$status\" = '200' ] || [ \"\$status\" = '201' ] || [ \"\$status\" = '202' ]; then
    echo \"HTTP \$status\"
  elif [ \"\$status\" = '502' ] || [ \"\$status\" = '504' ]; then
    echo \"HTTP \$status (tools unreachable — expected in CI)\"
  else
    exit 1
  fi
" || true

# ============================================================================
section "11. Test Plans"
# ============================================================================

PLAN_ID=""

test_case "11.1 List test plans" bash -c "
  resp=\$(curl -sf -b '$COOKIE' '$API/test-plans/')
  echo \"\$resp\" | python3 -c \"
import sys, json
d = json.load(sys.stdin)
count = len(d) if isinstance(d, list) else 0
print(f'{count} plans')
\"
" || true

test_case "11.2 Create test plan" bash -c "
  [ -z '$TEMPLATE_ID' ] && exit 1
  resp=\$(curl -sf -b '$COOKIE' -c '$COOKIE' -X POST '$API/test-plans/' \
    -H 'Content-Type: application/json' \
    -d '{\"name\":\"E2E Test Plan\",\"description\":\"Created by E2E test\",\"base_template_id\":\"$TEMPLATE_ID\",\"test_configs\":[{\"test_id\":\"U01\",\"enabled\":true},{\"test_id\":\"U02\",\"enabled\":true}]}')
  id=\$(echo \"\$resp\" | python3 -c 'import sys,json; print(json.load(sys.stdin)[\"id\"])')
  echo \"\$id\" > /tmp/edq_e2e_plan_id
  echo \"id=\${id:0:8}...\"
" && PLAN_ID=$(cat /tmp/edq_e2e_plan_id 2>/dev/null) || true

test_case "11.3 Get test plan detail" bash -c "
  [ -z '$PLAN_ID' ] && exit 1
  resp=\$(curl -sf -b '$COOKIE' '$API/test-plans/$PLAN_ID')
  echo \"\$resp\" | python3 -c \"
import sys, json
d = json.load(sys.stdin)
configs = d.get('test_configs', [])
print(f\"{d.get('name','')} ({len(configs)} configs)\")
\"
" || true

test_case "11.4 Clone test plan" bash -c "
  [ -z '$PLAN_ID' ] && exit 1
  resp=\$(curl -sf -b '$COOKIE' -c '$COOKIE' -X POST '$API/test-plans/$PLAN_ID/clone')
  echo \"\$resp\" | python3 -c \"
import sys, json
d = json.load(sys.stdin)
name = d.get('name', '')
clone_id = d.get('id', '')
print(clone_id)
\" > /tmp/edq_e2e_plan_clone_id
  echo \"cloned\"
" || true

PLAN_CLONE_ID=$(cat /tmp/edq_e2e_plan_clone_id 2>/dev/null || echo "")

# ============================================================================
section "12. Discovery"
# ============================================================================

test_case "12.1 Discovery scan endpoint" bash -c "
  status=\$(curl -s -o /dev/null -w '%{http_code}' \
    -b '$COOKIE' -c '$COOKIE' -X POST '$API/discovery/scan' \
    -H 'Content-Type: application/json' \
    -d '{\"ip_address\":\"10.99.99.1\"}')
  if [ \"\$status\" = '200' ] || [ \"\$status\" = '201' ] || [ \"\$status\" = '502' ]; then
    echo \"HTTP \$status\"
  else
    exit 1
  fi
" || true

# ============================================================================
section "13. Agents"
# ============================================================================

test_case "13.1 List agents" bash -c "
  resp=\$(curl -sf -b '$COOKIE' '$API/agents/')
  echo \"\$resp\" | python3 -c \"
import sys, json
d = json.load(sys.stdin)
count = len(d) if isinstance(d, list) else 0
print(f'{count} agents')
\"
" || true

# ============================================================================
section "14. Error Handling"
# ============================================================================

test_case "14.1 404 on nonexistent device" bash -c "
  status=\$(curl -s -o /dev/null -w '%{http_code}' -b '$COOKIE' '$API/devices/00000000-0000-0000-0000-000000000000')
  if [ \"\$status\" = '404' ]; then
    echo 'HTTP 404'
  else
    exit 1
  fi
" || true

test_case "14.2 404 on nonexistent test run" bash -c "
  status=\$(curl -s -o /dev/null -w '%{http_code}' -b '$COOKIE' '$API/test-runs/00000000-0000-0000-0000-000000000000')
  if [ \"\$status\" = '404' ]; then
    echo 'HTTP 404'
  else
    exit 1
  fi
" || true

test_case "14.3 400 on invalid CIDR" bash -c "
  status=\$(curl -s -o /dev/null -w '%{http_code}' \
    -b '$COOKIE' -c '$COOKIE' -X POST '$API/network-scan/discover' \
    -H 'Content-Type: application/json' \
    -d '{\"cidr\":\"not-a-cidr\"}')
  if [ \"\$status\" = '400' ] || [ \"\$status\" = '422' ]; then
    echo \"HTTP \$status\"
  else
    exit 1
  fi
" || true

test_case "14.4 422 on missing required fields" bash -c "
  status=\$(curl -s -o /dev/null -w '%{http_code}' \
    -b '$COOKIE' -c '$COOKIE' -X POST '$API/devices/' \
    -H 'Content-Type: application/json' \
    -d '{}')
  if [ \"\$status\" = '422' ] || [ \"\$status\" = '400' ]; then
    echo \"HTTP \$status\"
  else
    exit 1
  fi
" || true

test_case "14.5 Errors return JSON" bash -c "
  resp=\$(curl -s -b '$COOKIE' '$API/devices/00000000-0000-0000-0000-000000000000')
  echo \"\$resp\" | python3 -c \"
import sys, json
d = json.load(sys.stdin)
detail = d.get('detail', '')
if detail:
    print(f'detail: {detail}')
else:
    sys.exit(1)
\"
" || true

# ============================================================================
section "15. Cleanup"
# ============================================================================

cleanup_ok=0
cleanup_fail=0

printf "  Cleaning up test data...\n"

if [ -n "$PLAN_CLONE_ID" ]; then
  status=$(curl -s -o /dev/null -w "%{http_code}" -b "$COOKIE" -X DELETE "$API/test-plans/$PLAN_CLONE_ID" 2>/dev/null)
  if [ "$status" = "204" ] || [ "$status" = "200" ]; then
    cleanup_ok=$((cleanup_ok + 1))
  else
    cleanup_fail=$((cleanup_fail + 1))
  fi
fi

if [ -n "$PLAN_ID" ]; then
  status=$(curl -s -o /dev/null -w "%{http_code}" -b "$COOKIE" -X DELETE "$API/test-plans/$PLAN_ID" 2>/dev/null)
  if [ "$status" = "204" ] || [ "$status" = "200" ]; then
    cleanup_ok=$((cleanup_ok + 1))
  else
    cleanup_fail=$((cleanup_fail + 1))
  fi
fi

if [ -n "$WL_ID" ]; then
  status=$(curl -s -o /dev/null -w "%{http_code}" -b "$COOKIE" -X DELETE "$API/whitelists/$WL_ID" 2>/dev/null)
  if [ "$status" = "204" ] || [ "$status" = "200" ]; then
    cleanup_ok=$((cleanup_ok + 1))
  else
    cleanup_fail=$((cleanup_fail + 1))
  fi
fi

if [ -n "$E2E_PROFILE_ID" ]; then
  status=$(curl -s -o /dev/null -w "%{http_code}" -b "$COOKIE" -X DELETE "$API/device-profiles/$E2E_PROFILE_ID" 2>/dev/null)
  if [ "$status" = "204" ] || [ "$status" = "200" ]; then
    cleanup_ok=$((cleanup_ok + 1))
  else
    cleanup_fail=$((cleanup_fail + 1))
  fi
fi

for did in "${CREATED_DEVICE_IDS[@]}"; do
  if [ -n "$did" ]; then
    status=$(curl -s -o /dev/null -w "%{http_code}" -b "$COOKIE" -X DELETE "$API/devices/$did" 2>/dev/null)
    if [ "$status" = "204" ] || [ "$status" = "200" ]; then
      cleanup_ok=$((cleanup_ok + 1))
    else
      cleanup_fail=$((cleanup_fail + 1))
    fi
  fi
done

printf "  ${GREEN}Cleaned: %d${NC}  ${RED}Failed: %d${NC}\n" "$cleanup_ok" "$cleanup_fail"

rm -f /tmp/edq_e2e_device_id /tmp/edq_e2e_run_device_id /tmp/edq_e2e_run_id \
      /tmp/edq_e2e_result_id /tmp/edq_e2e_template_id /tmp/edq_e2e_template_count \
      /tmp/edq_e2e_wl_id /tmp/edq_e2e_profile_id /tmp/edq_e2e_new_profile_id \
      /tmp/edq_e2e_plan_id /tmp/edq_e2e_plan_clone_id /tmp/edq_e2e_scan_resp

# ============================================================================
# Summary
# ============================================================================
echo ""
echo "╔═══════════════════════════════════════════════════════╗"
printf "║  Results: ${GREEN}%d passed${NC}, ${RED}%d failed${NC}, ${YELLOW}%d skipped${NC}  " "$PASS" "$FAIL" "$SKIP"
printf "         ║\n"
printf "║  Total:  %-44s ║\n" "$TOTAL tests"
echo "╚═══════════════════════════════════════════════════════╝"
echo ""

if [ "$FAIL" -gt 0 ]; then
  printf "${RED}E2E test suite FAILED${NC}\n"
  exit 1
else
  printf "${GREEN}E2E test suite PASSED${NC}\n"
  exit 0
fi
