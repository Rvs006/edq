"""Rate limiter with in-memory default and optional Redis persistence.

When REDIS_URL is configured, uses Redis for cross-instance rate limiting.
Otherwise falls back to a local sliding-window implementation.
"""

import logging
import time
from collections import defaultdict
from typing import Dict, Protocol

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


class RateLimiter(Protocol):
    def check(self, key: str, max_requests: int, window_seconds: int = 60) -> bool: ...


class InMemoryRateLimiter:
    """Sliding-window rate limiter keyed by client IP (single-instance only)."""

    def __init__(self) -> None:
        self._buckets: Dict[str, _Bucket] = defaultdict(_Bucket)
        self._request_count = 0

    def check(self, key: str, max_requests: int, window_seconds: int = 60) -> bool:
        self._request_count += 1
        # Prune stale buckets every 1000 requests to prevent memory leak
        if self._request_count % 1000 == 0:
            now = time.monotonic()
            stale_keys = [
                k for k, b in self._buckets.items()
                if not b.timestamps or b.timestamps[-1] < now - 300
            ]
            for k in stale_keys:
                del self._buckets[k]
        return self._buckets[key].is_allowed(time.monotonic(), window_seconds, max_requests)


class RedisRateLimiter:
    """Redis-backed sliding-window rate limiter for multi-instance deployments."""

    # Atomic Lua script: prune expired entries, check count, conditionally add.
    # This eliminates the TOCTOU race in the previous pipeline-based approach.
    _LUA_SCRIPT = """
    local key = KEYS[1]
    local now = tonumber(ARGV[1])
    local window = tonumber(ARGV[2])
    local max_requests = tonumber(ARGV[3])
    local ttl = tonumber(ARGV[4])
    redis.call('ZREMRANGEBYSCORE', key, 0, now - window)
    local count = redis.call('ZCARD', key)
    if count >= max_requests then
        return 0
    end
    redis.call('ZADD', key, now, tostring(now) .. ':' .. tostring(math.random(1000000)))
    redis.call('EXPIRE', key, ttl)
    return 1
    """

    def __init__(self, redis_url: str) -> None:
        import redis
        self._redis = redis.from_url(redis_url, decode_responses=True)
        self._redis.ping()
        self._script = self._redis.register_script(self._LUA_SCRIPT)
        logger.info("Rate limiter using Redis: %s", redis_url.split("@")[-1])

    def check(self, key: str, max_requests: int, window_seconds: int = 60) -> bool:
        now = time.time()
        redis_key = f"ratelimit:{key}"
        result = self._script(
            keys=[redis_key],
            args=[now, window_seconds, max_requests, window_seconds + 1],
        )
        return bool(result)


def _create_rate_limiter() -> RateLimiter:
    """Create the appropriate rate limiter based on configuration."""
    from app.config import settings
    if settings.REDIS_URL:
        try:
            limiter = RedisRateLimiter(settings.REDIS_URL)
            return limiter
        except Exception as exc:
            if settings.REDIS_REQUIRED:
                raise RuntimeError("REDIS_REQUIRED=true but Redis is unavailable") from exc
            logger.warning("Failed to connect to Redis, falling back to in-memory rate limiter")
    return InMemoryRateLimiter()


rate_limiter: RateLimiter = _create_rate_limiter()


def reset_rate_limiter() -> RateLimiter:
    """Rebuild the global limiter after runtime config changes."""
    global rate_limiter
    rate_limiter = _create_rate_limiter()
    return rate_limiter


# IPs that are trusted to set X-Forwarded-For (nginx in Docker resolves as 172.x.x.x)
# Only trust X-Forwarded-For when the direct connection comes from a known proxy.
import ipaddress as _ipaddress

_TRUSTED_PROXY_CIDRS = (
    _ipaddress.ip_network("127.0.0.0/8"),
    _ipaddress.ip_network("::1/128"),
    _ipaddress.ip_network("172.16.0.0/12"),  # Docker bridge range only, not all 172.x
    _ipaddress.ip_network("10.0.0.0/8"),
)


def _is_trusted_proxy(peer_ip: str) -> bool:
    """Return True if the peer IP is in a trusted proxy network."""
    try:
        addr = _ipaddress.ip_address(peer_ip)
    except ValueError:
        return False
    return any(addr in network for network in _TRUSTED_PROXY_CIDRS)


def get_client_ip(request: Request) -> str:
    """Extract client IP from request.

    Only trust X-Forwarded-For when the TCP peer is a known internal proxy.
    This prevents attackers from spoofing X-Forwarded-For to bypass rate limits.
    """
    peer = request.client.host if request.client else None
    if peer and _is_trusted_proxy(peer):
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
