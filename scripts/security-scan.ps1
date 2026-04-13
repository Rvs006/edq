param(
    [ValidateSet("markdown", "json")]
    [string]$Format = "markdown"
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$shieldMyRepo = Get-Command "shieldmyrepo" -ErrorAction SilentlyContinue

if (-not $shieldMyRepo) {
    throw "shieldmyrepo was not found on PATH. Install ShieldMyRepo first."
}

Push-Location $repoRoot
try {
    $args = @("scan", ".", "--format", $Format)
    if ($Format -eq "markdown") {
        $args += "--badge"
    }
    & $shieldMyRepo.Source @args
}
finally {
    Pop-Location
}