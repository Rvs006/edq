param(
    [int]$HostScannerPort = 8002,
    [switch]$InstallMissing,
    [switch]$InstallHostScannerStartup,
    [switch]$StartStack,
    [switch]$NoBuild,
    [switch]$SkipPreflight,
    [switch]$SkipVerify,
    [switch]$OpenBrowser,
    [switch]$NoElevate,
    [switch]$ElevatedRelaunch
)

$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$StartScript = Join-Path $RepoRoot "scripts\start-edq.ps1"
$PreflightScript = Join-Path $RepoRoot "scripts\preflight-scanner.ps1"
$VerifyScript = Join-Path $RepoRoot "scripts\verify-app.ps1"
$HostHelperScript = Join-Path $RepoRoot "scripts\start-host-mac-helper.ps1"
$Results = New-Object System.Collections.Generic.List[object]

function Add-Result {
    param(
        [string]$Name,
        [string]$Status,
        [string]$Message
    )

    $Results.Add([pscustomobject]@{
        name = $Name
        status = $Status
        message = $Message
    }) | Out-Null
}

function Write-Result {
    param([object]$Result)

    $color = switch ($Result.status) {
        "ok" { "Green" }
        "warn" { "Yellow" }
        "fail" { "Red" }
        default { "Gray" }
    }

    Write-Host ("[{0}] {1}: {2}" -f $Result.status.ToUpperInvariant(), $Result.name, $Result.message) -ForegroundColor $color
}

function Test-CommandAvailable {
    param([string]$Name)
    return $null -ne (Get-Command $Name -ErrorAction SilentlyContinue)
}

function Test-IsWindows {
    return [System.Environment]::OSVersion.Platform -eq [System.PlatformID]::Win32NT -or $PSVersionTable.Platform -eq "Win32NT" -or $env:OS -eq "Windows_NT"
}

function Test-IsAdministrator {
    if (-not (Test-IsWindows)) {
        return $false
    }

    $principal = [Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Test-NpcapInstalled {
    if (Get-Service -Name "npcap" -ErrorAction SilentlyContinue) {
        return $true
    }

    return (Test-Path "HKLM:\SYSTEM\CurrentControlSet\Services\npcap") -or (Test-Path "HKLM:\SOFTWARE\Npcap")
}

function ConvertTo-ProcessArgument {
    param([string]$Value)

    if ($Value -match '[\s"]') {
        return '"' + ($Value -replace '"', '\"') + '"'
    }
    return $Value
}

function Invoke-ElevatedRelaunch {
    $arguments = @(
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        $PSCommandPath,
        "-HostScannerPort",
        "$HostScannerPort",
        "-ElevatedRelaunch"
    )

    if ($InstallMissing) { $arguments += "-InstallMissing" }
    if ($InstallHostScannerStartup) { $arguments += "-InstallHostScannerStartup" }
    if ($StartStack) { $arguments += "-StartStack" }
    if ($NoBuild) { $arguments += "-NoBuild" }
    if ($SkipPreflight) { $arguments += "-SkipPreflight" }
    if ($SkipVerify) { $arguments += "-SkipVerify" }
    if ($OpenBrowser) { $arguments += "-OpenBrowser" }

    $argumentString = ($arguments | ForEach-Object { ConvertTo-ProcessArgument $_ }) -join " "
    Start-Process -FilePath "powershell.exe" -ArgumentList $argumentString -Verb RunAs -WorkingDirectory $RepoRoot
}

function Invoke-WingetInstall {
    param(
        [string]$PackageId,
        [string]$DisplayName
    )

    if (-not (Test-CommandAvailable "winget")) {
        Add-Result $DisplayName "fail" "winget is not available; install $DisplayName manually."
        return $false
    }

    Write-Host "Installing $DisplayName with winget..."
    $wingetArgs = @(
        "install",
        "--id",
        $PackageId,
        "--exact",
        "--source",
        "winget",
        "--accept-source-agreements",
        "--accept-package-agreements"
    )

    & winget @wingetArgs
    if ($LASTEXITCODE -eq 0) {
        Add-Result $DisplayName "ok" "winget install completed for $PackageId."
        return $true
    }

    Add-Result $DisplayName "fail" "winget install failed for $PackageId with exit code $LASTEXITCODE."
    return $false
}

function Resolve-ComposeFrontendUrl {
    if (-not (Test-CommandAvailable "docker")) {
        return $null
    }

    try {
        $portLine = docker compose port frontend 8080 2>$null | Select-Object -First 1
        if ($LASTEXITCODE -ne 0 -or -not $portLine) {
            return $null
        }

        $port = ([string]$portLine -split ":")[-1].Trim()
        if ($port -match "^\d+$") {
            return "http://localhost:$port"
        }
    } catch {
        return $null
    }

    return $null
}

function Invoke-CheckedScript {
    param(
        [string]$Label,
        [string]$ScriptPath,
        [string[]]$Arguments = @()
    )

    Write-Host ""
    Write-Host $Label
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $ScriptPath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Label failed with exit code $LASTEXITCODE."
    }
}

Write-Host ""
Write-Host "EDQ engineer workstation setup"
Write-Host "Repository: $RepoRoot"
Write-Host ""

$isWindows = Test-IsWindows
$isAdmin = Test-IsAdministrator

if ($isWindows) {
    if ($isAdmin) {
        Add-Result "Administrator shell" "ok" "PowerShell is elevated."
    } else {
        Add-Result "Administrator shell" "warn" "Not elevated. Installs, Npcap, firewall changes, and raw discovery may need admin approval."
    }
} else {
    Add-Result "Operating system" "warn" "This bootstrap is tuned for Windows engineer workstations."
}

if (($InstallMissing -or $InstallHostScannerStartup) -and $isWindows -and -not $isAdmin -and -not $NoElevate -and -not $ElevatedRelaunch) {
    Write-Host "Installer or startup-task work requested from a non-admin shell."
    Write-Host "Relaunching this setup in an Administrator PowerShell window..."
    Invoke-ElevatedRelaunch
    exit 0
}

if (Test-CommandAvailable "docker") {
    Add-Result "Docker CLI" "ok" "docker is on PATH."
} elseif ($InstallMissing) {
    Invoke-WingetInstall "Docker.DockerDesktop" "Docker Desktop" | Out-Null
} else {
    Add-Result "Docker CLI" "fail" "Docker Desktop is missing. Rerun with -InstallMissing or install Docker Desktop."
}

if (Test-CommandAvailable "python") {
    $pythonVersion = python --version 2>&1
    Add-Result "Python" "ok" "$pythonVersion is on PATH."
} elseif ($InstallMissing) {
    Invoke-WingetInstall "Python.Python.3.12" "Python 3.12" | Out-Null
} else {
    Add-Result "Python" "fail" "Python 3.12+ is missing. Rerun with -InstallMissing or install Python."
}

if (Test-CommandAvailable "nmap") {
    Add-Result "Nmap" "ok" "nmap is on PATH for host-network discovery."
} elseif ($InstallMissing) {
    Invoke-WingetInstall "Insecure.Nmap" "Nmap" | Out-Null
} else {
    Add-Result "Nmap" "warn" "nmap is missing on the host. Docker scans still work, but direct-Ethernet discovery is weaker."
}

if ($isWindows) {
    if (Test-NpcapInstalled) {
        Add-Result "Npcap" "ok" "Npcap driver/service is installed."
    } elseif ($InstallMissing) {
        Invoke-WingetInstall "Insecure.Npcap" "Npcap" | Out-Null
    } else {
        Add-Result "Npcap" "warn" "Npcap is not detected. Direct-Ethernet packet capture may require installing Npcap."
    }
}

if (Test-CommandAvailable "curl.exe") {
    Add-Result "curl.exe" "ok" "curl.exe is available."
} elseif (Test-CommandAvailable "curl") {
    Add-Result "curl" "warn" "curl is available, but Windows scripts prefer curl.exe."
} else {
    Add-Result "curl.exe" "fail" "curl.exe is missing."
}

if (Test-CommandAvailable "winget") {
    Add-Result "winget" "ok" "winget is available for optional prerequisite installs."
} else {
    Add-Result "winget" "warn" "winget is not available; missing prerequisites must be installed manually."
}

if ($InstallHostScannerStartup) {
    Invoke-CheckedScript `
        -Label "Installing EDQ host scanner startup task" `
        -ScriptPath $HostHelperScript `
        -Arguments @("-InstallDeps", "-InstallStartupTask", "-Port", "$HostScannerPort")
    Add-Result "Host scanner startup" "ok" "Host scanner startup registration completed."
}

if (-not $SkipPreflight) {
    $preflightArgs = @("-SkipRuntimeChecks")
    Invoke-CheckedScript -Label "Running prerequisite preflight" -ScriptPath $PreflightScript -Arguments $preflightArgs
    Add-Result "Prerequisite preflight" "ok" "Required setup checks completed."
}

if ($StartStack) {
    $startArgs = @("-HostScannerPort", "$HostScannerPort")
    if ($NoBuild) { $startArgs += "-NoBuild" }
    $startArgs += "-SkipPreflight"

    Invoke-CheckedScript -Label "Starting EDQ production-like Docker stack" -ScriptPath $StartScript -Arguments $startArgs
    Add-Result "Docker stack" "ok" "EDQ Docker stack started."

    if (-not $SkipPreflight) {
        Invoke-CheckedScript -Label "Running full scanner preflight" -ScriptPath $PreflightScript
        Add-Result "Scanner preflight" "ok" "Runtime scanner checks completed."
    }

    if (-not $SkipVerify) {
        Invoke-CheckedScript -Label "Running EDQ integration verification" -ScriptPath $VerifyScript
        Add-Result "Integration verification" "ok" "Application smoke checks completed."
    }
}

$frontendUrl = Resolve-ComposeFrontendUrl
if (-not $frontendUrl) {
    $frontendUrl = "http://localhost:3000"
}

if ($OpenBrowser) {
    Start-Process $frontendUrl
}

Write-Host ""
Write-Host "Setup summary"
foreach ($result in $Results) {
    Write-Result $result
}

Write-Host ""
Write-Host "Daily launcher:"
Write-Host "  powershell -ExecutionPolicy Bypass -File .\scripts\start-edq.ps1"
Write-Host ""
Write-Host "Production-like local test URL:"
Write-Host "  $frontendUrl"

if (@($Results | Where-Object { $_.status -eq "fail" }).Count -gt 0) {
    exit 1
}
