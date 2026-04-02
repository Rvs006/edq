"""Rate limiter with in-memory default and optional Redis persistence.

When REDIS_URL is configured, uses Redis for cross-instance rate limiting.
Otherwise falls back to a local sliding-window implementation.
"""

import logging
import time
from collections import defaultdict
from typing import Dict

from fastapi import HTTPException, Request, status

logger = logging.getLogger("edq.middleware.rate_limit")


class _Bucket:
    """Track request timestamps for a single key."""

    __slots__ = ("timestamps",)

    def __init__(self) -> None:
        self.timestamps: list[float] = []

    def is_allowed(self, now: float, window: int, max_requests: int) -> bool:
        cutoff = now - window
        self.timestamps = [t for t in self.timestamps if t > cutoff]
        if len(self.timestamps) >= max_requests:
            return False
        self.timestamps.append(now)
        return True


class InMemoryRateLimiter:
    """Sliding-window rate limiter keyed by client IP (single-instance only)."""

    def __init__(self) -> None:
        self._buckets: Dict[str, _Bucket] = defaultdict(_Bucket)

    def check(self, key: str, max_requests: int, window_seconds: int = 60) -> bool:
        return self._buckets[key].is_allowed(time.monotonic(), window_seconds, max_requests)


class RedisRateLimiter:
    """Redis-backed sliding-window rate limiter for multi-instance deployments."""

    def __init__(self, redis_url: str) -> None:
        import redis
        self._redis = redis.from_url(redis_url, decode_responses=True)
        logger.info("Rate limiter using Redis: %s", redis_url.split("@")[-1])

    def check(self, key: str, max_requests: int, window_seconds: int = 60) -> bool:
        now = time.time()
        pipe = self._redis.pipeline()
        redis_key = f"ratelimit:{key}"
        cutoff = now - window_seconds
        pipe.zremrangebyscore(redis_key, 0, cutoff)
        pipe.zcard(redis_key)
        pipe.zadd(redis_key, {str(now): now})
        pipe.expire(redis_key, window_seconds + 1)
        results = pipe.execute()
        current_count = results[1]
        if current_count >= max_requests:
            # Remove the entry we just added since we're denying the request
            self._redis.zrem(redis_key, str(now))
            return False
        return True


def _create_rate_limiter():
    """Create the appropriate rate limiter based on configuration."""
    from app.config import settings
    if settings.REDIS_URL:
        try:
            limiter = RedisRateLimiter(settings.REDIS_URL)
            return limiter
        except Exception:
            logger.warning("Failed to connect to Redis, falling back to in-memory rate limiter")
    return InMemoryRateLimiter()


rate_limiter = _create_rate_limiter()


# IPs that are trusted to set X-Forwarded-For (nginx in Docker resolves as 172.x.x.x)
# Only trust X-Forwarded-For when the direct connection comes from a known proxy.
_TRUSTED_PROXY_NETWORKS = ("127.0.0.1", "::1", "172.")


def get_client_ip(request: Request) -> str:
    """Extract client IP from request.

    Only trust X-Forwarded-For when the TCP peer is a known internal proxy.
    This prevents attackers from spoofing X-Forwarded-For to bypass rate limits.
    """
    peer = request.client.host if request.client else None
    if peer and any(peer.startswith(p) for p in _TRUSTED_PROXY_NETWORKS):
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
    if peer:
        return peer
    return "unknown"


def check_rate_limit(request: Request, max_requests: int, window_seconds: int = 60, action: str = "default") -> None:
    """Raise 429 if rate limit is exceeded for the client IP + action."""
    ip = get_client_ip(request)
    key = f"{ip}:{action}"
    if not rate_limiter.check(key, max_requests, window_seconds):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Please try again later.",
        )


def check_user_rate_limit(
    request: Request,
    user_id: str,
    max_requests: int,
    window_seconds: int = 60,
    action: str = "default",
) -> None:
    """Rate limit by authenticated user ID (prevents abuse from a single account).

    This runs in addition to IP-based rate limiting, catching cases where a
    single user has multiple IPs (VPN rotation, proxies).
    """
    key = f"user:{user_id}:{action}"
    if not rate_limiter.check(key, max_requests, window_seconds):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests for this account. Please try again later.",
        )
