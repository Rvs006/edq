# Redis profile for EDQ

Use Redis when EDQ is deployed in a shared or multi-instance environment and you want rate limiting to stay consistent across workers.

## Start Redis locally

```powershell
docker compose --profile redis up -d redis
```

## Backend settings

Set these in the repo-root `.env` for shared deployments:

```env
REDIS_URL=redis://redis:6379/0
REDIS_REQUIRED=true
```

For local single-user runs, leave Redis disabled and EDQ will fall back to the in-memory limiter.