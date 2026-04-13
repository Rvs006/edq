#!/bin/bash
set -euo pipefail

FORMAT="${1:-markdown}"

if [[ "$FORMAT" != "markdown" && "$FORMAT" != "json" ]]; then
  echo "Usage: ./scripts/security-scan.sh [markdown|json]" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

SHIELDMYREPO_BIN="${SHIELDMYREPO_BIN:-}"

resolve_windows_home() {
  local win_home_raw=""
  if command -v wslvar >/dev/null 2>&1 && command -v wslpath >/dev/null 2>&1; then
    win_home_raw="$(wslvar USERPROFILE 2>/dev/null || true)"
    if [[ -n "$win_home_raw" ]]; then
      wslpath -u "$win_home_raw"
      return 0
    fi
  fi
  if command -v cmd.exe >/dev/null 2>&1 && command -v wslpath >/dev/null 2>&1; then
    win_home_raw="$(cmd.exe /c echo %USERPROFILE% 2>/dev/null)"
    win_home_raw="${win_home_raw//$'\r'/}"
    if [[ -n "$win_home_raw" ]]; then
      wslpath -u "$win_home_raw"
      return 0
    fi
  fi
  return 1
}

resolve_windows_shieldmyrepo_bin() {
  local windows_bin=""
  if command -v where.exe >/dev/null 2>&1 && command -v wslpath >/dev/null 2>&1; then
    windows_bin="$(where.exe shieldmyrepo 2>/dev/null || true)"
    windows_bin="${windows_bin%%$'\n'*}"
    windows_bin="${windows_bin//$'\r'/}"
    if [[ -n "$windows_bin" ]]; then
      wslpath -u "$windows_bin"
      return 0
    fi
  fi

  for candidate in /mnt/c/Users/*/AppData/Local/Programs/Python/*/Scripts/shieldmyrepo.exe; do
    if [[ -x "$candidate" ]]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done

  return 1
}

if [[ -z "$SHIELDMYREPO_BIN" ]]; then
  if command -v shieldmyrepo >/dev/null 2>&1; then
    SHIELDMYREPO_BIN="$(command -v shieldmyrepo)"
  else
    WINDOWS_HOME="$(resolve_windows_home || true)"
    if [[ -n "${WINDOWS_HOME:-}" && -x "$WINDOWS_HOME/.local/bin/shieldmyrepo" ]]; then
      SHIELDMYREPO_BIN="$WINDOWS_HOME/.local/bin/shieldmyrepo"
    else
      WINDOWS_SHIELDMYREPO_BIN="$(resolve_windows_shieldmyrepo_bin || true)"
      if [[ -n "${WINDOWS_SHIELDMYREPO_BIN:-}" && -x "$WINDOWS_SHIELDMYREPO_BIN" ]]; then
        SHIELDMYREPO_BIN="$WINDOWS_SHIELDMYREPO_BIN"
      fi
    fi

    if [[ -z "$SHIELDMYREPO_BIN" ]]; then
      for candidate in /mnt/c/Users/*/.local/bin/shieldmyrepo; do
        if [[ -x "$candidate" ]]; then
          SHIELDMYREPO_BIN="$candidate"
          break
        fi
      done
      if [[ -z "$SHIELDMYREPO_BIN" ]]; then
        echo "shieldmyrepo was not found on PATH. Install ShieldMyRepo first or set SHIELDMYREPO_BIN." >&2
        exit 1
      fi
    fi
  fi
fi

cd "$REPO_ROOT"

if [[ "$FORMAT" == "markdown" ]]; then
  "$SHIELDMYREPO_BIN" scan . --format markdown --badge
else
  "$SHIELDMYREPO_BIN" scan . --format json
fi