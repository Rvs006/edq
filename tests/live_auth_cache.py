"""Shared auth-cache helpers for the live-app integration suite."""

from __future__ import annotations

from live_helpers import _login

_auth_cache: dict[str, dict] = {}


async def get_cached_auth(username: str, password: str, force_refresh: bool = False) -> dict:
    if force_refresh or username not in _auth_cache:
        _auth_cache[username] = await _login(username, password)
    return _auth_cache[username]


def invalidate_auth_cache(username: str | None = None) -> None:
    if username:
        _auth_cache.pop(username, None)
    else:
        _auth_cache.clear()