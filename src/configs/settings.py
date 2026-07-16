"""
Application configuration model.

This module defines the `Settings` class, which encapsulates all configuration
parameters for the application. It leverages Pydantic's `BaseSettings` to load
configuration values from environment variables, providing type validation and
default values. The settings include runtime parameters, directory paths, and
external service configurations.
"""

from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Self

from pydantic import Field, computed_field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Absolute path to the project root directory
BASE_DIR = Path(__file__).resolve().parents[2]


class _Environment(StrEnum):
    """Enumeration of application environments."""

    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
    TEST = "test"


class _LogLevel(StrEnum):
    """Enumeration of logging levels."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class _Settings(BaseSettings):
    """
    Application configuration model.

    Settings are loaded from environment variables and validated during
    initialization. The class provides dynamically generated filesystem
    paths, artifact resolution utilities, and workspace initialization.

    Attributes
    ----------
    ENVIRONMENT : StrEnum
        The current application environment (e.g., development, production).
    LOG_LEVEL : StrEnum
        The logging level for the application.
    LOG_BACKUP_COUNT : int
        The number of backup log files to retain for rotating logs.
    LOG_ROTATION_WHEN : str
        The time interval for log rotation (e.g., 'midnight', 'H', 'D').
    LOGGER_NAME : str
        The name of the logger used for structured logging.
    SESSION_ID : str
        A unique identifier for the current session, used in log file naming.
    LOGS_DIR : Path
        The directory path where log files are stored.
    LOGS : Path
        The full path to the log file for the current session.
    SENTRY_DSN : str | None
        The Data Source Name (DSN) for Sentry error tracking. Required in production environment.
    """

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Runtime configuration
    ENVIRONMENT: _Environment = Field(
        default=_Environment.DEVELOPMENT,
        title="Application environment",
        description="The current application environment.",
        examples=["development", "test", "production"],
    )
    LOG_LEVEL: _LogLevel = Field(
        default=_LogLevel.INFO,
        title="Logging level",
        description="The logging level for the application.",
        examples=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
    )
    LOG_BACKUP_COUNT: int = Field(
        default=14,
        ge=1,
        title="Log backup count",
        description="The number of backup log files to retain for rotating logs.",
        examples=[7, 14, 30],
    )
    LOG_ROTATION_WHEN: str = Field(
        default="midnight",
        title="Log rotation schedule",
        description="The time interval for log rotation.",
        pattern=r"^(midnight|[Hh]|[Dd]|[Ww])$",
        examples=["midnight", "H", "D"],
    )
    LOGGER_NAME: str = Field(
        default="chun_forecast",
        min_length=1,
        title="Logger name",
        description="The name of the logger used for structured logging.",
        examples=["chun_forecast", "my_app_logger"],
    )
    SESSION_ID: str = Field(
        default="initial",
        min_length=1,
        title="Session ID",
        description="A unique identifier for the current session, used in log file naming.",
        examples=["initial", "20240701001"],
    )

    # Directory paths
    LOGS_DIR: Path = BASE_DIR / "logs"

    @computed_field
    @property
    def LOGS(self) -> Path:
        """Return the path to the log file."""
        return self.LOGS_DIR / f"{self.SESSION_ID}.log"

    # External services
    SENTRY_DSN: str | None = Field(
        default=None,
        json_schema_extra={"nullable": True},
        title="Sentry DSN",
        description="The Data Source Name (DSN) for Sentry error tracking.",
        examples=["https://examplePublicKey@o0.ingest.sentry.io/0", None],
    )

    @model_validator(mode="after")
    def _validate_required_fields(self) -> Self:
        """
        Validate required external service configuration.

        This method checks for the presence of required configuration values
        in non-test environments. If any required values are missing, it raises
        a ValueError with a descriptive message.

        Returns
        -------
        Self
            Validated settings instance.

        Raises
        ------
        ValueError
            If required configuration values are missing.
        """
        if self.ENVIRONMENT != _Environment.PRODUCTION:
            return self

        # Check for required fields in non-test environments
        required_fields = {
            "SENTRY_DSN": self.SENTRY_DSN,
        }

        # Identify any missing required fields
        missing = [field for field, value in required_fields.items() if value is None]
        if missing:
            raise ValueError(f"Missing required settings: {', '.join(missing)}")

        return self

    def _setup_workspace(self) -> None:
        """
        Create all required project directories.

        This method ensures that all configured output directories
        exist before pipeline execution begins.
        """
        output_dirs = [
            self.LOGS_DIR,
        ]
        for dir_path in output_dirs:
            dir_path.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> _Settings:
    """
    Return a cached application settings instance.

    The workspace is initialized during the first invocation,
    and subsequent calls reuse the cached configuration object.

    Returns
    -------
    _Settings
        Fully initialized application settings.

    Example
    -------
    >>> settings = get_settings()
    >>> print(settings.LOGS)
    /path/to/logs/initial.log
    """
    settings = _Settings()
    settings._setup_workspace()

    return settings
