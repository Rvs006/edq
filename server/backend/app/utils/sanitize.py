"""Input sanitization utilities for XSS protection."""

from typing import Optional

try:
    import nh3

    def strip_html(value: Optional[str]) -> Optional[str]:
        """Remove all HTML tags from a string value using nh3."""
        if value is None:
            return None
        return nh3.clean(value, tags=set(), attributes={}).strip()

except ImportError:
    import re

    _TAG_RE = re.compile(r"<[^>]+>")
    _SCRIPT_PATTERNS = re.compile(
        r"(javascript\s*:|on\w+\s*=|<\s*script|<\s*iframe|<\s*object|<\s*embed)",
        re.IGNORECASE,
    )

    def strip_html(value: Optional[str]) -> Optional[str]:  # type: ignore[misc]
        """Remove HTML tags from a string value (regex fallback)."""
        if value is None:
            return None
        cleaned = _TAG_RE.sub("", value)
        cleaned = _SCRIPT_PATTERNS.sub("", cleaned)
        return cleaned.strip()


def sanitize_dict(data: dict, fields: list[str]) -> dict:
    """Sanitize specified string fields in a dictionary."""
    sanitized = dict(data)
    for field in fields:
        if field in sanitized and isinstance(sanitized[field], str):
            sanitized[field] = strip_html(sanitized[field])
    return sanitized
