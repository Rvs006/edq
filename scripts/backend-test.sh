#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BACKEND_PATH="$REPO_ROOT/server/backend"

echo "=== EDQ Backend Test Suite ==="
echo "Repo root: $REPO_ROOT"

docker compose build backend
docker compose run --rm --no-deps -T \
  -v "$BACKEND_PATH:/app" \
  backend \
  sh -lc "python -m pip install --quiet pytest pytest-asyncio httpx && python -m pytest tests/ -v --tb=short"
