"""Bot configuration loading and validation.

Loads configuration from environment variables with validation
and sensible defaults for the Erebus Discord bot.
"""

from __future__ import annotations

import os
import warnings
from dataclasses import dataclass
from enum import Enum
from typing import ClassVar

from dotenv import load_dotenv


class Environment(Enum):
    """Application environment."""

    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


@dataclass
class Config:
    """Erebus bot configuration.

    Loads and validates configuration from environment variables.
    All sensitive values are loaded from environment, never hardcoded.
    """

    # Discord settings
    discord_bot_token: str
    discord_user_id: int
    allowed_user_ids: set[int]
    discord_guild_id: int | None = None

    # AI Model settings
    claude_api_key: str | None = None

    # Application settings
    environment: Environment = Environment.DEVELOPMENT
    log_level: str = "INFO"

    # Class-level constants
    BOT_NAME: ClassVar[str] = "Erebus"
    BOT_DESCRIPTION: ClassVar[str] = "The darkness that works - a stateful AI assistant"

    @classmethod
    def from_env(cls, env_file: str | None = None) -> Config:
        """Load configuration from environment variables.

        Args:
            env_file: Optional path to .env file. If not provided,
                     looks for .env in current directory.

        Returns:
            Validated Config instance.

        Raises:
            ValueError: If required configuration is missing or invalid.
        """
        if env_file:
            load_dotenv(env_file)
        else:
            load_dotenv()

        # Required: Discord bot token
        discord_bot_token = os.getenv("DISCORD_BOT_TOKEN")
        if not discord_bot_token or discord_bot_token == "your_discord_bot_token_here":
            raise ValueError(
                "DISCORD_BOT_TOKEN is required. "
                "Get it from https://discord.com/developers/applications"
            )

        # Required: Primary user ID for whitelist
        discord_user_id_str = os.getenv("DISCORD_USER_ID")
        if not discord_user_id_str or discord_user_id_str == "your_discord_user_id_here":
            raise ValueError(
                "DISCORD_USER_ID is required. "
                "Enable Developer Mode in Discord and copy your user ID."
            )

        try:
            discord_user_id = int(discord_user_id_str)
        except ValueError as e:
            raise ValueError(
                f"DISCORD_USER_ID must be a valid integer, got: {discord_user_id_str}"
            ) from e

        # Build allowed user IDs set (includes primary user)
        allowed_user_ids = {discord_user_id}
        allowed_ids_str = os.getenv("ALLOWED_USER_IDS", "")
        if allowed_ids_str and allowed_ids_str != "your_discord_user_id_here":
            for id_str in allowed_ids_str.split(","):
                id_str = id_str.strip()
                if id_str:
                    try:
                        allowed_user_ids.add(int(id_str))
                    except ValueError:
                        warnings.warn(
                            f"Invalid user ID in ALLOWED_USER_IDS: '{id_str}' - skipping",
                            UserWarning,
                            stacklevel=2,
                        )

        # Optional: Guild ID for faster command sync during development
        discord_guild_id = None
        guild_id_str = os.getenv("DISCORD_GUILD_ID")
        if guild_id_str and guild_id_str != "optional_test_server_id":
            try:
                discord_guild_id = int(guild_id_str)
            except ValueError:
                pass  # Use global commands if invalid

        # Environment
        env_str = os.getenv("ENVIRONMENT", "development").lower()
        try:
            environment = Environment(env_str)
        except ValueError:
            environment = Environment.DEVELOPMENT

        # Log level
        log_level = os.getenv("LOG_LEVEL", "INFO").upper()
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if log_level not in valid_levels:
            log_level = "INFO"

        # Optional: Claude API key (required for AI features)
        claude_api_key = os.getenv("CLAUDE_API_KEY")
        if claude_api_key == "your_anthropic_api_key_here":
            claude_api_key = None

        return cls(
            discord_bot_token=discord_bot_token,
            discord_user_id=discord_user_id,
            allowed_user_ids=allowed_user_ids,
            discord_guild_id=discord_guild_id,
            claude_api_key=claude_api_key,
            environment=environment,
            log_level=log_level,
        )

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
        return user_id in self.allowed_user_ids
