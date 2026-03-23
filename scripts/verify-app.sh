#!/bin/bash
# EDQ Integration Verification Script
# Run after docker compose up

set -euo pipefail

BASE_URL="${EDQ_URL:-http://localhost:80}"
API_URL="$BASE_URL/api"
COOKIE_FILE=$(mktemp)
PASS=0
FAIL=0
SKIP=0

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
  -d '{\"username\":\"admin@electracom.co.uk\",\"password\":\"Admin123!\"}' \
  -c '$COOKIE_FILE' | python3 -c \"import sys,json; d=json.load(sys.stdin); print('token received')\""

check "Get current user" bash -c "curl -sf '$API_URL/auth/me' -b '$COOKIE_FILE' | python3 -c \"import sys,json; d=json.load(sys.stdin); print(d.get('email',''))\""

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

check "Static assets (JS)" bash -c "curl -sf '$BASE_URL/' | grep -oP 'src=\"[^\"]+\\.js\"' | head -1 && echo 'JS bundle linked'"

echo ""
echo "--- WebSocket ---"
skip "WebSocket upgrade" "Requires wscat for full test"

echo ""
echo "====================================="
printf "  Results: \033[32m%d passed\033[0m, \033[31m%d failed\033[0m, \033[33m%d skipped\033[0m\n" "$PASS" "$FAIL" "$SKIP"
echo "====================================="
echo ""

if [ "$FAIL" -gt 0 ]; then
  exit 1
fi
