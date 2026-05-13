param(
    [string]$ToolsUrl = "",
    [string]$HostScannerUrl = "",
    [string]$ToolsApiKey = "",
    [switch]$SkipRuntimeChecks,
    [switch]$Json
)

$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Checks = New-Object System.Collections.Generic.List[object]

function Get-RootEnvValue {
    param([string]$Name)

    $envFile = Join-Path $RepoRoot ".env"
    if (-not (Test-Path $envFile)) { return $null }

    $line = Get-Content $envFile | Where-Object { $_ -match "^$([regex]::Escape($Name))=" } | Select-Object -First 1
    if (-not $line) { return $null }

    $value = ($line -split "=", 2)[1].Trim()
    return $value.Trim("'").Trim('"')
}

function Add-Check {
    param(
        [string]$Name,
        [string]$Status,
        [string]$Message,
        [string]$Severity = "info"
    )
    $Checks.Add([pscustomobject]@{
        name = $Name
        status = $Status
        severity = $Severity
        message = $Message
    }) | Out-Null
}

function Test-CommandAvailable {
    param([string]$Name)
    return $null -ne (Get-Command $Name -ErrorAction SilentlyContinue)
}

function Invoke-JsonGet {
    param(
        [string]$Url,
        [hashtable]$Headers = $null
    )

    if ($Headers) {
        return Invoke-RestMethod -Uri $Url -Method Get -Headers $Headers -TimeoutSec 5
    }
    return Invoke-RestMethod -Uri $Url -Method Get -TimeoutSec 5
}

function Resolve-HostScannerCheckUrls {
    param(
        [string]$Url,
        [bool]$IsWindowsHost
    )

    $urls = New-Object System.Collections.Generic.List[string]
    $urls.Add($Url.TrimEnd("/")) | Out-Null

    try {
        $uri = [Uri]$Url
        if ($IsWindowsHost -and $uri.Host -eq "host.docker.internal") {
            $builder = [UriBuilder]::new($uri)
            $builder.Host = "127.0.0.1"
            $urls.Add($builder.Uri.AbsoluteUri.TrimEnd("/")) | Out-Null
        }
    } catch {
        return @($urls | Select-Object -Unique)
    }

    return @($urls | Select-Object -Unique)
}

if (-not $ToolsUrl) {
    $ToolsUrl = $env:TOOLS_SIDECAR_URL
}
if (-not $ToolsUrl) {
    $ToolsUrl = Get-RootEnvValue "TOOLS_SIDECAR_URL"
}
if (-not $ToolsUrl) {
    $ToolsUrl = "http://127.0.0.1:8001"
}
$ToolsUrl = $ToolsUrl.TrimEnd("/")

if (-not $ToolsApiKey) {
    $ToolsApiKey = $env:TOOLS_API_KEY
}
if (-not $ToolsApiKey) {
    $ToolsApiKey = Get-RootEnvValue "TOOLS_API_KEY"
}
$ToolsHeaders = $null
if ($ToolsApiKey) {
    $ToolsHeaders = @{ "X-Tools-Key" = $ToolsApiKey }
}

if (-not $HostScannerUrl) {
    $HostScannerUrl = $env:HOST_NETWORK_SCANNER_URL
}
if (-not $HostScannerUrl) {
    $HostScannerUrl = Get-RootEnvValue "HOST_NETWORK_SCANNER_URL"
}
if (-not $HostScannerUrl) {
    $HostScannerUrl = "http://127.0.0.1:8002"
}
$HostScannerUrl = $HostScannerUrl.TrimEnd("/")

$RunningOnWindows = [System.Environment]::OSVersion.Platform -eq [System.PlatformID]::Win32NT -or $PSVersionTable.Platform -eq "Win32NT" -or $env:OS -eq "Windows_NT"
$HostScannerCheckUrls = Resolve-HostScannerCheckUrls $HostScannerUrl $RunningOnWindows
if ($RunningOnWindows) {
    $principal = [Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()
    $isAdmin = $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    if ($isAdmin) {
        Add-Check "Administrator shell" "ok" "PowerShell is elevated."
    } else {
        Add-Check "Administrator shell" "warning" "Not elevated. Docker Desktop can work without elevation, but packet capture, Nmap host mode, and firewall changes may need an Administrator shell." "warning"
    }
}

if (Test-CommandAvailable "docker") {
    Add-Check "Docker CLI" "ok" "docker is on PATH."
    try {
        $dockerInfo = docker info --format "{{.ServerVersion}}" 2>$null
        if ($LASTEXITCODE -eq 0 -and $dockerInfo) {
            Add-Check "Docker daemon" "ok" "Docker daemon is reachable (server $dockerInfo)."
        } else {
            Add-Check "Docker daemon" "error" "Docker daemon is not reachable. Start Docker Desktop, then rerun preflight." "error"
        }
    } catch {
        Add-Check "Docker daemon" "error" "Docker daemon check failed: $($_.Exception.Message)" "error"
    }

    try {
        $composeVersion = docker compose version --short 2>$null
        if ($LASTEXITCODE -eq 0 -and $composeVersion) {
            Add-Check "Docker Compose" "ok" "docker compose $composeVersion is available."
        } else {
            Add-Check "Docker Compose" "error" "docker compose is not available through Docker CLI." "error"
        }
    } catch {
        Add-Check "Docker Compose" "error" "docker compose check failed: $($_.Exception.Message)" "error"
    }
} else {
    Add-Check "Docker CLI" "error" "docker is not on PATH. Install Docker Desktop." "error"
}

if (Test-CommandAvailable "curl.exe") {
    Add-Check "curl.exe" "ok" "curl.exe is available for smoke checks and downloads."
} elseif (Test-CommandAvailable "curl") {
    Add-Check "curl" "warning" "curl is available, but Windows scripts prefer curl.exe to avoid PowerShell alias behavior." "warning"
} else {
    Add-Check "curl.exe" "error" "curl.exe is missing. Install curl or enable the Windows optional curl package." "error"
}

if (Test-CommandAvailable "python") {
    $pythonVersion = python --version 2>&1
    Add-Check "Python" "ok" "$pythonVersion is available for the host scanner helper."
} else {
    Add-Check "Python" "error" "python is not on PATH. Install Python 3.12+ before using the Windows host scanner helper." "error"
}

if (Test-CommandAvailable "wsl") {
    Add-Check "WSL" "ok" "WSL is available as a fallback for Linux-oriented scanner tools."
} else {
    Add-Check "WSL" "warning" "WSL is not available. EDQ can still use the Docker sidecar for testssl.sh, ssh-audit, hydra, nikto, and snmpwalk." "warning"
}

if (Test-CommandAvailable "nmap") {
    Add-Check "Host Nmap" "ok" "nmap is on the Windows PATH for host-network discovery."
} else {
    Add-Check "Host Nmap" "warning" "nmap is not on the Windows PATH. Docker sidecar scans still work, but Windows direct-Ethernet discovery is better with Nmap installed on the host." "warning"
}

if (-not $SkipRuntimeChecks) {
    try {
        $health = Invoke-JsonGet "$ToolsUrl/health"
        $status = [string]$health.status
        if ($status -in @("ok", "healthy")) {
            Add-Check "Tools sidecar health" "ok" "Tools sidecar reports $status at $ToolsUrl."
        } else {
            Add-Check "Tools sidecar health" "error" "Tools sidecar reports '$status' at $ToolsUrl. Rebuild backend with docker compose up --build -d backend." "error"
        }
    } catch {
        Add-Check "Tools sidecar health" "error" "Could not reach $ToolsUrl/health. Start EDQ or check TOOLS_SIDECAR_URL." "error"
    }

    try {
        if (-not $ToolsHeaders) {
            throw "TOOLS_API_KEY is not set in the environment or repo-root .env."
        }
        $versions = Invoke-JsonGet "$ToolsUrl/versions" $ToolsHeaders
        $toolVersions = $versions.versions
        $required = @("nmap", "testssl", "ssh_audit", "hydra", "nikto", "snmpwalk")
        $missing = @()
        foreach ($tool in $required) {
            $value = $toolVersions.$tool
            if (-not $value -or [string]$value -eq "unavailable") {
                $missing += $tool
            }
        }
        if ($missing.Count -eq 0) {
            Add-Check "Scanner tools" "ok" "Required scanner tools are present: nmap, testssl.sh, ssh-audit, hydra, nikto, snmpwalk."
        } else {
            Add-Check "Scanner tools" "error" "Missing or unavailable scanner tools: $($missing -join ', '). Rebuild the backend image." "error"
        }
    } catch {
        Add-Check "Scanner tools" "error" "Could not read $ToolsUrl/versions: $($_.Exception.Message)" "error"
    }

    $hostScannerReached = $false
    $hostScannerErrors = @()
    foreach ($candidateUrl in $HostScannerCheckUrls) {
        try {
            $hostHealth = Invoke-JsonGet "$candidateUrl/health"
            if ($candidateUrl -eq $HostScannerUrl) {
                Add-Check "Host scanner" "ok" "Host network scanner is reachable at $candidateUrl ($($hostHealth.status))."
            } else {
                Add-Check "Host scanner" "ok" "Host network scanner is reachable from this shell at $candidateUrl ($($hostHealth.status)); Docker containers should use $HostScannerUrl."
            }
            $hostScannerReached = $true
            break
        } catch {
            $hostScannerErrors += "${candidateUrl}: $($_.Exception.Message)"
        }
    }
    if (-not $hostScannerReached) {
        Add-Check "Host scanner" "warning" "Host scanner is not reachable. Tried: $($hostScannerErrors -join '; '). This is optional unless you need Windows direct-Ethernet ARP/Nmap visibility." "warning"
    }
}

if ($Json) {
    $Checks | ConvertTo-Json -Depth 4
} else {
    Write-Host ""
    Write-Host "EDQ scanner preflight"
    Write-Host "Tools sidecar: $ToolsUrl"
    Write-Host "Host scanner:  $HostScannerUrl"
    Write-Host ""
    foreach ($check in $Checks) {
        $color = switch ($check.severity) {
            "error" { "Red" }
            "warning" { "Yellow" }
            default { "Green" }
        }
        Write-Host ("[{0}] {1}: {2}" -f $check.status.ToUpperInvariant(), $check.name, $check.message) -ForegroundColor $color
    }
}

if (@($Checks | Where-Object { $_.severity -eq "error" }).Count -gt 0) {
    exit 1
}
