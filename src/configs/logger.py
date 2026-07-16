"""
Logging configuration for the application.

This module configures the logging system for the application, integrating
both standard logging and structured logging via Structlog. It also sets up
Sentry for error tracking in production environments and writes all log
records to rotating files for later inspection.
"""

import logging
import logging.handlers
import sys
import threading
from typing import Any

import sentry_sdk
import structlog
from sentry_sdk.integrations.logging import LoggingIntegration

from src.configs.settings import get_settings


class _LoggingLifecycle:
    """Encapsulates the logging configuration state and thread safety."""

    lock = threading.Lock()
    logging_configured = False


def _init_sentry(dsn: str, environment: str) -> None:
    """
    Initialize Sentry for error tracking in production environments.

    Parameters
    ----------
    dsn : str
        The Data Source Name (DSN) for Sentry, used to identify the project.

    environment : str
        The environment name (e.g., 'production', 'staging') for Sentry context.

    Returns
    -------
    None
    """
    sentry_sdk.init(
        dsn=dsn,
        environment=environment,
        integrations=[
            LoggingIntegration(
                level=logging.INFO,
                event_level=logging.ERROR,
            )
        ],
        attach_stacktrace=True,
        send_default_pii=False,
    )


def _shared_processors() -> list[Any]:
    """
    Define the shared processor chain for structured logging.

    Returns
    -------
    list[Any]
        A list of processors for structured logging.
    """
    return [
        # Merge context variables for structured logging
        structlog.contextvars.merge_contextvars,
        # Add standard library log level
        structlog.stdlib.add_log_level,
        # Add timestamp to the event dictionary
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        # Add stack info to the event dictionary
        structlog.processors.StackInfoRenderer(),
        # Add exception info to the event dictionary
        structlog.processors.format_exc_info,
        # Decode bytes to Unicode for consistent output
        structlog.processors.UnicodeDecoder(),
    ]


def _configure_logging() -> None:
    """
    Configure the logging system for the application.

    This function sets up the logging configuration, including console and file
    handlers, structured logging via Structlog, and Sentry integration for
    error tracking in production environments.

    Returns
    -------
    None
    """
    if _LoggingLifecycle.logging_configured:
        return

    with _LoggingLifecycle.lock:
        if _LoggingLifecycle.logging_configured:
            return

        # Initialize the settings and determine the environment
        settings = get_settings()
        is_production = settings.ENVIRONMENT == "production"

        # 0. Initialize Sentry in Production or Staging Environments
        if settings.SENTRY_DSN and is_production:
            _init_sentry(settings.SENTRY_DSN, settings.ENVIRONMENT)

        # 1. Define shared processor chain
        shared_processors = _shared_processors()

        # 2. Configure Structlog Engine
        structlog.configure(
            processors=[
                *shared_processors,
                structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
            ],
            logger_factory=structlog.stdlib.LoggerFactory(),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=True,
        )

        # 3. Choose renderer for the console output
        console_renderer = (
            structlog.processors.JSONRenderer()
            if is_production
            else structlog.dev.ConsoleRenderer(colors=True)
        )

        # 4. Bind to System Standard Output Stream
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(
            structlog.stdlib.ProcessorFormatter(
                foreign_pre_chain=shared_processors,
                processors=[
                    structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                    console_renderer,
                ],
            )
        )

        # 5. Configure Rotating File Handler for Persistent Logging
        file_handler = logging.handlers.TimedRotatingFileHandler(
            filename=str(settings.LOGS),
            when=settings.LOG_ROTATION_WHEN,
            interval=1,
            backupCount=settings.LOG_BACKUP_COUNT,
            encoding="utf-8",
        )
        file_handler.setFormatter(
            structlog.stdlib.ProcessorFormatter(
                foreign_pre_chain=shared_processors,
                processors=[
                    structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                    structlog.processors.JSONRenderer(),
                ],
            )
        )

        # 6. Configure Root Logger Framework
        root_logger = logging.getLogger()

        # Clean up existing default handlers to prevent duplicate output records
        for handler in root_logger.handlers.copy():
            root_logger.removeHandler(handler)

        root_logger.addHandler(console_handler)
        root_logger.addHandler(file_handler)
        root_logger.setLevel(settings.LOG_LEVEL.upper())

        # Redirect standard library warnings through the logging ecosystem
        logging.captureWarnings(True)

        _LoggingLifecycle.logging_configured = True


def get_logger() -> structlog.stdlib.BoundLogger:
    """
    Retrieve a structured logger instance for the application.

    Returns
    -------
    structlog.stdlib.BoundLogger
        A structured logger instance configured with the application settings.

    Example
    -------
    >>> logger = get_logger()
    >>> logger.info("Application started", session_id=settings.SESSION_ID)
    """
    _configure_logging()
    settings = get_settings()
    return structlog.get_logger(settings.LOGGER_NAME)
