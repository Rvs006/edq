param(
    [int]$Port = 8002,
    [switch]$Run,
    [switch]$InstallStartupTask,
    [switch]$UninstallStartupTask,
    [switch]$InstallDeps
)

$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$EnvPath = Join-Path $RepoRoot ".env"
$TaskName = "EDQ Host MAC Helper"
$StartupCommandPath = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Startup\EDQ Host MAC Helper.cmd"

function Get-DotEnvValue {
    param([string]$Name)

    if (-not (Test-Path $EnvPath)) {
        throw "Missing .env at $EnvPath"
    }

    $line = Get-Content $EnvPath | Where-Object { $_ -match "^$Name=" } | Select-Object -First 1
    if (-not $line) {
        return ""
    }
    return ($line -replace "^$Name=", "").Trim().Trim('"').Trim("'")
}

if ($UninstallStartupTask) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $StartupCommandPath -Force -ErrorAction SilentlyContinue
    Write-Host "Removed scheduled task: $TaskName"
    Write-Host "Removed Startup command: $StartupCommandPath"
    exit 0
}

$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    throw "Python is required on PATH to run the EDQ host MAC helper."
}

if ($InstallDeps) {
    & $python.Source -m pip install -r (Join-Path $RepoRoot "tools\requirements.txt")
}

if ($InstallStartupTask) {
    $scriptPath = $PSCommandPath
    $argument = "-NoProfile -ExecutionPolicy Bypass -File `"$scriptPath`" -Run -Port $Port"
    $action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $argument -WorkingDirectory $RepoRoot
    $trigger = New-ScheduledTaskTrigger -AtLogOn
    $settings = New-ScheduledTaskSettingsSet -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)

    try {
        Register-ScheduledTask `
            -TaskName $TaskName `
            -Action $action `
            -Trigger $trigger `
            -Settings $settings `
            -Description "Runs the EDQ host ARP helper so Docker can read local MAC addresses for U02." `
            -Force | Out-Null

        Write-Host "Installed scheduled task: $TaskName"
    } catch {
        $logDir = Join-Path $env:LOCALAPPDATA "EDQ"
        New-Item -ItemType Directory -Path $logDir -Force | Out-Null
        $logPath = Join-Path $logDir "host-mac-helper.log"
        $cmd = "@echo off`r`npowershell -NoProfile -ExecutionPolicy Bypass -File `"$scriptPath`" -Run -Port $Port >> `"$logPath`" 2>&1`r`n"
        Set-Content -Path $StartupCommandPath -Value $cmd -Encoding ASCII

        Write-Host "Scheduled task install failed: $($_.Exception.Message)"
        Write-Host "Installed per-user Startup command instead: $StartupCommandPath"
    }

    Write-Host "It will start at logon. To run it now, execute:"
    Write-Host "  powershell -ExecutionPolicy Bypass -File `"$scriptPath`" -Run -Port $Port"
    exit 0
}

$apiKey = Get-DotEnvValue "TOOLS_API_KEY"
if (-not $apiKey) {
    throw "TOOLS_API_KEY is missing in $EnvPath"
}

$env:TOOLS_API_KEY = $apiKey
$env:EDQ_SCANNER_PORT = "$Port"
$env:EDQ_SCANNER_HOST = "0.0.0.0"

Set-Location $RepoRoot
Write-Host "Starting EDQ host MAC helper on http://0.0.0.0:$Port"
Write-Host "Use HOST_ARP_HELPER_URL=http://host.docker.internal:$Port in Docker."
& $python.Source (Join-Path $RepoRoot "tools\server.py")
