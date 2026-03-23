# EDQ — First Run Guide

## Prerequisites
- Docker Desktop installed and running
- Git installed

## Setup (One Time)

1. Clone and setup:
   ```
   git clone https://github.com/Rvs006/edq.git
   cd edq
   ```

2. On Windows: Run `setup.bat`
   On Mac/Linux: Run `chmod +x setup.sh && ./setup.sh`

3. Wait for the build to complete (~5-8 minutes first time)

4. Open http://localhost in Chrome

## Login
- Email: admin@electracom.co.uk
- Password: Admin123!
- **Change your password after first login** (Settings → Security)

## Running Tests
1. Add a device (Devices → Add Device)
2. Enter the device IP address and details
3. Start a test run (device page → Start Test Run)
4. Watch automated tests run in real-time
5. Complete guided manual tests by clicking Pass/Fail
6. Generate report (Reports → Generate)

## Stopping EDQ
```
docker compose down
```

## Troubleshooting

**Port 80 in use:** Edit `docker-compose.yml`, change `"80:80"` to `"8080:80"`, then access http://localhost:8080

**Docker not running:** Start Docker Desktop first

**Build fails:** Run `docker compose down -v && docker compose up --build`

**Backend unhealthy:** Check logs with `docker compose logs backend`

**Tools sidecar issues:** Check logs with `docker compose logs tools`

**Database reset:** Run `docker compose down -v` to remove all data, then `docker compose up --build -d`
