param(
    [string]$BaseUrl = "",
    [string]$AdminUser = "admin",
    [string]$AdminPass = "",
    [int]$ReviewDays = 30,
    [switch]$AllowWideRanges,
    [switch]$DisableLegacyAutoAuthorized,
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

function Get-CidrPrefix {
    param([string]$Cidr)
    if ($Cidr -match "/(\d{1,2})$") {
        return [int]$Matches[1]
    }
    return -1
}

$session = New-Object Microsoft.PowerShell.Commands.WebRequestSession
$base = Resolve-BaseUrl
$api = "$($base.TrimEnd('/'))/api"
$password = Resolve-AdminPassword

try {
    if (-not $password -or $password.StartsWith("CHANGE_ME") -or $password.StartsWith("change-me")) {
        throw "Set -AdminPass, EDQ_ADMIN_PASS, or INITIAL_ADMIN_PASSWORD."
    }

    $loginPayload = @{ username = $AdminUser; password = $password } | ConvertTo-Json -Compress
    $login = Invoke-RestMethod -Uri "$api/auth/login" -Method Post -ContentType "application/json" -Body $loginPayload -WebSession $session -TimeoutSec 10
    if (-not $login.csrf_token) {
        throw "Login response did not include a CSRF token."
    }
    Add-Check "Runtime auth" "ok" "Admin login succeeded at $base."

    $csrfHeaders = @{ "X-CSRF-Token" = $login.csrf_token }
    $rawNetworks = Invoke-RestMethod -Uri "$api/authorized-networks/?active_only=true&limit=200" -Method Get -WebSession $session -TimeoutSec 10
    $networks = @($rawNetworks | ForEach-Object { $_ })
    if ($networks.Count -lt 1) {
        Add-Check "Authorized networks" "error" "No active authorized scan ranges are configured."
    } else {
        Add-Check "Authorized networks" "ok" "$($networks.Count) active authorized scan range(s)."
    }

    $invalidPrefixes = @()
    $wideRanges = @()
    $autoAuthorized = @()
    foreach ($network in $networks) {
        $prefix = Get-CidrPrefix $network.cidr
        if ($prefix -lt 16 -or $prefix -gt 32) {
            $invalidPrefixes += $network.cidr
        }
        if ($prefix -eq 16) {
            $wideRanges += $network.cidr
        }
        $label = [string]$network.label
        if ($label -match "Auto-authorized") {
            $autoAuthorized += $network.cidr
            if ($DisableLegacyAutoAuthorized) {
                $payload = @{ is_active = $false } | ConvertTo-Json -Compress
                Invoke-RestMethod -Uri "$api/authorized-networks/$($network.id)" -Method Patch -ContentType "application/json" -Body $payload -Headers $csrfHeaders -WebSession $session -TimeoutSec 10 | Out-Null
            }
        }
    }

    if ($invalidPrefixes.Count -gt 0) {
        Add-Check "CIDR bounds" "error" "Invalid active range prefix(es): $($invalidPrefixes -join ', ')."
    } else {
        Add-Check "CIDR bounds" "ok" "All active ranges are within /16 through /32."
    }

    if ($autoAuthorized.Count -gt 0 -and $DisableLegacyAutoAuthorized) {
        Add-Check "Auto-authorized ranges" "ok" "Disabled $($autoAuthorized.Count) legacy auto-authorized range(s). Add explicit approved ranges before scan work."
    } elseif ($autoAuthorized.Count -gt 0) {
        Add-Check "Auto-authorized ranges" "error" "Remove or manually review legacy auto-authorized range(s): $($autoAuthorized -join ', ')."
    } else {
        Add-Check "Auto-authorized ranges" "ok" "No active legacy auto-authorized ranges found."
    }

    if ($wideRanges.Count -gt 0 -and -not $AllowWideRanges) {
        Add-Check "Wide ranges" "warning" "/16 ranges require explicit operational approval: $($wideRanges -join ', ')."
    } else {
        Add-Check "Wide ranges" "ok" "No unapproved /16 range warning for this report."
    }

    $dateFrom = (Get-Date).AddDays(-1 * $ReviewDays).ToString("yyyy-MM-ddTHH:mm:ss")
    $scanAudit = Invoke-RestMethod -Uri "$api/audit-logs/?limit=500&date_from=$([uri]::EscapeDataString($dateFrom))" -Method Get -WebSession $session -TimeoutSec 10
    $items = @($scanAudit.items)
    $scanActions = @($items | Where-Object {
        $_.action -match "scan|test_run.start|authorized_network" -or $_.resource_type -match "network_scan|discovery|authorized_network|test_run"
    })
    Add-Check "Audit review window" "ok" "$($scanActions.Count) scan-governance audit event(s) in the last $ReviewDays day(s)."
} catch {
    Add-Check "Scanner governance report" "error" $_.Exception.Message
}

if ($Json) {
    $Checks | ConvertTo-Json -Depth 5
} else {
    Write-Host ""
    Write-Host "EDQ scanner governance report"
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
