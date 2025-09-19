"""Logging bootstrap built on top of structlog."""
from __future__ import annotations

import logging
import os
import sys
from typing import Any, cast

import structlog
from structlog.stdlib import BoundLogger


def _configure_structlog(json_mode: bool) -> None:
    timestamper = structlog.processors.TimeStamper(fmt="iso", utc=True)
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        timestamper,
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
    ]

    if json_mode:
        processors = shared_processors + [structlog.processors.EventRenamer("message"), structlog.processors.JSONRenderer()]
    else:
        processors = shared_processors + [
            structlog.dev.set_exc_info,
            structlog.dev.ConsoleRenderer()
        ]

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )


def setup_logging(level: str = "INFO", *, json_mode: bool | None = None, diag: bool = False) -> None:
    """Initialise standard logging and structlog."""
    numeric_level = logging.getLevelName(level.upper()) if isinstance(level, str) else level
    logging.basicConfig(level=numeric_level, stream=sys.stdout, format="%(message)s")
    if json_mode is None:
        json_mode = os.getenv("ENV", "dev").lower() == "prod"
    _configure_structlog(json_mode)
    if diag:
        logging.getLogger("aiogram").setLevel(logging.DEBUG)
        logging.getLogger("storage.db").setLevel(logging.DEBUG)


def get_logger(name: str) -> BoundLogger:
    return cast(BoundLogger, structlog.get_logger(name))


def enrich_log(logger: Any, **kwargs: Any) -> None:
    """Bind additional context to the current logger."""
    try:
        logger.bind(**kwargs)
    except AttributeError:
        structlog.contextvars.bind_contextvars(**kwargs)
