param(
    [string]$BaseUrl = "",
    [string]$AdminUser = "admin",
    [string]$AdminPass = "",
    [string[]]$DeviceIps = @(),
    [int]$SinceDays = 30,
    [int]$MinCompletedRuns = 1,
    [int]$MinDistinctDevices = 1,
    [switch]$AllowUnspecifiedDevices,
    [switch]$AllowSyntheticDevices,
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

function Test-SyntheticDevice {
    param([object]$Device)

    if (-not $Device) {
        return $false
    }

    $hostname = [string]$Device.hostname
    $manufacturer = [string]$Device.manufacturer
    $model = [string]$Device.model
    return (
        $hostname -match "E2E|Smoke" -or
        ($manufacturer -eq "EDQ" -and $model -eq "Smoke")
    )
}

$session = New-Object Microsoft.PowerShell.Commands.WebRequestSession
$base = Resolve-BaseUrl
$api = "$($base.TrimEnd('/'))/api"
$password = Resolve-AdminPassword
$cutoff = (Get-Date).AddDays(-1 * $SinceDays)

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

    if ($DeviceIps.Count -eq 0 -and -not $AllowUnspecifiedDevices) {
        Add-Check "Pilot device scope" "error" "Pass every expected pilot device with -DeviceIps, or use -AllowUnspecifiedDevices for exploratory reporting."
    } elseif ($DeviceIps.Count -gt 0) {
        Add-Check "Pilot device scope" "ok" "Checking requested pilot device IP(s): $($DeviceIps -join ', ')."
    } else {
        Add-Check "Pilot device scope" "warning" "No pilot device IPs were specified; exploratory reporting only."
    }

    $rawDevices = Invoke-RestMethod -Uri "$api/devices/?limit=200" -Method Get -WebSession $session -TimeoutSec 20
    $devices = @($rawDevices | ForEach-Object { $_ })
    $devicesById = @{}
    foreach ($device in $devices) {
        $devicesById[$device.id] = $device
    }

    $rawRuns = Invoke-RestMethod -Uri "$api/test-runs/?limit=200&include_internal=true" -Method Get -WebSession $session -TimeoutSec 20
    $runs = @($rawRuns | ForEach-Object { $_ })

    $candidateRuns = @()
    $syntheticRuns = @()
    foreach ($run in $runs) {
        if ($run.status -ne "completed") {
            continue
        }
        if (-not $run.completed_at) {
            continue
        }
        $completedAt = [datetime]$run.completed_at
        if ($completedAt -lt $cutoff) {
            continue
        }
        if ($run.completed_tests -lt 1 -or -not $run.overall_verdict) {
            continue
        }

        $device = $devicesById[$run.device_id]
        if ($DeviceIps.Count -gt 0 -and ($DeviceIps -notcontains $run.device_ip)) {
            continue
        }
        if ((Test-SyntheticDevice $device) -and -not $AllowSyntheticDevices) {
            $syntheticRuns += $run
            continue
        }
        $candidateRuns += $run
    }

    if ($AllowSyntheticDevices) {
        Add-Check "Synthetic filter" "warning" "Synthetic test devices are allowed for this report."
    } elseif ($syntheticRuns.Count -gt 0) {
        Add-Check "Synthetic filter" "ok" "Excluded $($syntheticRuns.Count) synthetic run(s)."
    } else {
        Add-Check "Synthetic filter" "ok" "No synthetic pilot runs were included."
    }

    $distinctDeviceIds = @($candidateRuns | ForEach-Object { $_.device_id } | Sort-Object -Unique)
    if ($candidateRuns.Count -ge $MinCompletedRuns) {
        Add-Check "Completed pilot runs" "ok" "$($candidateRuns.Count) completed qualifying run(s) in the last $SinceDays day(s)."
    } else {
        Add-Check "Completed pilot runs" "error" "Expected at least $MinCompletedRuns completed qualifying run(s); found $($candidateRuns.Count)."
    }

    if ($distinctDeviceIds.Count -ge $MinDistinctDevices) {
        Add-Check "Pilot devices" "ok" "$($distinctDeviceIds.Count) distinct device(s) represented."
    } else {
        Add-Check "Pilot devices" "error" "Expected at least $MinDistinctDevices distinct device(s); found $($distinctDeviceIds.Count)."
    }

    if ($DeviceIps.Count -gt 0) {
        $coveredIps = @($candidateRuns | ForEach-Object { $_.device_ip } | Sort-Object -Unique)
        $missingIps = @($DeviceIps | Where-Object { $coveredIps -notcontains $_ })
        if ($missingIps.Count -eq 0) {
            Add-Check "Requested devices" "ok" "All requested device IPs have qualifying completed runs."
        } else {
            Add-Check "Requested devices" "error" "Missing qualifying completed runs for: $($missingIps -join ', ')."
        }
    }

    $verdicts = @($candidateRuns | ForEach-Object { $_.overall_verdict } | Sort-Object -Unique)
    if ($candidateRuns.Count -gt 0) {
        Add-Check "Pilot verdicts" "ok" "Observed verdict(s): $($verdicts -join ', ')."
    }
} catch {
    Add-Check "Real-device pilot report" "error" $_.Exception.Message
}

if ($Json) {
    $Checks | ConvertTo-Json -Depth 5
} else {
    Write-Host ""
    Write-Host "EDQ real-device pilot report"
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
