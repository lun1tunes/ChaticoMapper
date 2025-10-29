"""Simple application-wide logging configuration."""

from __future__ import annotations

import logging
from typing import Optional


DEFAULT_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"


def setup_logging(level: Optional[str] = None) -> None:
    """Configure standard library logging for the application."""

    resolved_level = _resolve_log_level(level)

    logging.basicConfig(
        level=resolved_level,
        format=DEFAULT_FORMAT,
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Align noisy third-party loggers with the chosen level.
    for logger_name in ("uvicorn", "uvicorn.error", "sqlalchemy.engine"):
        logging.getLogger(logger_name).setLevel(resolved_level)


def _resolve_log_level(level: Optional[str]) -> int:
    if level:
        numeric = logging.getLevelName(level.upper())
        if isinstance(numeric, int):
            return numeric
    return logging.INFO
