param(
    [string]$BaseUrl = "http://localhost",
    [string]$AdminUser = "admin",
    [string]$AdminPass = ""
)

$ErrorActionPreference = "Stop"

$script:Pass = 0
$script:Fail = 0
$script:Skip = 0

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$apiUrl = "$($BaseUrl.TrimEnd('/'))/api"
$frontendUrl = $BaseUrl.TrimEnd('/') + "/"
$session = New-Object Microsoft.PowerShell.Commands.WebRequestSession

function Resolve-AdminPassword {
    if ($AdminPass) {
        return $AdminPass
    }

    if ($env:EDQ_ADMIN_PASS) {
        return $env:EDQ_ADMIN_PASS
    }

    $envFile = Join-Path $repoRoot ".env"
    if (Test-Path $envFile) {
        $line = Get-Content $envFile | Where-Object { $_ -match "^INITIAL_ADMIN_PASSWORD=" } | Select-Object -First 1
        if ($line) {
            return ($line -split "=", 2)[1].Trim()
        }
    }

    throw "Set -AdminPass, EDQ_ADMIN_PASS, or INITIAL_ADMIN_PASSWORD in the root .env file."
}

function Get-ListCount {
    param([object]$Value)

    if ($null -eq $Value) { return 0 }
    if ($Value -is [string]) { return 0 }
    if ($Value -is [System.Array]) { return $Value.Count }
    if ($Value.PSObject.Properties["items"]) { return @($Value.items).Count }
    if ($Value.PSObject.Properties["total"]) { return [int]$Value.total }
    return @($Value).Count
}

function Get-PropertyCount {
    param([object]$Value)

    if ($null -eq $Value) { return 0 }
    if ($Value -is [System.Collections.IDictionary]) { return $Value.Count }
    return @($Value.PSObject.Properties | Where-Object { $_.MemberType -eq "NoteProperty" }).Count
}

function Invoke-Check {
    param(
        [string]$Label,
        [scriptblock]$Body
    )

    Write-Host ("  {0,-35} " -f $Label) -NoNewline
    try {
        $result = & $Body
        Write-Host ("OK  {0}" -f $result) -ForegroundColor Green
        $script:Pass++
    } catch {
        Write-Host "FAIL" -ForegroundColor Red
        if ($_.Exception.Message) {
            Write-Host ("      {0}" -f $_.Exception.Message) -ForegroundColor DarkGray
        }
        $script:Fail++
    }
}

$resolvedPassword = Resolve-AdminPassword
if (-not $resolvedPassword -or $resolvedPassword.StartsWith("CHANGE_ME") -or $resolvedPassword.StartsWith("change-me")) {
    throw "Admin password is still a placeholder. Update the root .env file first."
}

Write-Host ""
Write-Host "====================================="
Write-Host "  EDQ Integration Verification"
Write-Host "====================================="
Write-Host ""
Write-Host ("Target: {0}" -f $BaseUrl)
Write-Host ""

Write-Host "--- Backend Health ---"
Invoke-Check "API health" {
    $response = Invoke-RestMethod -Uri "$apiUrl/health" -Method Get
    if ($response.status -ne "ok") {
        throw "Expected status=ok, got $($response.status)"
    }
    $response.status
}

Write-Host ""
Write-Host "--- Authentication ---"
Invoke-Check "Login (admin)" {
    $payload = @{ username = $AdminUser; password = $resolvedPassword } | ConvertTo-Json -Compress
    $response = Invoke-RestMethod -Uri "$apiUrl/auth/login" -Method Post -ContentType "application/json" -Body $payload -WebSession $session
    if (-not $response.csrf_token) {
        throw "Missing csrf_token in login response."
    }
    "token received"
}

Invoke-Check "Get current user" {
    $response = Invoke-RestMethod -Uri "$apiUrl/auth/me" -Method Get -WebSession $session
    if ($response.username -ne $AdminUser) {
        throw "Expected username $AdminUser, got $($response.username)"
    }
    $response.username
}

Write-Host ""
Write-Host "--- Core Resources ---"
Invoke-Check "List devices" {
    $response = Invoke-RestMethod -Uri "$apiUrl/devices/" -Method Get -WebSession $session
    "{0} devices" -f (Get-ListCount $response)
}

Invoke-Check "List test runs" {
    $response = Invoke-RestMethod -Uri "$apiUrl/test-runs/" -Method Get -WebSession $session
    "{0} runs" -f (Get-ListCount $response)
}

Invoke-Check "List templates" {
    $response = Invoke-RestMethod -Uri "$apiUrl/test-templates/" -Method Get -WebSession $session
    "{0} templates" -f (Get-ListCount $response)
}

Invoke-Check "List whitelists" {
    $response = Invoke-RestMethod -Uri "$apiUrl/whitelists/" -Method Get -WebSession $session
    "{0} whitelists" -f (Get-ListCount $response)
}

Write-Host ""
Write-Host "--- Tools Sidecar ---"
Invoke-Check "Tool versions" {
    $response = Invoke-RestMethod -Uri "$apiUrl/health/tools/versions" -Method Get -WebSession $session
    $toolCount = Get-PropertyCount $response.tools
    "{0} tools" -f $toolCount
}

Write-Host ""
Write-Host "--- Frontend ---"
Invoke-Check "Frontend serves HTML" {
    $content = ((& curl.exe -fsSL $frontendUrl) -join [Environment]::NewLine)
    if ($LASTEXITCODE -ne 0) {
        throw "curl.exe could not fetch the frontend."
    }
    if ($content -notmatch "(?i)edq|device qualifier") {
        throw "Expected EDQ HTML markers."
    }
    "HTML OK"
}

Invoke-Check "Static assets (JS)" {
    $content = ((& curl.exe -fsSL $frontendUrl) -join [Environment]::NewLine)
    if ($LASTEXITCODE -ne 0) {
        throw "curl.exe could not fetch the frontend."
    }
    $match = [regex]::Match($content, 'src="([^"]+\.js)"')
    if (-not $match.Success) {
        throw "No JS bundle reference found."
    }
    "JS bundle linked"
}

Write-Host ""
Write-Host "--- WebSocket ---"
Write-Host ("  {0,-35} SKIP  {1}" -f "WebSocket upgrade", "Requires manual or dedicated WS tooling") -ForegroundColor Yellow
$script:Skip++

Write-Host ""
Write-Host "====================================="
Write-Host ("  Results: {0} passed, {1} failed, {2} skipped" -f $script:Pass, $script:Fail, $script:Skip)
Write-Host "====================================="
Write-Host ""

if ($script:Fail -gt 0) {
    exit 1
}
