"""Structured logging configuration for EDQ backend."""

import logging
import logging.config
from typing import Any

from app.config import settings


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
        }

        if record.exc_info and record.exc_info[0] is not None:
            log_entry["exception"] = self.formatException(record.exc_info)

        if hasattr(record, "request_id"):
            log_entry["request_id"] = record.request_id

        if record.name.startswith("edq."):
            # Include module context for application logs
            log_entry["module"] = record.module
            if record.funcName:
                log_entry["function"] = record.funcName

        return json.dumps(log_entry, default=str)


def configure_logging() -> None:
    """Configure structured logging for the EDQ application."""
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    use_json = not settings.DEBUG

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
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stdout",
                "formatter": "default",
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
