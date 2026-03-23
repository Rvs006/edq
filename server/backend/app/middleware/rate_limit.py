"""In-memory rate limiter using a sliding-window token bucket."""

import time
from collections import defaultdict
from typing import Dict, Tuple

from fastapi import HTTPException, Request, status


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


class RateLimiter:
    """Sliding-window rate limiter keyed by client IP."""

    def __init__(self) -> None:
        self._buckets: Dict[str, _Bucket] = defaultdict(_Bucket)

    def check(self, key: str, max_requests: int, window_seconds: int = 60) -> bool:
        """Return True if the request is allowed, False if rate-limited."""
        return self._buckets[key].is_allowed(time.time(), window_seconds, max_requests)


rate_limiter = RateLimiter()


def get_client_ip(request: Request) -> str:
    """Extract client IP from request, respecting X-Forwarded-For behind proxy."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def check_rate_limit(request: Request, max_requests: int, window_seconds: int = 60) -> None:
    """Raise 429 if rate limit is exceeded for the client IP."""
    ip = get_client_ip(request)
    if not rate_limiter.check(ip, max_requests, window_seconds):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Please try again later.",
        )
