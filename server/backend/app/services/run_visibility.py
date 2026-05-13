"""Production-facing visibility rules for templates and test runs."""

from __future__ import annotations

from sqlalchemy import func, not_, or_
from sqlalchemy.sql.elements import ColumnElement

from app.models.test_template import TestTemplate
from app.models.user import User, UserRole

INTERNAL_NAME_PATTERNS = (
    "%codex%",
    "%smoke%",
    "%fixture%",
    "%goal%",
    "%internal test%",
    "%test internal%",
)


def can_include_internal(user: User, include_internal: bool) -> bool:
    return bool(include_internal and user.role == UserRole.ADMIN)


def is_internal_template_name(name: str | None) -> bool:
    lowered = (name or "").lower()
    return any(pattern.strip("%") in lowered for pattern in INTERNAL_NAME_PATTERNS)


def can_view_template(user: User, template: TestTemplate | None, include_internal: bool = False) -> bool:
    if template is None or not template.is_active:
        return False
    if is_internal_template_name(template.name):
        return can_include_internal(user, include_internal)
    return True


def internal_template_name_clause() -> ColumnElement[bool]:
    lowered = func.lower(TestTemplate.name)
    return or_(*(lowered.like(pattern) for pattern in INTERNAL_NAME_PATTERNS))


def public_template_clause() -> ColumnElement[bool]:
    return not_(internal_template_name_clause())
