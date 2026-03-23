@echo off
echo === EDQ Setup ===

if not exist .env (
  copy .env.example .env
  echo Created .env — edit it to set custom secrets before production use
)

if not exist data (
  mkdir data
)

echo Starting EDQ...
docker compose up --build -d

echo.
echo Waiting for services to start...
timeout /t 10 /nobreak >nul

echo.
echo === EDQ is running at http://localhost ===
echo   Login: admin@electracom.co.uk / Admin123!
echo   (Change your password after first login)
echo.
echo Useful commands:
echo   docker compose logs -f        View live logs
echo   docker compose down            Stop EDQ
echo   docker compose down -v         Stop EDQ and remove data
