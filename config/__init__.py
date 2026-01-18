"""Unified configuration system for Erebus.

This module provides a hierarchical configuration system that:
1. Loads base configuration from config.toml
2. Overrides with environment variables (especially for secrets)
3. Validates all configuration at startup

Configuration hierarchy:
- config.toml: Default values and non-sensitive configuration
- Environment variables: Secrets and environment-specific overrides
- CLI arguments: Runtime overrides (handled by bot.__main__)

Usage:
    from config import get_config
    config = get_config()

    # Access nested config
    print(config.discord.guild_id)
    print(config.letta.model)
    print(config.scheduler.jobs.daily_note.cron)
"""

from __future__ import annotations

import logging
import tomllib
from dataclasses import dataclass, field
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Any, ClassVar

from pydantic import Field, PrivateAttr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

# Project root is parent of config/
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_CONFIG_FILE = _PROJECT_ROOT / "config.toml"
_ENV_FILE = _PROJECT_ROOT / ".env"


class Environment(str, Enum):
    """Application environment."""

    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


# ---------------------------------------------------------------------------
# MCP Server Configuration (canonical location - used by both local and Letta)
# ---------------------------------------------------------------------------


@dataclass
class MCPServerConfig:
    """Configuration for an MCP server.

    Used for both local MCP connections (via mcp-client) and Letta's native
    MCP support. This is the canonical definition - do not duplicate.

    Attributes:
        name: Unique identifier for this server.
        command: Command to run the server (e.g., "npx", "node", "python").
        args: Arguments to pass to the command.
        env: Environment variables to pass to the server.
    """

    name: str
    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Nested Configuration Sections
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DiscordConfig:
    """Discord bot configuration.

    Attributes:
        bot_token: Discord bot token (from env, required).
        user_id: Primary Discord user ID (from env, required).
        guild_id: Optional guild ID for faster command sync.
        allowed_user_ids: Additional allowed user IDs.
    """

    bot_token: str
    user_id: int
    guild_id: int | None = None
    allowed_user_ids: frozenset[int] = field(default_factory=frozenset)

    def is_user_allowed(self, user_id: int) -> bool:
        """Check if a user ID is allowed to use the bot."""
        return user_id == self.user_id or user_id in self.allowed_user_ids


@dataclass(frozen=True)
class LettaConfig:
    """Letta server configuration.

    Attributes:
        api_url: Letta server API URL.
        api_key: Optional API key for authentication.
        model: Model identifier for the agent.
        embedding: Embedding model for archival memory search.
    """

    api_url: str = "http://localhost:8283"
    api_key: str | None = None
    model: str = "anthropic/claude-sonnet-4-20250514"
    embedding: str = "openai/text-embedding-3-small"


@dataclass(frozen=True)
class VaultConfig:
    """Obsidian vault configuration.

    Attributes:
        root: Absolute path to vault root (None if not configured).
        templates_path: Relative path to templates directory.
        daily_notes_path: Relative path to daily notes directory.
        daily_note_format: strftime format for daily note filenames.
    """

    root: Path | None = None
    templates_path: str = "Templates"
    daily_notes_path: str = "Calendar/Daily Notes"
    daily_note_format: str = "%Y-%m-%d"


@dataclass(frozen=True)
class AgentConfig:
    """Agent behavior configuration.

    Attributes:
        max_tool_iterations: Maximum tool call iterations per request.
        tool_call_timeout: Timeout for individual tool calls in seconds.
        log_tool_calls: Whether to log tool call details.
    """

    max_tool_iterations: int = 10
    tool_call_timeout: float = 30.0
    log_tool_calls: bool = True


@dataclass(frozen=True)
class JobConfig:
    """Configuration for a single scheduled job.

    Attributes:
        enabled: Whether this job is enabled.
        cron: Cron expression for job schedule.
    """

    enabled: bool = True
    cron: str = ""


@dataclass(frozen=True)
class SchedulerJobsConfig:
    """Configuration for all scheduled jobs.

    Attributes:
        daily_note: Daily note generation job.
        end_of_day_sync: End-of-day sync job.
        weekly_review: Weekly review reminder job.
    """

    daily_note: JobConfig = field(default_factory=lambda: JobConfig(cron="0 6 * * *"))
    end_of_day_sync: JobConfig = field(default_factory=lambda: JobConfig(cron="55 23 * * *"))
    weekly_review: JobConfig = field(default_factory=lambda: JobConfig(cron="0 18 * * 0"))


@dataclass(frozen=True)
class SchedulerConfig:
    """Scheduler configuration.

    Attributes:
        enabled: Whether the scheduler is enabled.
        timezone: IANA timezone for job schedules.
        jobs: Individual job configurations.
    """

    enabled: bool = True
    timezone: str = "America/New_York"
    jobs: SchedulerJobsConfig = field(default_factory=SchedulerJobsConfig)


# ---------------------------------------------------------------------------
# Main Configuration Class
# ---------------------------------------------------------------------------


class ErebusConfig(BaseSettings):
    """Unified Erebus configuration.

    Loads configuration from:
    1. config.toml (defaults and non-sensitive values)
    2. Environment variables (secrets and overrides)

    Environment variables use uppercase with underscores:
    - DISCORD_BOT_TOKEN, DISCORD_USER_ID, DISCORD_GUILD_ID
    - LETTA_API_URL, LETTA_API_KEY
    - OBSIDIAN_VAULT_PATH
    - TODOIST_API_TOKEN
    - LOG_LEVEL, ENVIRONMENT
    - SCHEDULER_TIMEZONE, JOB_DAILY_NOTE_ENABLED, etc.

    Attributes:
        environment: Application environment (development/staging/production).
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        discord: Discord bot configuration.
        letta: Letta server configuration.
        vault: Obsidian vault configuration.
        agent: Agent behavior configuration.
        scheduler: Scheduler configuration.
        mcp_servers: MCP server configurations.
        todoist_api_token: Todoist API token.
    """

    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Class-level constants
    BOT_NAME: ClassVar[str] = "Erebus"
    BOT_DESCRIPTION: ClassVar[str] = "The darkness that works - a stateful AI assistant"

    # Top-level settings
    environment: Environment = Environment.DEVELOPMENT
    log_level: str = "INFO"

    # Discord settings (from env)
    discord_bot_token: str = Field(description="Discord bot token")
    discord_user_id: int = Field(description="Primary Discord user ID")
    discord_guild_id: int | None = Field(default=None)
    allowed_user_ids: str = Field(default="")

    # Letta settings
    letta_api_url: str = "http://localhost:8283"
    letta_api_key: str | None = None
    letta_model: str = "anthropic/claude-sonnet-4-20250514"
    letta_embedding: str = "openai/text-embedding-3-small"

    # Vault settings
    obsidian_vault_path: Path | None = None
    obsidian_templates_path: str = "Templates"
    obsidian_daily_notes_path: str = "Calendar/Daily Notes"
    obsidian_daily_note_format: str = "%Y-%m-%d"

    # Agent settings
    agent_max_tool_iterations: int = 10
    agent_tool_call_timeout: float = 30.0
    agent_log_tool_calls: bool = True

    # Scheduler settings
    scheduler_enabled: bool = True
    scheduler_timezone: str = "America/New_York"
    job_daily_note_enabled: bool = True
    job_daily_note_cron: str = "0 6 * * *"
    job_end_of_day_sync_enabled: bool = True
    job_end_of_day_sync_cron: str = "55 23 * * *"
    job_weekly_review_enabled: bool = True
    job_weekly_review_cron: str = "0 18 * * 0"

    # Integration tokens (from env)
    todoist_api_token: str | None = None

    # Private attributes for parsed values
    _allowed_user_ids_set: set[int] = PrivateAttr(default_factory=set)
    _mcp_servers: list[MCPServerConfig] = PrivateAttr(default_factory=list)
    _toml_loaded: bool = PrivateAttr(default=False)

    # ---------------------------------------------------------------------------
    # Validators
    # ---------------------------------------------------------------------------

    @field_validator("log_level", mode="after")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Ensure log level is valid."""
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        v = v.upper()
        if v not in valid_levels:
            return "INFO"
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

    @field_validator("allowed_user_ids", mode="before")
    @classmethod
    def filter_placeholder_allowed_user_ids(cls, v: str | None) -> str:
        """Filter out placeholder values from allowed_user_ids."""
        if v is None:
            return ""
        if "#" in v:
            v = v.split("#")[0]
        v = v.strip()
        if v == "your_discord_user_id_here":
            return ""
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

    @model_validator(mode="after")
    def parse_and_validate_allowlist(self) -> ErebusConfig:
        """Parse allowed_user_ids string and ensure primary user is included."""
        parsed: set[int] = set()
        if self.allowed_user_ids:
            for id_str in self.allowed_user_ids.split(","):
                id_str = id_str.strip()
                if id_str:
                    try:
                        parsed.add(int(id_str))
                    except ValueError:
                        pass
        parsed.add(self.discord_user_id)
        self._allowed_user_ids_set = parsed
        return self

    # ---------------------------------------------------------------------------
    # Computed Properties (nested config objects)
    # ---------------------------------------------------------------------------

    @property
    def discord(self) -> DiscordConfig:
        """Get Discord configuration as a structured object."""
        return DiscordConfig(
            bot_token=self.discord_bot_token,
            user_id=self.discord_user_id,
            guild_id=self.discord_guild_id,
            allowed_user_ids=frozenset(self._allowed_user_ids_set),
        )

    @property
    def letta(self) -> LettaConfig:
        """Get Letta configuration as a structured object."""
        return LettaConfig(
            api_url=self.letta_api_url,
            api_key=self.letta_api_key,
            model=self.letta_model,
            embedding=self.letta_embedding,
        )

    @property
    def vault(self) -> VaultConfig:
        """Get vault configuration as a structured object."""
        return VaultConfig(
            root=self.obsidian_vault_path.resolve() if self.obsidian_vault_path else None,
            templates_path=self.obsidian_templates_path,
            daily_notes_path=self.obsidian_daily_notes_path,
            daily_note_format=self.obsidian_daily_note_format,
        )

    @property
    def agent(self) -> AgentConfig:
        """Get agent configuration as a structured object."""
        return AgentConfig(
            max_tool_iterations=self.agent_max_tool_iterations,
            tool_call_timeout=self.agent_tool_call_timeout,
            log_tool_calls=self.agent_log_tool_calls,
        )

    @property
    def scheduler(self) -> SchedulerConfig:
        """Get scheduler configuration as a structured object."""
        return SchedulerConfig(
            enabled=self.scheduler_enabled,
            timezone=self.scheduler_timezone,
            jobs=SchedulerJobsConfig(
                daily_note=JobConfig(
                    enabled=self.job_daily_note_enabled,
                    cron=self.job_daily_note_cron,
                ),
                end_of_day_sync=JobConfig(
                    enabled=self.job_end_of_day_sync_enabled,
                    cron=self.job_end_of_day_sync_cron,
                ),
                weekly_review=JobConfig(
                    enabled=self.job_weekly_review_enabled,
                    cron=self.job_weekly_review_cron,
                ),
            ),
        )

    @property
    def mcp_servers(self) -> list[MCPServerConfig]:
        """Get MCP server configurations."""
        return self._mcp_servers

    # ---------------------------------------------------------------------------
    # Convenience Properties
    # ---------------------------------------------------------------------------

    @property
    def is_development(self) -> bool:
        """Check if running in development mode."""
        return self.environment == Environment.DEVELOPMENT

    @property
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return self.environment == Environment.PRODUCTION

    def is_user_allowed(self, user_id: int) -> bool:
        """Check if a user ID is in the allowed list."""
        return user_id in self._allowed_user_ids_set


def _load_toml_config() -> dict[str, Any]:
    """Load configuration from config.toml if it exists.

    Returns:
        Dictionary of configuration values, or empty dict if file doesn't exist.
    """
    if not _CONFIG_FILE.exists():
        logger.debug(f"No config file found at {_CONFIG_FILE}, using defaults")
        return {}

    try:
        with open(_CONFIG_FILE, "rb") as f:
            data = tomllib.load(f)
        logger.info(f"Loaded configuration from {_CONFIG_FILE}")
        return data
    except Exception as e:
        logger.warning(f"Failed to load {_CONFIG_FILE}: {e}")
        return {}


def _parse_mcp_servers(data: dict[str, Any], todoist_token: str | None) -> list[MCPServerConfig]:
    """Parse MCP server configurations from TOML.

    Also auto-configures Todoist if token is available but not in config.

    Args:
        data: Parsed TOML data.
        todoist_token: Todoist API token from environment.

    Returns:
        List of MCP server configurations.
    """
    servers: list[MCPServerConfig] = []
    mcp_data = data.get("mcp", {})
    server_list = mcp_data.get("servers", [])

    for server in server_list:
        if not isinstance(server, dict):
            continue
        name = server.get("name")
        command = server.get("command")
        if not name or not command:
            logger.warning(f"Skipping MCP server config missing name or command: {server}")
            continue

        servers.append(
            MCPServerConfig(
                name=name,
                command=command,
                args=server.get("args", []),
                env=server.get("env", {}),
            )
        )

    # Auto-configure Todoist if token available but not in config
    if todoist_token and not any(s.name == "todoist" for s in servers):
        servers.append(
            MCPServerConfig(
                name="todoist",
                command="npx",
                args=["@doist/todoist-ai"],
                env={
                    "TODOIST_API_KEY": todoist_token,
                    "DOTENV_CONFIG_QUIET": "true",
                },
            )
        )
        logger.debug("Auto-configured Todoist MCP server from TODOIST_API_TOKEN")

    return servers


@lru_cache
def get_config() -> ErebusConfig:
    """Get cached application configuration.

    Loads configuration from:
    1. Environment variables (via pydantic-settings)
    2. config.toml (for MCP server configurations only)

    Note: TOML is only used for MCP server configuration which requires
    array syntax. All other settings come from environment variables
    (loaded from .env file).

    Returns:
        Validated ErebusConfig instance.
    """
    # Load TOML config (used only for MCP servers)
    toml_data = _load_toml_config()

    # Create config from environment variables
    config = ErebusConfig()

    # Parse MCP servers from TOML
    config._mcp_servers = _parse_mcp_servers(toml_data, config.todoist_api_token)
    config._toml_loaded = bool(toml_data)

    return config


def clear_config_cache() -> None:
    """Clear the cached configuration.

    Useful for testing or when configuration needs to be reloaded.
    """
    get_config.cache_clear()


# Re-export commonly used items
__all__ = [
    "ErebusConfig",
    "Environment",
    "MCPServerConfig",
    "DiscordConfig",
    "LettaConfig",
    "VaultConfig",
    "AgentConfig",
    "SchedulerConfig",
    "SchedulerJobsConfig",
    "JobConfig",
    "get_config",
    "clear_config_cache",
]
