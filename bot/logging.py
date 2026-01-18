"""Logging configuration for Erebus bot.

Sets up structured logging with rich console output for development
and JSON formatting for production.
"""

from __future__ import annotations

import logging
import sys
from typing import TYPE_CHECKING

import structlog
from rich.console import Console
from rich.logging import RichHandler

if TYPE_CHECKING:
    from config import ErebusConfig


def setup_logging(config: ErebusConfig) -> None:
    """Configure logging for the application.

    Uses rich for development console output and structlog for
    structured logging in production.

    Args:
        config: Bot configuration with log level settings.
    """
    log_level = getattr(logging, config.log_level, logging.INFO)

    if config.is_development:
        # Development: Rich console output with colors
        console = Console(stderr=True)
        handler = RichHandler(
            console=console,
            rich_tracebacks=True,
            tracebacks_show_locals=True,
            show_time=True,
            show_path=True,
        )
        handler.setFormatter(logging.Formatter("%(message)s"))

        # Configure root logger
        logging.basicConfig(
            level=log_level,
            handlers=[handler],
            format="%(message)s",
        )

        # Configure structlog for development
        structlog.configure(
            processors=[
                structlog.contextvars.merge_contextvars,
                structlog.processors.add_log_level,
                structlog.processors.StackInfoRenderer(),
                structlog.dev.ConsoleRenderer(colors=True),
            ],
            wrapper_class=structlog.make_filtering_bound_logger(log_level),
            context_class=dict,
            logger_factory=structlog.PrintLoggerFactory(),
            cache_logger_on_first_use=True,
        )
    else:
        # Production: JSON output for log aggregation
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(
            logging.Formatter(
                '{"timestamp": "%(asctime)s", "level": "%(levelname)s", '
                '"logger": "%(name)s", "message": "%(message)s"}'
            )
        )

        logging.basicConfig(
            level=log_level,
            handlers=[handler],
        )

        # Configure structlog for production
        structlog.configure(
            processors=[
                structlog.contextvars.merge_contextvars,
                structlog.processors.add_log_level,
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.processors.StackInfoRenderer(),
                structlog.processors.format_exc_info,
                structlog.processors.JSONRenderer(),
            ],
            wrapper_class=structlog.make_filtering_bound_logger(log_level),
            context_class=dict,
            logger_factory=structlog.PrintLoggerFactory(),
            cache_logger_on_first_use=True,
        )

    # Reduce noise from third-party libraries
    logging.getLogger("discord").setLevel(logging.WARNING)
    logging.getLogger("discord.http").setLevel(logging.WARNING)
    logging.getLogger("discord.gateway").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
