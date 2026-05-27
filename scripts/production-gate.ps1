param(
    [ValidateSet("pilot", "production")]
    [string]$Mode = "pilot",
    [ValidateSet("env", "prod-compose", "tls-compose")]
    [string]$DeploymentConfig = "env",
    [string]$BaseUrl = "",
    [string]$AdminUser = "admin",
    [string]$AdminPass = "",
    [switch]$SkipRuntimeChecks,
    [switch]$SkipGitChecks,
    [switch]$Json
)

$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Checks = New-Object System.Collections.Generic.List[object]
$Production = $Mode -eq "production"
$EffectiveEnv = @{}
$FrontendEnv = @{}
$PublicEnv = @{}

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

function Get-EffectiveEnvValue {
    param([string]$Name)
    if ($EffectiveEnv.ContainsKey($Name)) {
        return [string]$EffectiveEnv[$Name]
    }
    $processValue = [Environment]::GetEnvironmentVariable($Name)
    if ($processValue) {
        return $processValue
    }
    return Get-RootEnvValue $Name
}

function Add-DeploymentConfigChecks {
    if ($DeploymentConfig -eq "env") {
        return
    }

    $composeFiles = @("docker-compose.yml")
    if ($DeploymentConfig -eq "prod-compose") {
        $composeFiles += "docker-compose.prod.yml"
    } elseif ($DeploymentConfig -eq "tls-compose") {
        $composeFiles += "docker-compose.tls.yml"
    }

    $args = @("compose")
    foreach ($file in $composeFiles) {
        $args += @("-f", $file)
    }
    $args += @("config", "--format", "json")

    try {
        $raw = & docker @args 2>$null
        if ($LASTEXITCODE -ne 0 -or -not $raw) {
            throw "docker $($args -join ' ') failed."
        }
        $config = ($raw | ConvertFrom-Json)
        $backendEnv = $config.services.backend.environment
        foreach ($prop in $backendEnv.PSObject.Properties) {
            $EffectiveEnv[$prop.Name] = $prop.Value
        }
        foreach ($serviceProp in $config.services.PSObject.Properties) {
            $serviceEnv = $serviceProp.Value.environment
            if (-not $serviceEnv) {
                continue
            }
            foreach ($prop in $serviceEnv.PSObject.Properties) {
                if (-not $PublicEnv.ContainsKey($prop.Name)) {
                    $PublicEnv[$prop.Name] = $prop.Value
                }
            }
        }
        if ($config.services.frontend.environment) {
            foreach ($prop in $config.services.frontend.environment.PSObject.Properties) {
                $FrontendEnv[$prop.Name] = $prop.Value
            }
        }

        $envMode = Get-EffectiveEnvValue "ENVIRONMENT"
        $cookieSecure = Get-EffectiveEnvValue "COOKIE_SECURE"
        $logJson = Get-EffectiveEnvValue "LOG_JSON"
        if ($envMode -eq "cloud" -and (Test-Truthy $cookieSecure) -and (Test-Truthy $logJson)) {
            Add-Check "Deployment config" "ok" "$DeploymentConfig sets ENVIRONMENT=cloud, COOKIE_SECURE=true, and LOG_JSON=true."
        } else {
            Add-Check "Deployment config" "error" "$DeploymentConfig must set ENVIRONMENT=cloud, COOKIE_SECURE=true, and LOG_JSON=true."
        }
    } catch {
        Add-Check "Deployment config" "error" $_.Exception.Message
    }
}

function Test-Truthy {
    param([string]$Value)
    return $Value -match "^(?i:true|1|yes|on)$"
}

function Test-Placeholder {
    param([string]$Value)
    return [string]::IsNullOrWhiteSpace($Value) -or $Value.StartsWith("CHANGE_ME") -or $Value.StartsWith("change-me")
}

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

function Test-LocalEndpointValue {
    param([string]$Value)
    if ([string]::IsNullOrWhiteSpace($Value)) {
        return $false
    }
    $normalized = $Value.Trim().ToLowerInvariant()
    $uri = $null
    if ([System.Uri]::TryCreate($normalized, [System.UriKind]::Absolute, [ref]$uri) -and $uri.Host) {
        return Test-LoopbackHost $uri.Host
    }
    if (Test-LoopbackHost $normalized) {
        return $true
    }
    return (
        $normalized.Contains("localhost") -or
        $normalized -match "127\.0\.0\.1" -or
        $normalized.Contains("::1")
    )
}

function Test-DomainHostname {
    param([string]$Value)
    if ([string]::IsNullOrWhiteSpace($Value)) {
        return $false
    }
    $candidate = $Value.Trim()
    if ($candidate.Length -gt 253 -or $candidate -match '[/:\\?#\s*]') {
        return $false
    }
    foreach ($label in ($candidate -split "\.")) {
        if (
            [string]::IsNullOrWhiteSpace($label) -or
            $label.Length -gt 63 -or
            $label -notmatch "^[A-Za-z0-9]([A-Za-z0-9-]*[A-Za-z0-9])?$"
        ) {
            return $false
        }
    }
    return $true
}

function Test-HttpsRootUrl {
    param([string]$Value)
    if ([string]::IsNullOrWhiteSpace($Value)) {
        return $false
    }

    $clean = $Value.Trim()
    $uri = $null
    if (
        -not [System.Uri]::TryCreate($clean, [System.UriKind]::Absolute, [ref]$uri) -or
        $uri.Scheme -ne "https" -or
        [string]::IsNullOrWhiteSpace($uri.Host) -or
        (Test-LoopbackHost $uri.Host) -or
        -not [string]::IsNullOrWhiteSpace($uri.UserInfo) -or
        $uri.AbsolutePath -ne "/" -or
        -not [string]::IsNullOrWhiteSpace($uri.Query) -or
        -not [string]::IsNullOrWhiteSpace($uri.Fragment)
    ) {
        return $false
    }
    return $true
}

function Get-PublicEndpointValue {
    param([string]$Name)
    if ($PublicEnv.ContainsKey($Name)) {
        return [string]$PublicEnv[$Name]
    }
    if ($FrontendEnv.ContainsKey($Name)) {
        return [string]$FrontendEnv[$Name]
    }
    return Get-EffectiveEnvValue $Name
}

function Add-PublicEndpointChecks {
    $domain = Get-PublicEndpointValue "DOMAIN"
    $publicUrl = Get-PublicEndpointValue "EDQ_PUBLIC_URL"

    if ($Production) {
        if (Test-Placeholder $domain) {
            Add-Check "Frontend domain" "error" "Production DOMAIN must be set to the real deployment hostname."
        } elseif (Test-LocalEndpointValue $domain) {
            Add-Check "Frontend domain" "error" "Production DOMAIN must be the real deployment hostname, not localhost."
        } elseif ($domain -match "^https?://") {
            Add-Check "Frontend domain" "error" "Production DOMAIN must be a hostname only, not a URL."
        } elseif (-not (Test-DomainHostname $domain)) {
            Add-Check "Frontend domain" "error" "Production DOMAIN must be a valid hostname without paths, ports, wildcards, or whitespace."
        } else {
            Add-Check "Frontend domain" "ok" "Production DOMAIN is set."
        }

        if (Test-Placeholder $publicUrl) {
            Add-Check "Public URL" "error" "Production EDQ_PUBLIC_URL must be set to the HTTPS deployment URL."
        } elseif (Test-LocalEndpointValue $publicUrl) {
            Add-Check "Public URL" "error" "Production EDQ_PUBLIC_URL must not point to localhost."
        } elseif (-not (Test-HttpsRootUrl $publicUrl)) {
            Add-Check "Public URL" "error" "Production EDQ_PUBLIC_URL must be an HTTPS origin without paths, query strings, or fragments."
        } else {
            Add-Check "Public URL" "ok" "Production EDQ_PUBLIC_URL is set."
        }
    } else {
        if (Test-Placeholder $domain) {
            Add-Check "Frontend domain" "warning" "DOMAIN is not set; pilot validation can continue for local-only testing."
        } elseif (Test-LocalEndpointValue $domain) {
            Add-Check "Frontend domain" "warning" "DOMAIN points to localhost; replace it before production sign-off."
        } else {
            Add-Check "Frontend domain" "ok" "DOMAIN is set."
        }

        if (Test-Placeholder $publicUrl) {
            Add-Check "Public URL" "warning" "EDQ_PUBLIC_URL is not set; scripts will use the local frontend port unless -BaseUrl is provided."
        } elseif (Test-LocalEndpointValue $publicUrl) {
            Add-Check "Public URL" "warning" "EDQ_PUBLIC_URL points to localhost; replace it before production sign-off."
        } else {
            Add-Check "Public URL" "ok" "EDQ_PUBLIC_URL is set."
        }
    }
}

function Get-CorsOriginValues {
    param([string]$Value)

    if ([string]::IsNullOrWhiteSpace($Value)) {
        return @()
    }

    $trimmed = $Value.Trim()
    try {
        $parsed = $trimmed | ConvertFrom-Json
        if ($parsed -is [System.Array]) {
            return @($parsed | ForEach-Object { [string]$_ })
        }
        if ($parsed) {
            return @([string]$parsed)
        }
    } catch {
        # Fall through to comma parsing for legacy env formats.
    }

    return @(
        $trimmed -split "," |
            ForEach-Object { $_.Trim().Trim("[", "]").Trim("'").Trim('"') } |
            Where-Object { $_ }
    )
}

function Get-InvalidProductionCorsOrigins {
    param([string[]]$Origins)

    $invalid = @()
    foreach ($origin in $Origins) {
        $clean = $origin.Trim()
        $uri = $null
        if (
            -not [System.Uri]::TryCreate($clean, [System.UriKind]::Absolute, [ref]$uri) -or
            $uri.Scheme -ne "https" -or
            [string]::IsNullOrWhiteSpace($uri.Host) -or
            (Test-LoopbackHost $uri.Host) -or
            -not [string]::IsNullOrWhiteSpace($uri.UserInfo) -or
            $clean -ne "$($uri.Scheme)://$($uri.Authority)"
        ) {
            $invalid += $origin
        }
    }
    return $invalid
}

function Resolve-EvidencePath {
    param([string]$Path)
    if (-not $Path) {
        return $null
    }
    if ([System.IO.Path]::IsPathRooted($Path)) {
        return $Path
    }
    return Join-Path $RepoRoot $Path
}

function Test-JsonEvidence {
    param([string]$Path)

    $resolved = Resolve-EvidencePath $Path
    if (-not $resolved -or -not (Test-Path $resolved)) {
        return $false
    }
    $evidence = Get-Content $resolved -Raw | ConvertFrom-Json
    if ($evidence.status -eq "ok" -and -not $evidence.checks) {
        return $true
    }
    if ($evidence -is [System.Array]) {
        $checks = @($evidence)
    } elseif ($evidence.PSObject.Properties["checks"]) {
        $checks = @($evidence.checks)
    } else {
        $checks = @($evidence)
    }
    $errorCount = @($checks | Where-Object { $_.status -eq "error" }).Count
    $warningCount = @($checks | Where-Object { $_.status -eq "warning" }).Count
    if ($checks.Count -gt 0 -and $errorCount -eq 0 -and $warningCount -eq 0) {
        return $true
    }
    return $false
}

function Add-RequiredSecretCheck {
    param(
        [string]$Name,
        [int]$MinLength = 1
    )
    $value = Get-EffectiveEnvValue $Name
    if (Test-Placeholder $value) {
        Add-Check $Name "error" "$Name is missing or still set to a placeholder."
        return
    }
    if ($value.Length -lt $MinLength) {
        Add-Check $Name "error" "$Name must be at least $MinLength characters."
        return
    }
    Add-Check $Name "ok" "$Name is set."
}

function Add-EvidenceGate {
    param(
        [string]$EnvName,
        [string]$Label
    )
    $value = Get-RootEnvValue $EnvName
    if (-not $value) {
        $value = [Environment]::GetEnvironmentVariable($EnvName)
    }
    if (Test-Truthy $value) {
        Add-Check $Label "ok" "$EnvName=true"
        return
    }
    if ($Production) {
        Add-Check $Label "error" "Set $EnvName=true only after evidence is recorded."
    } else {
        Add-Check $Label "warning" "Pilot gate: record evidence before wider production and set $EnvName=true."
    }
}

function Add-JsonEvidenceGate {
    param(
        [string]$EnvName,
        [string]$EvidenceEnvName,
        [string]$Label
    )
    $value = Get-RootEnvValue $EnvName
    if (-not $value) {
        $value = [Environment]::GetEnvironmentVariable($EnvName)
    }
    if (Test-Truthy $value) {
        Add-Check $Label "ok" "$EnvName=true"
        return
    }

    $evidencePath = Get-RootEnvValue $EvidenceEnvName
    if (-not $evidencePath) {
        $evidencePath = [Environment]::GetEnvironmentVariable($EvidenceEnvName)
    }
    if ($evidencePath -and (Test-JsonEvidence $evidencePath)) {
        Add-Check $Label "ok" "$EvidenceEnvName points to passing evidence."
        return
    }

    if ($Production) {
        Add-Check $Label "error" "Set $EnvName=true or $EvidenceEnvName to a passing JSON evidence file after evidence is recorded."
    } else {
        Add-Check $Label "warning" "Pilot gate: record evidence before wider production and set $EnvName=true or $EvidenceEnvName."
    }
}

function Invoke-GhJson {
    param([string[]]$Arguments)

    $output = & gh @Arguments 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw "gh $($Arguments -join ' ') failed."
    }
    if (-not $output) {
        return $null
    }
    return ($output | ConvertFrom-Json)
}

function Invoke-GhText {
    param([string[]]$Arguments)

    $output = & gh @Arguments 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw "gh $($Arguments -join ' ') failed."
    }
    return (($output -join "`n").Trim())
}

function Get-LatestWorkflowRun {
    param([string]$WorkflowName)

    $runs = @(
        Invoke-GhJson @(
            "run",
            "list",
            "--branch", "main",
            "--workflow", $WorkflowName,
            "--limit", "1",
            "--json", "workflowName,status,conclusion,createdAt"
        )
    )
    if ($runs.Count -lt 1) {
        return $null
    }
    return $runs[0]
}

function Add-GitHubSecurityGate {
    $confirmed = Get-RootEnvValue "EDQ_GITHUB_SECURITY_CONFIRMED"
    if (-not $confirmed) {
        $confirmed = [Environment]::GetEnvironmentVariable("EDQ_GITHUB_SECURITY_CONFIRMED")
    }

    if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
        if (Test-Truthy $confirmed) {
            Add-Check "GitHub CI/CodeQL/branch protection" "ok" "EDQ_GITHUB_SECURITY_CONFIRMED=true"
        } elseif ($Production) {
            Add-Check "GitHub CI/CodeQL/branch protection" "error" "Install gh or set EDQ_GITHUB_SECURITY_CONFIRMED=true after evidence is recorded."
        } else {
            Add-Check "GitHub CI/CodeQL/branch protection" "warning" "Install gh to verify GitHub security evidence automatically."
        }
        return
    }

    try {
        $repo = Invoke-GhText @("repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner")
        if (-not $repo) {
            throw "Could not resolve repository."
        }

        $protection = Invoke-GhJson @("api", "repos/$repo/branches/main/protection")
        $contexts = @($protection.required_status_checks.contexts)
        $requiredContexts = @("audit-report", "backend-verify", "frontend-verify", "docker-build", "container-scan")
        $missingContexts = @($requiredContexts | Where-Object { $contexts -notcontains $_ })
        if ($missingContexts.Count -gt 0) {
            throw "Branch protection is missing required check(s): $($missingContexts -join ', ')."
        }
        if (-not $protection.required_status_checks.strict) {
            throw "Branch protection does not require branches to be up to date."
        }
        if (-not $protection.required_linear_history.enabled -or $protection.allow_force_pushes.enabled -or $protection.allow_deletions.enabled) {
            throw "Branch protection does not enforce linear history, or allows force-push/delete."
        }

        foreach ($workflow in @("CI", "CodeQL", "Container Security")) {
            $latest = Get-LatestWorkflowRun $workflow
            if (-not $latest -or $latest.status -ne "completed" -or $latest.conclusion -ne "success") {
                throw "Latest $workflow run on main is not successful."
            }
        }

        $criticalCodeScanning = @(Invoke-GhJson @("api", "repos/$repo/code-scanning/alerts?state=open&severity=critical"))
        $highCodeScanning = @(Invoke-GhJson @("api", "repos/$repo/code-scanning/alerts?state=open&severity=high"))
        $dependabotAlerts = @(Invoke-GhJson @("api", "repos/$repo/dependabot/alerts?state=open"))
        $criticalHighDependabot = @(
            $dependabotAlerts | Where-Object {
                $_.security_vulnerability.severity -eq "critical" -or $_.security_vulnerability.severity -eq "high"
            }
        )
        if ($criticalCodeScanning.Count -gt 0 -or $highCodeScanning.Count -gt 0 -or $criticalHighDependabot.Count -gt 0) {
            throw "Open high/critical security alerts remain."
        }

        Add-Check "GitHub CI/CodeQL/branch protection" "ok" "main protection, latest CI/CodeQL/container scan, and high/critical alerts verified for $repo."
    } catch {
        if (Test-Truthy $confirmed) {
            Add-Check "GitHub CI/CodeQL/branch protection" "ok" "EDQ_GITHUB_SECURITY_CONFIRMED=true"
        } elseif ($Production) {
            Add-Check "GitHub CI/CodeQL/branch protection" "error" $_.Exception.Message
        } else {
            Add-Check "GitHub CI/CodeQL/branch protection" "warning" $_.Exception.Message
        }
    }
}

function Resolve-BaseUrl {
    if ($BaseUrl) {
        return $BaseUrl.TrimEnd("/")
    }
    if ($env:EDQ_URL) {
        return $env:EDQ_URL.TrimEnd("/")
    }
    if ($env:EDQ_PUBLIC_URL) {
        return $env:EDQ_PUBLIC_URL.TrimEnd("/")
    }
    $publicUrl = Get-RootEnvValue "EDQ_PUBLIC_URL"
    if ($publicUrl) {
        return $publicUrl.TrimEnd("/")
    }
    $publicPort = $env:EDQ_PUBLIC_PORT
    if (-not $publicPort) {
        $publicPort = Get-RootEnvValue "EDQ_PUBLIC_PORT"
    }
    if (-not $publicPort) {
        $publicPort = "3000"
    }
    return "http://localhost:$publicPort"
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

function Get-ProductionRuntimeTargetError {
    param([string]$Value)
    if ([string]::IsNullOrWhiteSpace($Value)) {
        return "Production runtime checks require an HTTPS deployment URL."
    }
    if (Test-LocalEndpointValue $Value) {
        return "Production runtime checks must target the real deployed URL, not localhost."
    }
    if (-not (Test-HttpsRootUrl $Value)) {
        return "Production runtime checks must target an HTTPS origin without paths, query strings, or fragments."
    }
    return $null
}

Push-Location $RepoRoot
try {
    $envFile = Join-Path $RepoRoot ".env"
    if (Test-Path $envFile) {
        Add-Check ".env" "ok" "Root .env exists."
    } else {
        Add-Check ".env" "error" "Root .env is required before release validation."
    }

    Add-DeploymentConfigChecks
    Add-PublicEndpointChecks

    if (-not $SkipGitChecks) {
        $branch = (git branch --show-current 2>$null)
        if ($LASTEXITCODE -ne 0 -or -not $branch) {
            Add-Check "Git branch" "error" "Could not read current Git branch."
        } elseif ($branch -eq "main") {
            Add-Check "Git branch" "ok" "On main."
        } elseif ($Production) {
            Add-Check "Git branch" "error" "Production release validation must run from main, not $branch."
        } else {
            Add-Check "Git branch" "warning" "Pilot validation is running from $branch."
        }

        $dirty = (git status --porcelain 2>$null)
        if ($LASTEXITCODE -ne 0) {
            Add-Check "Git cleanliness" "error" "Could not read Git status."
        } elseif ($dirty) {
            Add-Check "Git cleanliness" "error" "Working tree has uncommitted changes."
        } else {
            Add-Check "Git cleanliness" "ok" "Working tree is clean."
        }
    }

    Add-RequiredSecretCheck "JWT_SECRET" 32
    Add-RequiredSecretCheck "JWT_REFRESH_SECRET" 32
    Add-RequiredSecretCheck "SECRET_KEY" 32
    Add-RequiredSecretCheck "TOOLS_API_KEY" 32
    Add-RequiredSecretCheck "INITIAL_ADMIN_PASSWORD" 1
    Add-RequiredSecretCheck "POSTGRES_PASSWORD" 1

    $jwtSecret = Get-EffectiveEnvValue "JWT_SECRET"
    $jwtRefreshSecret = Get-EffectiveEnvValue "JWT_REFRESH_SECRET"
    if ($jwtSecret -and $jwtRefreshSecret -and $jwtSecret -eq $jwtRefreshSecret) {
        Add-Check "JWT secret separation" "error" "JWT_SECRET and JWT_REFRESH_SECRET must be different."
    } else {
        Add-Check "JWT secret separation" "ok" "JWT signing secrets are distinct."
    }

    $environment = Get-EffectiveEnvValue "ENVIRONMENT"
    $cookieSecure = Get-EffectiveEnvValue "COOKIE_SECURE"
    $debug = Get-EffectiveEnvValue "DEBUG"
    $cors = Get-EffectiveEnvValue "CORS_ORIGINS"
    $corsOrigins = @(Get-CorsOriginValues $cors)
    $invalidProductionCorsOrigins = @(
        if ($Production) { Get-InvalidProductionCorsOrigins $corsOrigins }
    )

    if ($Production -and $environment -ne "cloud" -and -not (Test-Truthy $cookieSecure)) {
        Add-Check "Secure cookies" "error" "Production needs ENVIRONMENT=cloud or COOKIE_SECURE=true."
    } else {
        Add-Check "Secure cookies" "ok" "Cookie security mode is acceptable for $Mode."
    }

    if ($Production -and (Test-Truthy $debug)) {
        Add-Check "DEBUG" "error" "DEBUG must be false in production."
    } else {
        Add-Check "DEBUG" "ok" "DEBUG is not enabled for this gate."
    }

    if ($Production -and $corsOrigins.Count -eq 0) {
        Add-Check "CORS origins" "error" "Production CORS_ORIGINS must be set."
    } elseif ($Production -and @($corsOrigins | Where-Object { $_.Trim() -eq "*" }).Count -gt 0) {
        Add-Check "CORS origins" "error" "Production CORS_ORIGINS must list explicit origins, not wildcard values."
    } elseif ($Production -and (Test-LocalEndpointValue $cors)) {
        Add-Check "CORS origins" "error" "Production CORS_ORIGINS must not include localhost."
    } elseif ($Production -and $invalidProductionCorsOrigins.Count -gt 0) {
        Add-Check "CORS origins" "error" "Production CORS_ORIGINS must contain only explicit https origins without paths: $($invalidProductionCorsOrigins -join ', ')."
    } elseif (-not $cors) {
        Add-Check "CORS origins" "warning" "CORS_ORIGINS is empty or missing."
    } else {
        Add-Check "CORS origins" "ok" "CORS_ORIGINS is configured."
    }

    $sentry = Get-EffectiveEnvValue "SENTRY_DSN"
    $monitoringConfirmed = Get-RootEnvValue "EDQ_MONITORING_CONFIRMED"
    if (-not $monitoringConfirmed) {
        $monitoringConfirmed = [Environment]::GetEnvironmentVariable("EDQ_MONITORING_CONFIRMED")
    }
    $monitoringEvidence = Get-RootEnvValue "EDQ_MONITORING_EVIDENCE"
    if (-not $monitoringEvidence) {
        $monitoringEvidence = [Environment]::GetEnvironmentVariable("EDQ_MONITORING_EVIDENCE")
    }
    if ($sentry -or (Test-Truthy $monitoringConfirmed)) {
        Add-Check "Monitoring" "ok" "Monitoring is configured or externally confirmed."
    } elseif ($monitoringEvidence -and (Test-JsonEvidence $monitoringEvidence)) {
        Add-Check "Monitoring" "ok" "EDQ_MONITORING_EVIDENCE points to passing evidence."
    } elseif ($Production) {
        Add-Check "Monitoring" "error" "Configure Sentry/log alerts, set EDQ_MONITORING_CONFIRMED=true, or set EDQ_MONITORING_EVIDENCE to passing JSON evidence."
    } else {
        Add-Check "Monitoring" "warning" "Monitoring evidence is still required before wider production."
    }

    Add-JsonEvidenceGate "EDQ_BACKUP_RESTORE_DRILL_CONFIRMED" "EDQ_BACKUP_RESTORE_DRILL_EVIDENCE" "Backup restore drill"
    Add-JsonEvidenceGate "EDQ_SCAN_GOVERNANCE_CONFIRMED" "EDQ_SCAN_GOVERNANCE_EVIDENCE" "Scanner governance review"
    Add-JsonEvidenceGate "EDQ_REAL_DEVICE_PILOT_CONFIRMED" "EDQ_REAL_DEVICE_PILOT_EVIDENCE" "Real-device pilot"
    Add-GitHubSecurityGate

    if (-not $SkipRuntimeChecks) {
        $resolvedBaseUrl = Resolve-BaseUrl
        $apiUrl = "$($resolvedBaseUrl.TrimEnd('/'))/api"
        $session = New-Object Microsoft.PowerShell.Commands.WebRequestSession
        $runtimeTargetError = if ($Production) { Get-ProductionRuntimeTargetError $resolvedBaseUrl } else { $null }

        if ($runtimeTargetError) {
            Add-Check "Runtime target" "error" $runtimeTargetError
        } else {
            if ($Production) {
                Add-Check "Runtime target" "ok" "Production runtime checks target $resolvedBaseUrl."
            }

            try {
                $health = Invoke-RestMethod -Uri "$apiUrl/health" -Method Get -TimeoutSec 10
                if ($health.status -eq "ok") {
                    Add-Check "Runtime health" "ok" "API health is ok at $resolvedBaseUrl."
                } else {
                    Add-Check "Runtime health" "error" "API health status is $($health.status)."
                }
            } catch {
                Add-Check "Runtime health" "error" "Could not reach $apiUrl/health: $($_.Exception.Message)"
            }

            $password = Resolve-AdminPassword
            if (Test-Placeholder $password) {
                Add-Check "Runtime auth" "error" "Set -AdminPass, EDQ_ADMIN_PASS, or INITIAL_ADMIN_PASSWORD."
            } else {
                try {
                    $payload = @{ username = $AdminUser; password = $password } | ConvertTo-Json -Compress
                    $login = Invoke-RestMethod -Uri "$apiUrl/auth/login" -Method Post -ContentType "application/json" -Body $payload -WebSession $session -TimeoutSec 10
                    if ($login.csrf_token) {
                        Add-Check "Runtime auth" "ok" "Admin login succeeded."
                    } else {
                        Add-Check "Runtime auth" "error" "Admin login response did not include csrf_token."
                    }
                } catch {
                    Add-Check "Runtime auth" "error" "Admin login failed: $($_.Exception.Message)"
                }
            }

            try {
                $networks = Invoke-RestMethod -Uri "$apiUrl/authorized-networks/?active_only=true" -Method Get -WebSession $session -TimeoutSec 10
                $count = @($networks).Count
                $legacyAuto = @($networks | Where-Object { [string]$_.label -match "Auto-authorized" })
                if ($count -gt 0) {
                    if ($legacyAuto.Count -gt 0) {
                        Add-Check "Authorized networks" "error" "$($legacyAuto.Count) active legacy auto-authorized range(s) require review or deactivation."
                    } else {
                        Add-Check "Authorized networks" "ok" "$count active authorized range(s) configured."
                    }
                } elseif ($Production) {
                    Add-Check "Authorized networks" "error" "At least one active authorized range is required before scan work."
                } else {
                    Add-Check "Authorized networks" "warning" "No active authorized ranges are configured yet. Add approved CIDRs before pilot scan work."
                }
            } catch {
                Add-Check "Authorized networks" "error" "Could not read authorized networks: $($_.Exception.Message)"
            }
        }
    }
} finally {
    Pop-Location
}

if ($Json) {
    $Checks | ConvertTo-Json -Depth 4
} else {
    Write-Host ""
    Write-Host "EDQ production gate ($Mode)"
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
