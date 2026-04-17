@echo off
setlocal
cd /d "%~dp0"

echo === EDQ Setup ===

if not exist .env (
  copy .env.example .env >nul
  echo Created root .env from .env.example
)

set "ADMIN_PASS="
set "PUBLIC_PORT=3000"
for /f "usebackq delims=" %%A in (`powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$chars = (48..57) + (65..90) + (97..122); " ^
  "$makeHex = { param([int]$len) -join ((1..$len) | ForEach-Object { '{0:x}' -f (Get-Random -Max 16) }) }; " ^
  "$makePassword = { -join ((1..20) | ForEach-Object { [char]($chars | Get-Random) }) }; " ^
  "$content = Get-Content '.env' -Raw; " ^
  "$updates = @(@{Key='JWT_SECRET';Value=(& $makeHex 128)}, @{Key='JWT_REFRESH_SECRET';Value=(& $makeHex 128)}, @{Key='SECRET_KEY';Value=(& $makeHex 64)}, @{Key='TOOLS_API_KEY';Value=(& $makeHex 64)}, @{Key='POSTGRES_PASSWORD';Value=(& $makeHex 48)}, @{Key='INITIAL_ADMIN_PASSWORD';Value=(& $makePassword)}); " ^
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
  "$postgresPassword = ([regex]::Match($content, '(?m)^POSTGRES_PASSWORD=(.*)$').Groups[1].Value).Trim(); " ^
  "$defaults = @(@{Key='DB_DRIVER';Value='postgresql+asyncpg'}, @{Key='DB_HOST';Value='127.0.0.1'}, @{Key='DB_PORT';Value='55432'}, @{Key='DB_NAME';Value='edq'}, @{Key='DB_USER';Value='edq'}, @{Key='DB_PASSWORD';Value=$postgresPassword}, @{Key='DB_CONNECT_TIMEOUT_SECONDS';Value='15'}, @{Key='EDQ_BACKEND_BIND_HOST';Value='127.0.0.1'}, @{Key='EDQ_BACKEND_PORT';Value='8000'}, @{Key='EDQ_TOOLS_BIND_HOST';Value='127.0.0.1'}, @{Key='EDQ_TOOLS_PORT';Value='8001'}, @{Key='EDQ_POSTGRES_BIND_HOST';Value='127.0.0.1'}, @{Key='EDQ_POSTGRES_PORT';Value='55432'}, @{Key='VITE_API_URL';Value='/api'}, @{Key='VITE_CLIENT_ERROR_ENDPOINT';Value='/api/client-errors'}, @{Key='VITE_SENTRY_ENABLED';Value='false'}, @{Key='VITE_SENTRY_TRACES_SAMPLE_RATE';Value='0.0'}, @{Key='VITE_SOURCEMAP';Value='false'}, @{Key='LOG_JSON';Value='false'}); " ^
  "foreach ($item in $defaults) { " ^
  "  $pattern = '(?m)^' + [regex]::Escape($item.Key) + '=(.*)$'; " ^
  "  $match = [regex]::Match($content, $pattern); " ^
  "  if (-not $match.Success) { $content += [Environment]::NewLine + ($item.Key + '=' + $item.Value); continue } " ^
  "  if ([string]::IsNullOrWhiteSpace($match.Groups[1].Value) -or $match.Groups[1].Value.StartsWith('CHANGE_ME') -or $match.Groups[1].Value.StartsWith('change-me')) { " ^
  "    $content = [regex]::Replace($content, $pattern, ($item.Key + '=' + $item.Value)); " ^
  "  } " ^
  "} " ^
  "$dbUrlPattern = '(?m)^DATABASE_URL=(.*)$'; " ^
  "$dbUrlMatch = [regex]::Match($content, $dbUrlPattern); " ^
  "if (-not $dbUrlMatch.Success) { $content += [Environment]::NewLine + 'DATABASE_URL=' } " ^
  "elseif ([string]::IsNullOrWhiteSpace($dbUrlMatch.Groups[1].Value) -or $dbUrlMatch.Groups[1].Value.StartsWith('CHANGE_ME') -or $dbUrlMatch.Groups[1].Value.StartsWith('change-me') -or $dbUrlMatch.Groups[1].Value -match 'sqlite') { " ^
  "  $content = [regex]::Replace($content, $dbUrlPattern, 'DATABASE_URL='); " ^
  "} " ^
  "Set-Content '.env' $content -Encoding ASCII; " ^
  "Write-Output $generatedAdmin"`) do set "ADMIN_PASS=%%A"
for /f "tokens=1,* delims==" %%A in ('findstr /B "EDQ_PUBLIC_PORT=" .env') do set "PUBLIC_PORT=%%B"

if not exist data (
  mkdir data
)

echo Starting EDQ...
REM Detect a previous install (existing edq-backend image). If found,
REM force a --no-cache rebuild to avoid carrying forward broken cached
REM layers from an earlier failed install. Uses ~2 extra minutes but
REM eliminates the "Security Tools: Unavailable" class of first-install
REM issues caused by stale image layers.
set "FORCE_REBUILD=0"
for /f %%I in ('docker image ls -q edq-backend 2^>nul') do set "FORCE_REBUILD=1"
if "%FORCE_REBUILD%"=="1" (
  echo Detected existing edq-backend image. Rebuilding with --no-cache to
  echo avoid stale cached layers. This takes an extra ~2 minutes but
  echo prevents the "Security Tools: Unavailable" failure mode.
  docker compose build --no-cache backend
  if errorlevel 1 (
    echo ERROR: backend rebuild failed. See output above.
    exit /b 1
  )
)
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
echo === EDQ is running at http://localhost:%PUBLIC_PORT% ===
echo   Login: username 'admin' / password from INITIAL_ADMIN_PASSWORD in the root .env file
if not "%ADMIN_PASS%"=="" echo   Generated initial admin password: %ADMIN_PASS%
echo   (Change your password after first login)
echo   After password rotation, set EDQ_ADMIN_PASS or -AdminPass for smoke scripts
echo.
echo Useful commands:
echo   docker compose logs -f        View live logs
echo   docker compose down           Stop EDQ
echo   docker compose down -v        Stop EDQ and remove data

endlocal
