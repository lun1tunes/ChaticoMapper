"""Centralised logging configuration aligned with instachatico-app (without Telegram alerts)."""

from __future__ import annotations

import contextvars
import logging
import os
from logging.config import dictConfig
from typing import Optional

# Context variable used by filters to enrich log records
trace_id_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar("trace_id", default=None)


class ChannelAliasFilter(logging.Filter):
    """Map noisy logger names to concise aliases for log output."""

    NAME_MAP = {
        "uvicorn.access": "uvicorn.access",
        "uvicorn.error": "uvicorn",
        "uvicorn": "uvicorn",
        "sqlalchemy.engine": "sqlalchemy",
        "celery.app.trace": "celery",
    }

    def filter(self, record: logging.LogRecord) -> bool:  # pragma: no cover - trivial
        record.channel = self.NAME_MAP.get(record.name, record.name)
        return True


class TraceIdFilter(logging.Filter):
    """Inject trace_id from context into log records."""

    def filter(self, record: logging.LogRecord) -> bool:  # pragma: no cover - trivial
        record.trace_id = trace_id_ctx.get() or "-"
        return True


def _resolve_log_level(default: Optional[str] = None) -> str:
    """Resolve desired log level from environment or provided default."""
    candidates = [
        os.getenv("LOGS_LEVEL", ""),
        os.getenv("LOG_LEVEL", ""),
        default or "",
    ]
    for candidate in candidates:
        level = candidate.strip().upper()
        if level in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            return level
    return "INFO"


def configure_logging(default_level: Optional[str] = None) -> None:
    """Configure application-wide logging in line with the reference project."""

    level = _resolve_log_level(default_level)

    config = {
        "version": 1,
        "disable_existing_loggers": False,
        "filters": {
            "channel": {"()": "src.core.logging_config.ChannelAliasFilter"},
            "trace": {"()": "src.core.logging_config.TraceIdFilter"},
        },
        "formatters": {
            "default": {
                "format": "%(asctime)s | %(levelname)-8s | %(channel)-20s | %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
            "with_trace": {
                "format": "%(asctime)s | %(levelname)-8s | %(channel)-20s | [%(trace_id)s] | %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
            "uvicorn_access": {
                "format": "%(asctime)s | %(levelname)-8s | %(channel)-20s | %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "with_trace" if level == "DEBUG" else "default",
                "level": level,
                "stream": "ext://sys.stdout",
                "filters": ["channel", "trace"],
            },
            "uvicorn_console": {
                "class": "logging.StreamHandler",
                "formatter": "uvicorn_access",
                "level": level if level != "DEBUG" else "INFO",
                "stream": "ext://sys.stdout",
                "filters": ["channel", "trace"],
            },
        },
        "loggers": {
            "": {
                "handlers": ["console"],
                "level": level,
            },
            "uvicorn": {
                "handlers": ["console"],
                "level": level,
                "propagate": False,
            },
            "uvicorn.error": {
                "handlers": ["console"],
                "level": level,
                "propagate": False,
            },
            "uvicorn.access": {
                "handlers": ["uvicorn_console"],
                "level": level if level != "DEBUG" else "INFO",
                "propagate": False,
            },
            "sqlalchemy": {
                "handlers": ["console"],
                "level": "WARNING",
                "propagate": False,
            },
            "celery": {
                "handlers": ["console"],
                "level": level,
                "propagate": False,
            },
            "celery.app.trace": {
                "handlers": ["console"],
                "level": level,
                "propagate": False,
            },
            "celery.pool": {
                "handlers": ["console"],
                "level": "WARNING",
                "propagate": False,
            },
            "celery.bootsteps": {
                "handlers": ["console"],
                "level": "WARNING",
                "propagate": False,
            },
            "celery.utils.functional": {
                "handlers": ["console"],
                "level": "WARNING",
                "propagate": False,
            },
            "celery.worker": {
                "handlers": ["console"],
                "level": "INFO",
                "propagate": False,
            },
            "httpx": {
                "handlers": ["console"],
                "level": "WARNING" if level != "DEBUG" else "INFO",
                "propagate": False,
            },
            "httpcore": {
                "handlers": ["console"],
                "level": "WARNING" if level != "DEBUG" else "INFO",
                "propagate": False,
            },
        },
    }

    dictConfig(config)
    logging.getLogger(__name__).debug("Logging configured with level %s", level)
