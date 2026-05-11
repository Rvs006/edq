param(
    [int]$HostScannerPort = 8002,
    [switch]$NoBuild
)

$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$HelperScript = Join-Path $RepoRoot "scripts\start-host-mac-helper.ps1"

function Test-HttpOk {
    param([string]$Url)

    try {
        $response = Invoke-WebRequest -Uri $Url -TimeoutSec 2 -UseBasicParsing
        return $response.StatusCode -ge 200 -and $response.StatusCode -lt 300
    } catch {
        return $false
    }
}

if (-not (Test-HttpOk "http://127.0.0.1:$HostScannerPort/health")) {
    Write-Host "Starting EDQ host scanner on port $HostScannerPort..."
    Start-Process `
        -FilePath "powershell.exe" `
        -ArgumentList @(
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            $HelperScript,
            "-Run",
            "-Port",
            "$HostScannerPort"
        ) `
        -WorkingDirectory $RepoRoot `
        -WindowStyle Hidden

    for ($i = 0; $i -lt 20; $i++) {
        if (Test-HttpOk "http://127.0.0.1:$HostScannerPort/health") {
            Write-Host "Host scanner is ready."
            break
        }
        Start-Sleep -Milliseconds 500
    }
} else {
    Write-Host "Host scanner is already running on port $HostScannerPort."
}

$env:TOOLS_SIDECAR_URL = "http://host.docker.internal:$HostScannerPort"
$env:EDQ_SCANNER_MODE = "host"
$env:EDQ_START_INTERNAL_TOOLS = "false"
$env:HOST_ARP_HELPER_URL = "http://host.docker.internal:$HostScannerPort"

Set-Location $RepoRoot
if ($NoBuild) {
    docker compose up -d
} else {
    docker compose up --build -d
}

Write-Host "EDQ Docker stack started."
