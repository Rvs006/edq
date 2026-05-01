#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

status_line() {
  local label="$1"
  local ok="$2"
  local detail="$3"
  printf '%-28s %-5s %s\n' "$label" "$ok" "$detail"
}

find_shieldmyrepo() {
  if command -v shieldmyrepo >/dev/null 2>&1; then
    command -v shieldmyrepo
    return 0
  fi

  if command -v where.exe >/dev/null 2>&1 && command -v wslpath >/dev/null 2>&1; then
    local windows_bin
    windows_bin="$(where.exe shieldmyrepo 2>/dev/null || true)"
    windows_bin="${windows_bin%%$'\n'*}"
    windows_bin="${windows_bin//$'\r'/}"
    if [[ -n "$windows_bin" ]]; then
      wslpath -u "$windows_bin"
      return 0
    fi
  fi

  for candidate in /mnt/c/Users/*/AppData/Local/Programs/Python/*/Scripts/shieldmyrepo.exe /mnt/c/Users/*/.local/bin/shieldmyrepo; do
    if [[ -x "$candidate" ]]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done

  return 1
}

cd "$REPO_ROOT"

if SHIELDMYREPO_BIN="$(find_shieldmyrepo)"; then
  status_line "shieldmyrepo installed" "OK" "$SHIELDMYREPO_BIN"
else
  status_line "shieldmyrepo installed" "FAIL" "not found on PATH"
fi

if command -v schtasks.exe >/dev/null 2>&1 && schtasks.exe /Query /TN "ShieldMyRepo Auto Update Daily" >/dev/null 2>&1; then
  status_line "auto-update task" "OK" "scheduled task present"
else
  status_line "auto-update task" "FAIL" "scheduled task missing"
fi

REPORT_JSON="$REPO_ROOT/reports/shieldmyrepo-report.json"
REPORT_MD="$REPO_ROOT/reports/shieldmyrepo-report.md"
BADGE_SVG="$REPO_ROOT/reports/shieldmyrepo-badge.svg"

if [[ -f "$REPORT_JSON" ]]; then
  status_line "report json" "OK" "$REPORT_JSON"
else
  status_line "report json" "FAIL" "missing"
fi

if [[ -f "$REPORT_MD" ]]; then
  status_line "report markdown" "OK" "$REPORT_MD"
else
  status_line "report markdown" "FAIL" "missing"
fi

if [[ -f "$BADGE_SVG" ]]; then
  status_line "report badge" "OK" "$BADGE_SVG"
else
  status_line "report badge" "FAIL" "missing"
fi

if [[ -f "$REPORT_JSON" ]]; then
  GRADE_OUTPUT="$(
    REPORT_JSON_PATH="$REPORT_JSON" python3 - <<'PY'
import json
import os
from pathlib import Path

path = Path(os.environ["REPORT_JSON_PATH"])
data = json.loads(path.read_text(encoding="utf-8"))
print(f"{data.get('grade', '?')} ({data.get('score', '?')}/100)")
PY
  )"
  status_line "current grade" "OK" "$GRADE_OUTPUT"
else
  status_line "current grade" "FAIL" "run a security scan first"
fi