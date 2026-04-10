param(
    [string]$BaseUrl = "http://localhost:3000",
    [string]$AdminUser = "admin",
    [string]$AdminPass = ""
)

$ErrorActionPreference = "Stop"

$script:Pass = 0
$script:Fail = 0
$script:Skip = 0

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$apiUrl = "$($BaseUrl.TrimEnd('/'))/api"
$session = New-Object Microsoft.PowerShell.Commands.WebRequestSession
$csrfToken = ""
$createdDeviceId = ""
$randomSuffix = Get-Random -Minimum 100 -Maximum 255
$deviceIp = "10.99.99.$randomSuffix"
$deviceMac = "AA:BB:CC:DD:EE:{0:X2}" -f (Get-Random -Minimum 16 -Maximum 254)

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

function Get-StatusCode {
    param(
        [string]$Uri,
        [string]$Method = "GET",
        [hashtable]$Headers = @{},
        [string]$Body = "",
        [Microsoft.PowerShell.Commands.WebRequestSession]$WebSession = $null
    )

    try {
        $invokeParams = @{
            Uri         = $Uri
            Method      = $Method
            Headers     = $Headers
            ErrorAction = "Stop"
        }
        if ($WebSession) { $invokeParams.WebSession = $WebSession }
        if ($Body) {
            $invokeParams.Body = $Body
            $invokeParams.ContentType = "application/json"
        }
        $response = Invoke-WebRequest @invokeParams
        return [int]$response.StatusCode
    } catch {
        if ($_.Exception.Response) {
            return [int]$_.Exception.Response.StatusCode.value__
        }
        throw
    }
}

function Invoke-Check {
    param(
        [string]$Label,
        [scriptblock]$Body
    )

    Write-Host ("  {0,-40} " -f $Label) -NoNewline
    try {
        $result = & $Body
        Write-Host ("PASS  {0}" -f $result) -ForegroundColor Green
        $script:Pass++
    } catch {
        Write-Host "FAIL" -ForegroundColor Red
        if ($_.Exception.Message) {
            Write-Host ("      {0}" -f $_.Exception.Message) -ForegroundColor DarkGray
        }
        $script:Fail++
    }
}

function Get-PropertyCount {
    param([object]$Value)

    if ($null -eq $Value) { return 0 }
    if ($Value -is [System.Collections.IDictionary]) { return $Value.Count }
    return @($Value.PSObject.Properties | Where-Object { $_.MemberType -eq "NoteProperty" }).Count
}

function Get-CsrfHeaders {
    if (-not $csrfToken) {
        return @{}
    }
    return @{ "X-CSRF-Token" = $csrfToken }
}

$resolvedPassword = Resolve-AdminPassword
if (-not $resolvedPassword -or $resolvedPassword.StartsWith("CHANGE_ME") -or $resolvedPassword.StartsWith("change-me")) {
    throw "Admin password is still a placeholder. Update the root .env file first."
}

Write-Host ""
Write-Host "====================================="
Write-Host "  EDQ API Regression Script"
Write-Host "====================================="
Write-Host ("Target: {0}" -f $BaseUrl)
Write-Host ("Date:   {0}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"))
Write-Host ""

Write-Host "--- Infrastructure Health ---"
Invoke-Check "Health endpoint returns status" {
    $response = Invoke-RestMethod -Uri "$apiUrl/health" -Method Get
    if (-not $response.status -or -not $response.database) {
        throw "Missing health fields."
    }
    "status=$($response.status) database=$($response.database)"
}

Invoke-Check "Tool versions requires auth" {
    $status = Get-StatusCode -Uri "$apiUrl/health/tools/versions"
    if ($status -ne 401) {
        throw "Expected 401, got $status"
    }
    "HTTP 401"
}

Write-Host ""
Write-Host "--- Authentication ---"
Invoke-Check "Login as admin" {
    $payload = @{ username = $AdminUser; password = $resolvedPassword } | ConvertTo-Json -Compress
    $response = Invoke-RestMethod -Uri "$apiUrl/auth/login" -Method Post -ContentType "application/json" -Body $payload -WebSession $session
    if (-not $response.csrf_token) {
        throw "Missing csrf_token in login response."
    }
    $script:csrfToken = $response.csrf_token
    $response.message
}

Invoke-Check "Current user uses username auth" {
    $response = Invoke-RestMethod -Uri "$apiUrl/auth/me" -Method Get -WebSession $session
    if ($response.username -ne $AdminUser) {
        throw "Expected username $AdminUser, got $($response.username)"
    }
    $response.username
}

Invoke-Check "Authenticated tool versions" {
    $response = Invoke-RestMethod -Uri "$apiUrl/health/tools/versions" -Method Get -WebSession $session
    $toolCount = Get-PropertyCount $response.tools
    "{0} tools" -f $toolCount
}

Write-Host ""
Write-Host "--- API Regression ---"
Invoke-Check "List test templates" {
    $response = Invoke-RestMethod -Uri "$apiUrl/test-templates/" -Method Get -WebSession $session
    $count = @($response).Count
    if ($count -lt 1) {
        throw "Expected at least one template."
    }
    "{0} templates" -f $count
}

Invoke-Check "Create device" {
    $payload = @{
        ip_address   = $deviceIp
        mac_address  = $deviceMac
        hostname     = "PowerShell E2E Device"
        category     = "camera"
        manufacturer = "EDQ"
        model        = "Smoke"
    } | ConvertTo-Json -Compress
    $response = Invoke-RestMethod -Uri "$apiUrl/devices/" -Method Post -ContentType "application/json" -Body $payload -Headers (Get-CsrfHeaders) -WebSession $session
    if (-not $response.id) {
        throw "Missing device ID."
    }
    $script:createdDeviceId = $response.id
    $response.ip_address
}

Invoke-Check "Get device detail" {
    if (-not $createdDeviceId) { throw "No device created." }
    $response = Invoke-RestMethod -Uri "$apiUrl/devices/$createdDeviceId" -Method Get -WebSession $session
    if ($response.ip_address -ne $deviceIp) {
        throw "Device detail mismatch."
    }
    $response.hostname
}

Invoke-Check "Update device metadata" {
    if (-not $createdDeviceId) { throw "No device created." }
    $payload = @{ firmware_version = "2.0.1" } | ConvertTo-Json -Compress
    $response = Invoke-RestMethod -Uri "$apiUrl/devices/$createdDeviceId" -Method Patch -ContentType "application/json" -Body $payload -Headers (Get-CsrfHeaders) -WebSession $session
    if ($response.firmware_version -ne "2.0.1") {
        throw "Firmware version update failed."
    }
    $response.firmware_version
}

Invoke-Check "Delete device" {
    if (-not $createdDeviceId) { throw "No device created." }
    $cookieHeader = (($session.Cookies.GetCookies($apiUrl) | ForEach-Object { "{0}={1}" -f $_.Name, $_.Value }) -join "; ")
    $status = (& curl.exe -s -o NUL -w "%{http_code}" -X DELETE -H ("X-CSRF-Token: " + $csrfToken) -H ("Cookie: " + $cookieHeader) "$apiUrl/devices/$createdDeviceId")
    if ($LASTEXITCODE -ne 0) {
        throw "curl.exe delete request failed."
    }
    if ($status -ne "204") {
        throw "Expected 204, got $status"
    }
    $script:createdDeviceId = ""
    "HTTP 204"
}

Write-Host ""
Write-Host "====================================="
Write-Host ("  Results: {0} passed, {1} failed, {2} skipped" -f $script:Pass, $script:Fail, $script:Skip)
Write-Host "====================================="
Write-Host ""

if ($script:Fail -gt 0) {
    exit 1
}
