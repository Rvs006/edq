param()

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

function Write-Status([string]$Label, [bool]$Ok, [string]$Detail) {
    $status = if ($Ok) { "OK" } else { "FAIL" }
    Write-Host ("{0,-28} {1,-5} {2}" -f $Label, $status, $Detail)
}

Push-Location $repoRoot
try {
    $shieldMyRepo = Get-Command "shieldmyrepo" -ErrorAction SilentlyContinue
    Write-Status "shieldmyrepo installed" ($null -ne $shieldMyRepo) $(if ($null -ne $shieldMyRepo) { $shieldMyRepo.Source } else { "not found on PATH" })

    $taskOutput = schtasks /Query /TN "ShieldMyRepo Auto Update Daily" /FO LIST 2>$null
    $taskOk = $LASTEXITCODE -eq 0
    $taskDetail = if ($taskOk) { "scheduled task present" } else { "scheduled task missing" }
    Write-Status "auto-update task" $taskOk $taskDetail

    $reportJson = Join-Path $repoRoot "reports/shieldmyrepo-report.json"
    $reportMd = Join-Path $repoRoot "reports/shieldmyrepo-report.md"
    $badgeSvg = Join-Path $repoRoot "reports/shieldmyrepo-badge.svg"

    $reportJsonExists = Test-Path $reportJson
    $reportMdExists = Test-Path $reportMd
    $badgeExists = Test-Path $badgeSvg

    Write-Status "report json" $reportJsonExists ($(if ($reportJsonExists) { $reportJson } else { "missing" }))
    Write-Status "report markdown" $reportMdExists ($(if ($reportMdExists) { $reportMd } else { "missing" }))
    Write-Status "report badge" $badgeExists ($(if ($badgeExists) { $badgeSvg } else { "missing" }))

    if ($reportJsonExists) {
        $report = Get-Content $reportJson -Raw | ConvertFrom-Json
        $grade = [string]$report.grade
        $score = [string]$report.score
        Write-Status "current grade" $true "$grade ($score/100)"
    } else {
        Write-Status "current grade" $false "run a security scan first"
    }
}
finally {
    Pop-Location
}
