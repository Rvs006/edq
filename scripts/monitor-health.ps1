param(
    [string]$BaseUrl = "",
    [string]$AdminUser = "admin",
    [string]$AdminPass = "",
    [string]$MetricsApiKey = "",
    [switch]$Json
)

$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Checks = New-Object System.Collections.Generic.List[object]

function Add-Check {
    param(
        [string]$Name,
        [string]$Status,
        [string]$Message
    )
    $Checks.Add([pscustomobject]@{
        name = $Name
        status = $Status
        message = $Message
    }) | Out-Null
}

function Get-RootEnvValue {
    param([string]$Name)

    $envFile = Join-Path $RepoRoot ".env"
    if (-not (Test-Path $envFile)) {
        return $null
    }

    $line = Get-Content $envFile | Where-Object { $_ -match "^$([regex]::Escape($Name))=" } | Select-Object -First 1
    if (-not $line) {
        return $null
    }

    $value = ($line -split "=", 2)[1].Trim()
    return $value.Trim("'").Trim('"')
}

function Resolve-BaseUrl {
    if ($BaseUrl) { return $BaseUrl.TrimEnd("/") }
    if ($env:EDQ_URL) { return $env:EDQ_URL.TrimEnd("/") }
    if ($env:EDQ_PUBLIC_URL) { return $env:EDQ_PUBLIC_URL.TrimEnd("/") }

    $publicUrl = Get-RootEnvValue "EDQ_PUBLIC_URL"
    if ($publicUrl) { return $publicUrl.TrimEnd("/") }

    $publicPort = $env:EDQ_PUBLIC_PORT
    if (-not $publicPort) { $publicPort = Get-RootEnvValue "EDQ_PUBLIC_PORT" }
    if (-not $publicPort) { $publicPort = "3000" }
    return "http://localhost:$publicPort"
}

function Resolve-AdminPassword {
    if ($AdminPass) { return $AdminPass }
    if ($env:EDQ_ADMIN_PASS) { return $env:EDQ_ADMIN_PASS }
    return Get-RootEnvValue "INITIAL_ADMIN_PASSWORD"
}

function Resolve-MetricsApiKey {
    if ($MetricsApiKey) { return $MetricsApiKey }
    if ($env:METRICS_API_KEY) { return $env:METRICS_API_KEY }
    return Get-RootEnvValue "METRICS_API_KEY"
}

$base = Resolve-BaseUrl
$api = "$($base.TrimEnd('/'))/api"
$session = New-Object Microsoft.PowerShell.Commands.WebRequestSession

try {
    $health = Invoke-RestMethod -Uri "$api/health" -Method Get -TimeoutSec 10
    if ($health.status -eq "ok" -and $health.database -eq "ok") {
        Add-Check "API health" "ok" "API and database are healthy at $base."
    } else {
        Add-Check "API health" "error" "Health status=$($health.status), database=$($health.database)."
    }
} catch {
    Add-Check "API health" "error" $_.Exception.Message
}

try {
    $metricsKey = Resolve-MetricsApiKey
    $curl = Get-Command curl.exe -ErrorAction SilentlyContinue
    if (-not $curl) {
        $curl = Get-Command curl -ErrorAction SilentlyContinue
    }
    if (-not $curl) {
        throw "curl is required for the metrics check."
    }
    $curlArgs = @("-fsSL")
    if ($metricsKey) {
        $curlArgs += @("-H", "Authorization: Bearer $metricsKey")
    }
    $curlArgs += "$api/health/metrics"
    $body = ((& $curl.Source @curlArgs) -join "`n")
    if ($LASTEXITCODE -ne 0) {
        throw "Metrics endpoint request failed."
    }
    if ($body -match "(?m)^edq_up 1$") {
        Add-Check "Metrics" "ok" "Prometheus metrics endpoint reports edq_up 1."
    } else {
        Add-Check "Metrics" "error" "Metrics endpoint did not report edq_up 1."
    }
} catch {
    Add-Check "Metrics" "error" $_.Exception.Message
}

try {
    $password = Resolve-AdminPassword
    if (-not $password -or $password.StartsWith("CHANGE_ME") -or $password.StartsWith("change-me")) {
        Add-Check "Tool versions" "warning" "Admin password unavailable; skipping authenticated tool check."
    } else {
        $payload = @{ username = $AdminUser; password = $password } | ConvertTo-Json -Compress
        Invoke-RestMethod -Uri "$api/auth/login" -Method Post -ContentType "application/json" -Body $payload -WebSession $session -TimeoutSec 10 | Out-Null
        $versions = Invoke-RestMethod -Uri "$api/health/tools/versions" -Method Get -WebSession $session -TimeoutSec 20
        $toolCount = @($versions.tools.PSObject.Properties).Count
        if ($versions.status -eq "ok" -and $toolCount -gt 0) {
            Add-Check "Tool versions" "ok" "$toolCount scanner tool version(s) returned."
        } else {
            Add-Check "Tool versions" "error" "Tools sidecar status=$($versions.status)."
        }
    }
} catch {
    Add-Check "Tool versions" "error" $_.Exception.Message
}

if ($Json) {
    $Checks | ConvertTo-Json -Depth 5
} else {
    Write-Host ""
    Write-Host "EDQ health monitor"
    Write-Host ""
    foreach ($check in $Checks) {
        $color = switch ($check.status) {
            "error" { "Red" }
            "warning" { "Yellow" }
            default { "Green" }
        }
        Write-Host ("[{0}] {1}: {2}" -f $check.status.ToUpperInvariant(), $check.name, $check.message) -ForegroundColor $color
    }
}

if (@($Checks | Where-Object { $_.status -eq "error" }).Count -gt 0) {
    exit 1
}
