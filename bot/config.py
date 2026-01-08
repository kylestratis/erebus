"""Bot configuration using pydantic-settings.

Loads configuration from environment variables with validation.
In development, loads from .env file. In production, use Docker env vars.
"""

from __future__ import annotations

from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import ClassVar

from pydantic import Field, PrivateAttr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(str, Enum):
    """Application environment."""

    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class Settings(BaseSettings):
    """Erebus application settings.

    Loads configuration from environment variables. In development,
    also reads from .env file. Environment variables take precedence.

    Attributes:
        discord_bot_token: Discord bot token for authentication.
        discord_user_id: Primary user's Discord ID.
        discord_guild_id: Optional guild ID for faster command sync.
        allowed_user_ids: Set of Discord user IDs allowed to use the bot.
        todoist_api_token: Todoist API token for task management.
        obsidian_vault_path: Path to Obsidian vault root.
        obsidian_templates_path: Relative path to templates directory.
        obsidian_daily_notes_path: Relative path to daily notes directory.
        obsidian_daily_note_format: strftime format for daily note filenames.
        letta_api_url: Letta server API URL.
        letta_api_key: Letta API key (optional for local server).
        environment: Application environment (development/staging/production).
        log_level: Logging level.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # Ignore extra env vars
    )

    # Class-level constants (not loaded from env)
    BOT_NAME: ClassVar[str] = "Erebus"
    BOT_DESCRIPTION: ClassVar[str] = "The darkness that works - a stateful AI assistant"

    # Discord settings (required)
    discord_bot_token: str = Field(description="Discord bot token")
    discord_user_id: int = Field(description="Primary Discord user ID")
    discord_guild_id: int | None = Field(
        default=None,
        description="Optional guild ID for faster command sync in development",
    )

    # User allowlist (parsed from comma-separated string in env)
    allowed_user_ids: str = Field(
        default="",
        description="Comma-separated list of allowed Discord user IDs",
    )
    # Parsed set populated by model validator (private attr not from env)
    _allowed_user_ids_set: set[int] = PrivateAttr(default_factory=set)

    # Integration settings
    todoist_api_token: str | None = Field(
        default=None,
        description="Todoist API token",
    )

    # Obsidian vault settings
    obsidian_vault_path: Path | None = Field(
        default=None,
        description="Path to Obsidian vault root",
    )
    obsidian_templates_path: str = Field(
        default="Templates",
        description="Relative path to templates directory in vault",
    )
    obsidian_daily_notes_path: str = Field(
        default="Calendar/Daily Notes",
        description="Relative path to daily notes directory in vault",
    )
    obsidian_daily_note_format: str = Field(
        default="%Y-%m-%d",
        description="strftime format for daily note filenames",
    )

    # Scheduler settings
    scheduler_timezone: str = Field(
        default="America/Chicago",
        description="Timezone for scheduled jobs (IANA timezone name)",
    )
    scheduler_enabled: bool = Field(
        default=True,
        description="Whether to enable the job scheduler",
    )
    job_daily_note_enabled: bool = Field(
        default=True,
        description="Enable automatic daily note generation (6am)",
    )
    job_daily_note_cron: str = Field(
        default="0 6 * * *",
        description="Cron expression for daily note job",
    )
    job_end_of_day_sync_enabled: bool = Field(
        default=True,
        description="Enable end-of-day sync (11:55pm)",
    )
    job_end_of_day_sync_cron: str = Field(
        default="55 23 * * *",
        description="Cron expression for end-of-day sync job",
    )
    job_weekly_review_enabled: bool = Field(
        default=True,
        description="Enable weekly review prompt (Sunday 6pm)",
    )
    job_weekly_review_cron: str = Field(
        default="0 18 * * 0",
        description="Cron expression for weekly review job",
    )

    # Letta settings
    letta_api_url: str = Field(
        default="http://localhost:8283",
        description="Letta server API URL",
    )
    letta_api_key: str | None = Field(
        default=None,
        description="Letta API key (optional for local server)",
    )

    # Application settings
    environment: Environment = Field(
        default=Environment.DEVELOPMENT,
        description="Application environment",
    )
    log_level: str = Field(
        default="INFO",
        description="Logging level",
    )

    @field_validator("allowed_user_ids", mode="before")
    @classmethod
    def filter_placeholder_allowed_user_ids(cls, v: str | None) -> str:
        """Filter out placeholder values and comments from allowed_user_ids."""
        if v is None:
            return ""
        # Strip inline comments
        if "#" in v:
            v = v.split("#")[0]
        v = v.strip()
        # Filter placeholder
        if v == "your_discord_user_id_here":
            return ""
        return v

    @field_validator("log_level", mode="after")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Ensure log level is valid."""
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        v = v.upper()
        if v not in valid_levels:
            return "INFO"
        return v

    @field_validator(
        "job_daily_note_cron",
        "job_end_of_day_sync_cron",
        "job_weekly_review_cron",
        mode="after",
    )
    @classmethod
    def validate_cron_expression(cls, v: str) -> str:
        """Validate cron expressions at config load time."""
        from apscheduler.triggers.cron import CronTrigger

        try:
            CronTrigger.from_crontab(v, timezone="UTC")
        except ValueError as e:
            raise ValueError(f"Invalid cron expression '{v}': {e}") from e
        return v

    @field_validator("discord_bot_token", mode="before")
    @classmethod
    def validate_discord_token(cls, v: str | None) -> str:
        """Validate Discord bot token is set and not a placeholder."""
        if v is None or not v.strip():
            raise ValueError("DISCORD_BOT_TOKEN is required")
        if v == "your_discord_bot_token_here":
            raise ValueError("DISCORD_BOT_TOKEN must be set to a valid token")
        return v

    @field_validator("discord_user_id", mode="before")
    @classmethod
    def validate_discord_user_id(cls, v: int | str | None) -> int:
        """Validate Discord user ID is set and numeric."""
        if v is None:
            raise ValueError("DISCORD_USER_ID is required")
        if isinstance(v, str):
            if v == "your_discord_user_id_here" or not v.strip():
                raise ValueError("DISCORD_USER_ID must be set to a valid numeric ID")
            try:
                return int(v)
            except ValueError as e:
                raise ValueError(f"DISCORD_USER_ID must be numeric, got: {v}") from e
        return v

    @field_validator("todoist_api_token", "letta_api_key", mode="before")
    @classmethod
    def filter_placeholder_values(cls, v: str | None) -> str | None:
        """Filter out placeholder values from .env.example."""
        if v is None:
            return None
        placeholders = {
            "your_todoist_api_token_here",
            "optional_letta_api_key",
        }
        if v in placeholders:
            return None
        return v

    @model_validator(mode="after")
    def parse_and_validate_allowlist(self) -> Settings:
        """Parse allowed_user_ids string and ensure primary user is included."""
        # Parse comma-separated IDs
        parsed: set[int] = set()
        if self.allowed_user_ids:
            for id_str in self.allowed_user_ids.split(","):
                id_str = id_str.strip()
                if id_str:
                    try:
                        parsed.add(int(id_str))
                    except ValueError:
                        pass  # Skip invalid IDs
        # Always include primary user
        parsed.add(self.discord_user_id)
        self._allowed_user_ids_set = parsed
        return self

    @property
    def is_development(self) -> bool:
        """Check if running in development mode."""
        return self.environment == Environment.DEVELOPMENT

    @property
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return self.environment == Environment.PRODUCTION

    def is_user_allowed(self, user_id: int) -> bool:
        """Check if a user ID is in the allowed list.

        Args:
            user_id: Discord user ID to check.

        Returns:
            True if user is allowed to interact with the bot.
        """
        return user_id in self._allowed_user_ids_set


@lru_cache
def get_settings() -> Settings:
    """Get cached application settings.

    Returns:
        Validated Settings instance.
    """
    return Settings()
