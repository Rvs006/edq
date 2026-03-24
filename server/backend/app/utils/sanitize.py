"""Input sanitization utilities for XSS protection."""

import re
from typing import Optional

# Regex to strip HTML tags
_TAG_RE = re.compile(r"<[^>]+>")

# Dangerous patterns that could indicate XSS attempts
_SCRIPT_PATTERNS = re.compile(
    r"(javascript\s*:|on\w+\s*=|<\s*script|<\s*iframe|<\s*object|<\s*embed)",
    re.IGNORECASE,
)


def strip_html(value: Optional[str]) -> Optional[str]:
    """Remove HTML tags from a string value."""
    if value is None:
        return None
    cleaned = _TAG_RE.sub("", value)
    # Also remove dangerous patterns
    cleaned = _SCRIPT_PATTERNS.sub("", cleaned)
    return cleaned.strip()


def sanitize_dict(data: dict, fields: list[str]) -> dict:
    """Sanitize specified string fields in a dictionary."""
    sanitized = dict(data)
    for field in fields:
        if field in sanitized and isinstance(sanitized[field], str):
            sanitized[field] = strip_html(sanitized[field])
    return sanitized
