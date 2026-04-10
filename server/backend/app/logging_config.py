"""Structured logging configuration for EDQ backend."""

from contextvars import ContextVar, Token
import logging
import logging.config
from typing import Any

from app.config import settings

_request_id_ctx: ContextVar[str | None] = ContextVar("edq_request_id", default=None)
_request_method_ctx: ContextVar[str | None] = ContextVar("edq_request_method", default=None)
_request_path_ctx: ContextVar[str | None] = ContextVar("edq_request_path", default=None)


def bind_request_log_context(
    request_id: str,
    *,
    method: str | None = None,
    path: str | None = None,
) -> tuple[Token, Token, Token]:
    """Bind request metadata to the current logging context."""
    return (
        _request_id_ctx.set(request_id),
        _request_method_ctx.set(method),
        _request_path_ctx.set(path),
    )


def reset_request_log_context(tokens: tuple[Token, Token, Token]) -> None:
    """Reset request metadata after a request completes."""
    request_id_token, method_token, path_token = tokens
    _request_id_ctx.reset(request_id_token)
    _request_method_ctx.reset(method_token)
    _request_path_ctx.reset(path_token)


class RequestContextFilter(logging.Filter):
    """Attach request metadata to log records when available."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = _request_id_ctx.get()
        record.http_method = _request_method_ctx.get()
        record.http_path = _request_path_ctx.get()
        record.service = "edq-backend"
        record.environment = settings.SENTRY_ENVIRONMENT
        return True


class JSONFormatter(logging.Formatter):
    """JSON-structured log formatter for production use."""

    def format(self, record: logging.LogRecord) -> str:
        import json
        from datetime import datetime, timezone

        log_entry: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "service": getattr(record, "service", "edq-backend"),
            "environment": getattr(record, "environment", settings.SENTRY_ENVIRONMENT),
        }

        if record.exc_info and record.exc_info[0] is not None:
            log_entry["exception"] = self.formatException(record.exc_info)

        if getattr(record, "request_id", None):
            log_entry["request_id"] = record.request_id
        if getattr(record, "http_method", None):
            log_entry["http_method"] = record.http_method
        if getattr(record, "http_path", None):
            log_entry["http_path"] = record.http_path

        if record.name.startswith("edq."):
            # Include module context for application logs
            log_entry["module"] = record.module
            if record.funcName:
                log_entry["function"] = record.funcName

        return json.dumps(log_entry, default=str)


def configure_logging() -> None:
    """Configure structured logging for the EDQ application."""
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    use_json = bool(settings.LOG_JSON)

    if use_json:
        formatter: dict[str, Any] = {
            "class": "app.logging_config.JSONFormatter",
        }
    else:
        formatter = {
            "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        }

    config: dict[str, Any] = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": formatter,
        },
        "filters": {
            "request_context": {
                "()": "app.logging_config.RequestContextFilter",
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stdout",
                "formatter": "default",
                "filters": ["request_context"],
            },
        },
        "loggers": {
            "edq": {
                "level": log_level,
                "handlers": ["console"],
                "propagate": False,
            },
            "uvicorn": {
                "level": "INFO",
                "handlers": ["console"],
                "propagate": False,
            },
            "uvicorn.access": {
                "level": "INFO",
                "handlers": ["console"],
                "propagate": False,
            },
            "sqlalchemy.engine": {
                "level": "WARNING",
                "handlers": ["console"],
                "propagate": False,
            },
        },
        "root": {
            "level": "WARNING",
            "handlers": ["console"],
        },
    }

    logging.config.dictConfig(config)

    logger = logging.getLogger("edq.startup")
    logger.info(
        "Logging configured: level=%s, format=%s",
        settings.LOG_LEVEL,
        "json" if use_json else "text",
    )
