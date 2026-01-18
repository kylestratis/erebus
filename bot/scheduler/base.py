"""Base classes for scheduled jobs.

Defines the ScheduledJob abstraction and supporting types for building
time-based automation tasks.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import discord

    from agents import MCPClientManager
    from agents.eidolon import EidolonMemory
    from agents.vault import Vault
    from config import ErebusConfig

logger = logging.getLogger(__name__)


class JobStatus(str, Enum):
    """Status of a job execution."""

    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class JobResult:
    """Result of a scheduled job execution.

    Attributes:
        status: Whether the job succeeded, failed, or was skipped.
        message: Human-readable summary of what happened.
        data: Optional structured data from the job.
        error: Exception if the job failed.
        started_at: When the job started.
        completed_at: When the job finished.
    """

    status: JobStatus
    message: str
    data: dict[str, Any] = field(default_factory=dict)
    error: Exception | None = None
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None

    @classmethod
    def success(cls, message: str, **data: Any) -> JobResult:
        """Create a successful result."""
        return cls(status=JobStatus.SUCCESS, message=message, data=data)

    @classmethod
    def failed(cls, message: str, error: Exception | None = None, **data: Any) -> JobResult:
        """Create a failed result."""
        return cls(status=JobStatus.FAILED, message=message, error=error, data=data)

    @classmethod
    def skipped(cls, message: str, **data: Any) -> JobResult:
        """Create a skipped result (e.g., nothing to do)."""
        return cls(status=JobStatus.SKIPPED, message=message, data=data)

    @property
    def duration_seconds(self) -> float | None:
        """Get duration in seconds if completed."""
        if self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None


@dataclass
class JobContext:
    """Context provided to scheduled jobs for execution.

    Contains references to all the bot's resources that a job might need.

    Attributes:
        config: Bot configuration settings.
        eidolon: EidolonMemory instance for AI capabilities (may be None).
        vault: Obsidian vault interface (may be None).
        mcp: MCP client manager for integrations (may be None).
        discord_user: Discord user to send messages to (may be None).
    """

    config: ErebusConfig
    eidolon: EidolonMemory | None = None
    vault: Vault | None = None
    mcp: MCPClientManager | None = None
    discord_user: discord.User | None = None

    @property
    def has_ai(self) -> bool:
        """Check if AI capabilities are available."""
        return self.eidolon is not None

    @property
    def has_vault(self) -> bool:
        """Check if vault is configured."""
        return self.vault is not None

    @property
    def has_mcp(self) -> bool:
        """Check if MCP integrations are available."""
        return self.mcp is not None

    @property
    def can_send_dm(self) -> bool:
        """Check if we can send Discord DMs."""
        return self.discord_user is not None


class ScheduledJob(ABC):
    """Base class for scheduled jobs.

    Subclasses must implement:
    - `name`: Human-readable job name
    - `run()`: The job logic

    Jobs can access bot resources through the `context` attribute after
    `set_context()` is called by the scheduler.

    Example:
        class MyJob(ScheduledJob):
            name = "my_job"
            cron = "0 6 * * *"  # Every day at 6am

            async def run(self) -> JobResult:
                if not self.context.has_vault:
                    return JobResult.skipped("Vault not configured")

                # Do work...
                return JobResult.success("Did the thing")
    """

    # Job identification
    name: str = "unnamed_job"
    description: str = ""

    # Schedule (cron expression: minute hour day month day_of_week)
    # Set to None to disable by default
    cron: str | None = None

    # Whether job is enabled (can be toggled at runtime)
    enabled: bool = True

    def __init__(self) -> None:
        """Initialize the job."""
        self._context: JobContext | None = None

    @property
    def context(self) -> JobContext:
        """Get the job context.

        Raises:
            RuntimeError: If context hasn't been set.
        """
        if self._context is None:
            raise RuntimeError(f"Job {self.name} context not set. Call set_context() first.")
        return self._context

    def set_context(self, context: JobContext) -> None:
        """Set the job context.

        Called by the scheduler before running the job.

        Args:
            context: The execution context.
        """
        self._context = context

    @abstractmethod
    async def run(self) -> JobResult:
        """Execute the job.

        Returns:
            Result of the job execution.
        """
        ...

    async def send_dm(self, content: str) -> bool:
        """Send a DM to the configured user.

        Args:
            content: Message content to send.

        Returns:
            True if message was sent successfully.
        """
        if not self.context.can_send_dm:
            logger.warning(f"Job {self.name} cannot send DM: no discord_user configured")
            return False

        try:
            await self.context.discord_user.send(content)
            return True
        except Exception as e:
            logger.exception(f"Job {self.name} failed to send DM: {e}")
            return False

    async def chat(self, message: str, user_id: int | None = None) -> str | None:
        """Send a message to the AI and get a response.

        Args:
            message: The message/prompt to send.
            user_id: Optional user ID for conversation context.

        Returns:
            The AI's response content, or None if unavailable.
        """
        if not self.context.has_ai:
            logger.warning(f"Job {self.name} cannot chat: AI not configured")
            return None

        try:
            # Use the primary user ID if not specified
            if user_id is None:
                user_id = self.context.config.discord_user_id

            response = await self.context.eidolon.chat(
                user_id=user_id,
                message=message,
                timezone=self.context.config.scheduler_timezone,
            )
            return response
        except Exception as e:
            logger.exception(f"Job {self.name} AI chat failed: {e}")
            return None

    def __repr__(self) -> str:
        """String representation."""
        status = "enabled" if self.enabled else "disabled"
        schedule = self.cron or "no schedule"
        return f"<{self.__class__.__name__} name={self.name!r} {status} ({schedule})>"
