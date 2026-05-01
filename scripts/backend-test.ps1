param()

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

Write-Host "=== EDQ Backend Test Suite ==="
Write-Host ("Repo root: {0}" -f $repoRoot)

docker compose build backend
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

$mountArg = "{0}:/workspace" -f $repoRoot
docker compose run --rm --no-deps -T --entrypoint sh -v $mountArg backend -lc "cd /workspace/server/backend && mkdir -p /tmp/edq-test-uploads /tmp/edq-test-reports && python -m pip install --quiet -r requirements-dev.txt && UPLOAD_DIR=/tmp/edq-test-uploads REPORT_DIR=/tmp/edq-test-reports python -m pytest tests/ -v --tb=short"
exit $LASTEXITCODE
