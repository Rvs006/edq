param()

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$backendPath = (Resolve-Path (Join-Path $repoRoot "server\backend")).Path

Write-Host "=== EDQ Backend Test Suite ==="
Write-Host ("Repo root: {0}" -f $repoRoot)

docker compose build backend
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

$mountArg = "{0}:/app" -f $backendPath
docker compose run --rm --no-deps -T -v $mountArg backend sh -lc "python -m pip install --quiet pytest pytest-asyncio httpx && python -m pytest tests/ -v --tb=short"
exit $LASTEXITCODE
