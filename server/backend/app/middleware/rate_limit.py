"""In-memory rate limiter using a sliding-window token bucket."""

import time
from collections import defaultdict
from typing import Dict

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
