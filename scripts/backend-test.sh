#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "=== EDQ Backend Test Suite ==="
echo "Repo root: $REPO_ROOT"

docker compose build backend
docker compose run --rm --no-deps -T \
  --entrypoint sh \
  -v "$REPO_ROOT:/workspace" \
  backend \
  -lc "cd /workspace/server/backend && mkdir -p /tmp/edq-test-uploads /tmp/edq-test-reports && python -m pip install --quiet -r requirements-dev.txt && UPLOAD_DIR=/tmp/edq-test-uploads REPORT_DIR=/tmp/edq-test-reports python -m pytest tests/ -v --tb=short"
