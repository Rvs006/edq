@echo off
setlocal

echo === EDQ Update ===
cd /d "%~dp0"

if not exist .env (
  echo ERROR: .env not found. Run setup.bat first.
  exit /b 1
)

echo Fetching latest changes from GitHub...
git fetch origin
if errorlevel 1 exit /b 1

echo Switching to main...
git switch main
if errorlevel 1 exit /b 1

echo Pulling latest official release...
git pull --ff-only origin main
if errorlevel 1 exit /b 1

echo Rebuilding EDQ containers...
docker compose up --build -d
if errorlevel 1 exit /b 1

echo.
echo Current container status:
docker compose ps

echo.
echo === EDQ update complete ===
echo Open http://localhost

endlocal
