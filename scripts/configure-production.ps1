param(
    [Parameter(Mandatory = $true)]
    [string]$Domain,
    [string[]]$CorsOrigins = @(),
    [string[]]$AuthorizedCidrs = @(),
    [string]$BaseUrl = "",
    [string]$AdminUser = "admin",
    [string]$AdminPass = "",
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$EnvPath = Join-Path $RepoRoot ".env"

function Test-LoopbackHost {
    param([string]$HostName)
    if ([string]::IsNullOrWhiteSpace($HostName)) {
        return $false
    }
    $normalized = $HostName.Trim().Trim([char[]]"[]").ToLowerInvariant()
    if ($normalized -eq "localhost" -or $normalized.EndsWith(".localhost")) {
        return $true
    }
    $ip = $null
    if ([System.Net.IPAddress]::TryParse($normalized, [ref]$ip)) {
        return [System.Net.IPAddress]::IsLoopback($ip)
    }
    return $false
}

function Assert-ProductionDomain {
    param([string]$Value)

    if ([string]::IsNullOrWhiteSpace($Value)) {
        throw "Domain is required."
    }
    $candidate = $Value.Trim()
    if ($candidate -match "^https?://") {
        throw "Pass only the hostname in -Domain, for example edq.example.com."
    }
    if (Test-LoopbackHost $candidate) {
        throw "Production domain must not be localhost."
    }
    if ($candidate.Length -gt 253 -or $candidate -match '[/:\\?#\s*]') {
        throw "Domain must be a hostname without paths, ports, wildcards, or whitespace."
    }
    foreach ($label in ($candidate -split "\.")) {
        if (
            [string]::IsNullOrWhiteSpace($label) -or
            $label.Length -gt 63 -or
            $label -notmatch "^[A-Za-z0-9]([A-Za-z0-9-]*[A-Za-z0-9])?$"
        ) {
            throw "Domain contains an invalid DNS label: $label"
        }
    }
    return $candidate.ToLowerInvariant()
}

function Assert-HttpsOrigin {
    param([string]$Value)

    if ([string]::IsNullOrWhiteSpace($Value)) {
        throw "Production CORS origin must not be empty."
    }

    $origin = $Value.Trim()
    if ($origin -match "localhost|127\.0\.0\.1|::1") {
        throw "Production CORS origin must not be localhost: $origin"
    }

    $uri = $null
    if (
        -not [System.Uri]::TryCreate($origin, [System.UriKind]::Absolute, [ref]$uri) -or
        $uri.Scheme -ne "https" -or
        [string]::IsNullOrWhiteSpace($uri.Host) -or
        (Test-LoopbackHost $uri.Host) -or
        -not [string]::IsNullOrWhiteSpace($uri.UserInfo) -or
        $uri.AbsolutePath -ne "/" -or
        -not [string]::IsNullOrWhiteSpace($uri.Query) -or
        -not [string]::IsNullOrWhiteSpace($uri.Fragment)
    ) {
        throw "Production CORS origin must be an explicit https origin without paths, query strings, or fragments: $origin"
    }

    return "$($uri.Scheme)://$($uri.Authority)"
}

function ConvertTo-JsonArrayLiteral {
    param([string[]]$Values)

    $encoded = @()
    foreach ($value in $Values) {
        $escaped = $value.Replace("\", "\\").Replace('"', '\"')
        $encoded += '"' + $escaped + '"'
    }
    return "[" + ($encoded -join ",") + "]"
}

function Assert-Ipv4Cidr {
    param([string]$Cidr)

    $parts = $Cidr.Trim().Split("/")
    if ($parts.Count -ne 2) {
        throw "Invalid CIDR: $Cidr"
    }
    try {
        $addr = [System.Net.IPAddress]::Parse($parts[0])
    } catch {
        throw "Invalid CIDR address: $Cidr"
    }
    if ($addr.AddressFamily -ne [System.Net.Sockets.AddressFamily]::InterNetwork) {
        throw "Only IPv4 CIDRs are supported for scan authorization: $Cidr"
    }
    if ($parts[1] -notmatch "^\d{1,2}$") {
        throw "Invalid CIDR prefix: $Cidr"
    }
    $prefix = [int]$parts[1]
    if ($prefix -lt 16 -or $prefix -gt 32) {
        throw "Authorized CIDR prefix must be between /16 and /32: $Cidr"
    }
    return "$($addr.IPAddressToString)/$prefix"
}

function Set-EnvValue {
    param(
        [string[]]$Lines,
        [string]$Key,
        [string]$Value
    )

    $found = $false
    $updated = foreach ($line in $Lines) {
        if ($line -match "^\s*#") {
            $line
        } elseif ($line -match "^$([regex]::Escape($Key))=") {
            $found = $true
            "$Key=$Value"
        } else {
            $line
        }
    }

    if (-not $found) {
        $updated += "$Key=$Value"
    }
    return $updated
}

function Get-RootEnvValue {
    param([string]$Name)

    if (-not (Test-Path $EnvPath)) {
        return $null
    }
    $line = Get-Content $EnvPath | Where-Object { $_ -match "^$([regex]::Escape($Name))=" } | Select-Object -First 1
    if (-not $line) {
        return $null
    }
    return (($line -split "=", 2)[1].Trim()).Trim("'").Trim('"')
}

function Resolve-AdminPassword {
    if ($AdminPass) {
        return $AdminPass
    }
    if ($env:EDQ_ADMIN_PASS) {
        return $env:EDQ_ADMIN_PASS
    }
    return Get-RootEnvValue "INITIAL_ADMIN_PASSWORD"
}

function Resolve-CurrentBaseUrl {
    if ($BaseUrl) {
        return $BaseUrl.TrimEnd("/")
    }

    if ($script:publicUrl) {
        return $script:publicUrl.TrimEnd("/")
    }

    throw "Could not resolve authorization API URL. Pass -BaseUrl explicitly."
}

function Add-AuthorizedCidr {
    param(
        [string]$ApiUrl,
        [string]$Cidr,
        [Microsoft.PowerShell.Commands.WebRequestSession]$Session,
        [string]$CsrfToken
    )

    $payload = @{
        cidr = $Cidr
        label = "Production approved"
        description = "Configured by scripts/configure-production.ps1"
    } | ConvertTo-Json -Compress

    try {
        Invoke-RestMethod -Uri "$ApiUrl/authorized-networks/" -Method Post -ContentType "application/json" -Body $payload -Headers @{ "X-CSRF-Token" = $CsrfToken } -WebSession $Session | Out-Null
        Write-Host "Authorized $Cidr"
    } catch {
        $status = if ($_.Exception.Response) { [int]$_.Exception.Response.StatusCode.value__ } else { 0 }
        if ($status -eq 409) {
            Write-Host "$Cidr already authorized"
        } else {
            throw
        }
    }
}

$productionDomain = Assert-ProductionDomain $Domain
$publicUrl = "https://$productionDomain"
$normalizedAuthorizedCidrs = @()
foreach ($cidr in $AuthorizedCidrs) {
    if (-not [string]::IsNullOrWhiteSpace($cidr)) {
        $normalizedAuthorizedCidrs += Assert-Ipv4Cidr $cidr
    }
}
$AuthorizedCidrs = $normalizedAuthorizedCidrs
$normalizedCorsOrigins = @()
foreach ($originValue in $CorsOrigins) {
    foreach ($part in ($originValue -split ",")) {
        $trimmed = $part.Trim()
        if ($trimmed) {
            $normalizedCorsOrigins += (Assert-HttpsOrigin $trimmed)
        }
    }
}
$CorsOrigins = $normalizedCorsOrigins
if ($CorsOrigins.Count -eq 0) {
    $CorsOrigins = @($publicUrl)
}

if (-not (Test-Path $EnvPath)) {
    throw "Root .env does not exist. Run setup first."
}

$lines = Get-Content $EnvPath
$updates = [ordered]@{
    "DOMAIN" = $productionDomain
    "EDQ_PUBLIC_URL" = $publicUrl
    "ENVIRONMENT" = "cloud"
    "COOKIE_SECURE" = "true"
    "LOG_JSON" = "true"
    "DEBUG" = "false"
    "CORS_ORIGINS" = ConvertTo-JsonArrayLiteral $CorsOrigins
}

foreach ($entry in $updates.GetEnumerator()) {
    $lines = Set-EnvValue -Lines $lines -Key $entry.Key -Value $entry.Value
}

if ($DryRun) {
    Write-Host "Dry run. Would update .env with:"
    foreach ($entry in $updates.GetEnumerator()) {
        Write-Host "$($entry.Key)=$($entry.Value)"
    }
    if ($AuthorizedCidrs.Count -gt 0) {
        Write-Host "Dry run. Would authorize CIDR(s) against $(Resolve-CurrentBaseUrl): $($AuthorizedCidrs -join ', ')"
    }
} elseif ($AuthorizedCidrs.Count -gt 0) {
    $targetBaseUrl = Resolve-CurrentBaseUrl
    $apiUrl = "$targetBaseUrl/api"
    $password = Resolve-AdminPassword
    if ([string]::IsNullOrWhiteSpace($password) -or $password.StartsWith("CHANGE_ME") -or $password.StartsWith("change-me")) {
        throw "Set -AdminPass, EDQ_ADMIN_PASS, or INITIAL_ADMIN_PASSWORD before adding authorized CIDRs."
    }

    $session = New-Object Microsoft.PowerShell.Commands.WebRequestSession
    $loginPayload = @{ username = $AdminUser; password = $password } | ConvertTo-Json -Compress
    $login = Invoke-RestMethod -Uri "$apiUrl/auth/login" -Method Post -ContentType "application/json" -Body $loginPayload -WebSession $session
    if (-not $login.csrf_token) {
        throw "Login did not return a CSRF token."
    }

    foreach ($cidr in $AuthorizedCidrs) {
        Add-AuthorizedCidr -ApiUrl $apiUrl -Cidr $cidr -Session $session -CsrfToken $login.csrf_token
    }
}

if (-not $DryRun) {
    Set-Content -Path $EnvPath -Value $lines -Encoding UTF8
    Write-Host "Updated root .env for $productionDomain"
}
