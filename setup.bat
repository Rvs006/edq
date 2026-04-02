@echo off
setlocal
cd /d "%~dp0"

echo === EDQ Setup ===

if not exist .env (
  copy .env.example .env >nul
  echo Created root .env from .env.example
)

set "ADMIN_PASS="
for /f "usebackq delims=" %%A in (`powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$chars = (48..57) + (65..90) + (97..122); " ^
  "$makeHex = { param([int]$len) -join ((1..$len) | ForEach-Object { '{0:x}' -f (Get-Random -Max 16) }) }; " ^
  "$makePassword = { -join ((1..20) | ForEach-Object { [char]($chars | Get-Random) }) }; " ^
  "$content = Get-Content '.env' -Raw; " ^
  "$updates = @(@{Key='JWT_SECRET';Value=(& $makeHex 128)}, @{Key='JWT_REFRESH_SECRET';Value=(& $makeHex 128)}, @{Key='SECRET_KEY';Value=(& $makeHex 64)}, @{Key='TOOLS_API_KEY';Value=(& $makeHex 64)}, @{Key='INITIAL_ADMIN_PASSWORD';Value=(& $makePassword)}); " ^
  "$generatedAdmin = ''; " ^
  "foreach ($item in $updates) { " ^
  "  $pattern = '(?m)^' + [regex]::Escape($item.Key) + '=(.*)$'; " ^
  "  $match = [regex]::Match($content, $pattern); " ^
  "  if (-not $match.Success) { " ^
  "    $content += [Environment]::NewLine + ($item.Key + '=' + $item.Value); " ^
  "    if ($item.Key -eq 'INITIAL_ADMIN_PASSWORD') { $generatedAdmin = $item.Value } " ^
  "    continue " ^
  "  } " ^
  "  if ([string]::IsNullOrWhiteSpace($match.Groups[1].Value) -or $match.Groups[1].Value.StartsWith('CHANGE_ME') -or $match.Groups[1].Value.StartsWith('change-me')) { " ^
  "    $content = [regex]::Replace($content, $pattern, ($item.Key + '=' + $item.Value)); " ^
  "    if ($item.Key -eq 'INITIAL_ADMIN_PASSWORD') { $generatedAdmin = $item.Value } " ^
  "  } " ^
  "} " ^
  "Set-Content '.env' $content -Encoding ASCII; " ^
  "Write-Output $generatedAdmin"`) do set "ADMIN_PASS=%%A"

if not exist data (
  mkdir data
)

echo Starting EDQ...
docker compose up --build -d

echo.
echo Waiting for services to start...
set "READY=0"
for /L %%I in (1,1,30) do (
  docker compose exec -T backend curl -sf http://localhost:8000/api/health >nul 2>nul
  if not errorlevel 1 (
    set "READY=1"
    goto :ready
  )
  timeout /t 2 /nobreak >nul
)

:ready
if "%READY%"=="0" (
  echo WARNING: Backend did not become healthy within timeout. Check logs with: docker compose logs backend
)

echo.
echo === EDQ is running at http://localhost ===
echo   Login: username 'admin' / password from INITIAL_ADMIN_PASSWORD in the root .env file
if not "%ADMIN_PASS%"=="" echo   Generated initial admin password: %ADMIN_PASS%
echo   (Change your password after first login)
echo.
echo Useful commands:
echo   docker compose logs -f        View live logs
echo   docker compose down           Stop EDQ
echo   docker compose down -v        Stop EDQ and remove data

endlocal
