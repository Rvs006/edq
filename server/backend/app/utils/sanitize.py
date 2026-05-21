"""Input sanitization utilities for XSS protection."""

from html.parser import HTMLParser
from typing import Optional


class _HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def get_text(self) -> str:
        return "".join(self.parts)


def _remove_case_insensitive(value: str, needle: str) -> str:
    cleaned: list[str] = []
    lower_value = value.lower()
    lower_needle = needle.lower()
    start = 0
    while True:
        index = lower_value.find(lower_needle, start)
        if index == -1:
            cleaned.append(value[start:])
            return "".join(cleaned)
        cleaned.append(value[start:index])
        start = index + len(needle)


def _strip_html_fallback(value: str) -> str:
    parser = _HTMLTextExtractor()
    parser.feed(value)
    parser.close()
    cleaned = parser.get_text()
    for unsafe in ("javascript:", "<script", "<iframe", "<object", "<embed"):
        cleaned = _remove_case_insensitive(cleaned, unsafe)
    return cleaned.strip()

try:
    import nh3

    def strip_html(value: Optional[str]) -> Optional[str]:
        """Remove all HTML tags from a string value using nh3."""
        if value is None:
            return None
        return nh3.clean(value, tags=set(), attributes={}).strip()

except ImportError:
    def strip_html(value: Optional[str]) -> Optional[str]:  # type: ignore[misc]
        """Remove HTML tags from a string value without regex fallback parsing."""
        if value is None:
            return None
        return _strip_html_fallback(value)


def sanitize_dict(data: dict, fields: list[str]) -> dict:
    """Sanitize specified string fields in a dictionary."""
    sanitized = dict(data)
    for field in fields:
        if field in sanitized and isinstance(sanitized[field], str):
            sanitized[field] = strip_html(sanitized[field])
    return sanitized
