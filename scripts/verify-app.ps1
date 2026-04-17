param(
    [string]$BaseUrl = "",
    [string]$AdminUser = "admin",
    [string]$AdminPass = ""
)

$ErrorActionPreference = "Stop"

$script:Pass = 0
$script:Fail = 0
$script:Skip = 0

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$session = New-Object Microsoft.PowerShell.Commands.WebRequestSession

function Get-RootEnvValue {
    param([string]$Name)

    $envFile = Join-Path $repoRoot ".env"
    if (-not (Test-Path $envFile)) {
        return $null
    }

    $line = Get-Content $envFile | Where-Object { $_ -match "^$([regex]::Escape($Name))=" } | Select-Object -First 1
    if (-not $line) {
        return $null
    }

    $value = ($line -split "=", 2)[1].Trim()
    $value = $value.Trim("'")
    $value = $value.Trim('"')
    return $value
}

function Resolve-BaseUrl {
    if ($BaseUrl) {
        return $BaseUrl.TrimEnd('/')
    }

    if ($env:EDQ_URL) {
        return $env:EDQ_URL.TrimEnd('/')
    }

    if ($env:EDQ_PUBLIC_URL) {
        return $env:EDQ_PUBLIC_URL.TrimEnd('/')
    }

    $publicUrl = Get-RootEnvValue "EDQ_PUBLIC_URL"
    if ($publicUrl) {
        return $publicUrl.TrimEnd('/')
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

$resolvedBaseUrl = Resolve-BaseUrl
$apiUrl = "$($resolvedBaseUrl.TrimEnd('/'))/api"
$frontendUrl = $resolvedBaseUrl.TrimEnd('/') + "/"

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
        # Check-body can opt into a "skip" outcome by returning/throwing a
        # string prefixed with "SKIP:". Used for preconditions that are
        # legitimately absent on a fresh install (e.g. no test runs yet
        # to exercise the WebSocket).
        if ($result -is [string] -and $result.StartsWith("SKIP:")) {
            $reason = $result.Substring(5).TrimStart()
            Write-Host ("SKIP {0}" -f $reason) -ForegroundColor Yellow
            $script:Skip++
            return
        }
        Write-Host ("OK  {0}" -f $result) -ForegroundColor Green
        $script:Pass++
    } catch {
        $msg = if ($_.Exception.Message) { $_.Exception.Message } else { "" }
        if ($msg.StartsWith("SKIP:")) {
            $reason = $msg.Substring(5).TrimStart()
            Write-Host ("SKIP {0}" -f $reason) -ForegroundColor Yellow
            $script:Skip++
            return
        }
        Write-Host "FAIL" -ForegroundColor Red
        if ($msg) {
            Write-Host ("      {0}" -f $msg) -ForegroundColor DarkGray
        }
        $script:Fail++
    }
}

function Convert-ToWebSocketUrl {
    param([string]$Url)

    if ($Url.StartsWith("https://")) {
        return "wss://" + $Url.Substring(8).TrimEnd('/')
    }
    if ($Url.StartsWith("http://")) {
        return "ws://" + $Url.Substring(7).TrimEnd('/')
    }
    throw "Unsupported base URL for WebSocket conversion: $Url"
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
Write-Host ("Target: {0}" -f $resolvedBaseUrl)
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
Invoke-Check "WebSocket upgrade" {
    $loginPayload = @{ username = $AdminUser; password = $resolvedPassword } | ConvertTo-Json -Compress
    $loginResponse = Invoke-RestMethod -Uri "$apiUrl/auth/login" -Method Post -ContentType "application/json" -Body $loginPayload -WebSession $session
    if (-not $loginResponse.csrf_token) {
        throw "Missing csrf token after websocket login."
    }

    $wsCookie = $session.Cookies.GetCookies($resolvedBaseUrl)["edq_session"]
    if (-not $wsCookie -or -not $wsCookie.Value) {
        throw "Missing edq_session cookie for websocket verification."
    }

    $runsResponse = Invoke-RestMethod -Uri "$apiUrl/test-runs/" -Method Get -WebSession $session
    $runs = @($runsResponse)
    if (-not $runs -or $runs.Count -eq 0) {
        # Fresh install has no runs yet — not a failure, just nothing to
        # exercise. The WebSocket server itself is reachable (backend is
        # healthy); this check revisits once the first test run exists.
        return "SKIP: no test runs yet (create one, then re-run verify)"
    }

    $runId = [string]$runs[0].id
    $wsUrl = "$(Convert-ToWebSocketUrl $resolvedBaseUrl)/api/ws/test-run/$runId"

    $socket = [System.Net.WebSockets.ClientWebSocket]::new()
    try {
        $socket.Options.SetRequestHeader("Origin", $resolvedBaseUrl.TrimEnd('/'))
        $socket.Options.SetRequestHeader("Cookie", "edq_session=$($wsCookie.Value)")
        $socket.ConnectAsync([Uri]$wsUrl, [Threading.CancellationToken]::None).GetAwaiter().GetResult()
        if ($socket.State -ne [System.Net.WebSockets.WebSocketState]::Open) {
            throw "WebSocket did not open."
        }
        "connected to run $runId"
    }
    finally {
        if ($socket.State -eq [System.Net.WebSockets.WebSocketState]::Open) {
            $socket.CloseAsync([System.Net.WebSockets.WebSocketCloseStatus]::NormalClosure, "verify", [Threading.CancellationToken]::None).GetAwaiter().GetResult()
        }
        $socket.Dispose()
    }
}

Write-Host ""
Write-Host "====================================="
Write-Host ("  Results: {0} passed, {1} failed, {2} skipped" -f $script:Pass, $script:Fail, $script:Skip)
Write-Host "====================================="
Write-Host ""

if ($script:Fail -gt 0) {
    exit 1
}
