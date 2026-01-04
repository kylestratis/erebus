"""Scheduler for managing and running scheduled jobs.

Uses APScheduler to run jobs at configured times with cron-like scheduling.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from apscheduler.jobstores.base import JobLookupError
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from bot.scheduler.base import JobContext, JobResult, JobStatus, ScheduledJob

if TYPE_CHECKING:
    import discord

    from agents import ConversationManager, MCPClientManager
    from agents.vault import Vault
    from bot.config import Settings

logger = logging.getLogger(__name__)


class Scheduler:
    """Manages scheduled jobs for Erebus.

    Handles job registration, scheduling, and execution using APScheduler.
    Jobs receive a context with access to bot resources.

    Example:
        scheduler = Scheduler(config)
        scheduler.register(DailyNoteJob())
        scheduler.register(EndOfDaySyncJob())

        # Set resources when available
        scheduler.set_resources(
            conversation_manager=bot.conversation_manager,
            vault=bot.vault,
            mcp=bot.mcp,
        )

        # Start the scheduler
        await scheduler.start()

        # Fetch discord user and enable DMs
        user = await bot.fetch_user(config.discord_user_id)
        scheduler.set_discord_user(user)

    Attributes:
        config: Bot configuration.
        jobs: Dictionary of registered jobs by name.
        history: Recent job execution history.
    """

    def __init__(
        self,
        config: Settings,
        timezone: str = "America/Chicago",
        max_history: int = 100,
    ) -> None:
        """Initialize the scheduler.

        Args:
            config: Bot configuration.
            timezone: Timezone for cron schedules (default: America/Chicago).
            max_history: Maximum number of job results to keep in history.
        """
        self.config = config
        self.timezone = timezone
        self.max_history = max_history

        self._scheduler = AsyncIOScheduler(timezone=timezone)
        self._jobs: dict[str, ScheduledJob] = {}
        self._history: list[tuple[str, JobResult]] = []

        # Resources set later via set_resources()
        self._conversation_manager: ConversationManager | None = None
        self._vault: Vault | None = None
        self._mcp: MCPClientManager | None = None
        self._discord_user: discord.User | None = None

        self._running = False

    @property
    def jobs(self) -> dict[str, ScheduledJob]:
        """Get registered jobs."""
        return self._jobs.copy()

    @property
    def history(self) -> list[tuple[str, JobResult]]:
        """Get job execution history (job_name, result)."""
        return self._history.copy()

    @property
    def is_running(self) -> bool:
        """Check if scheduler is running."""
        return self._running

    def set_resources(
        self,
        conversation_manager: ConversationManager | None = None,
        vault: Vault | None = None,
        mcp: MCPClientManager | None = None,
    ) -> None:
        """Set shared resources that jobs can access.

        Args:
            conversation_manager: AI conversation interface.
            vault: Obsidian vault interface.
            mcp: MCP client manager.
        """
        self._conversation_manager = conversation_manager
        self._vault = vault
        self._mcp = mcp
        logger.info(
            f"Scheduler resources updated: "
            f"ai={conversation_manager is not None}, "
            f"vault={vault is not None}, "
            f"mcp={mcp is not None}"
        )

    def set_discord_user(self, user: discord.User | None) -> None:
        """Set the Discord user for sending DMs.

        Args:
            user: Discord user to send messages to.
        """
        self._discord_user = user
        if user:
            logger.info(f"Scheduler Discord user set: {user}")

    def _build_context(self) -> JobContext:
        """Build a job context with current resources."""
        return JobContext(
            config=self.config,
            conversation_manager=self._conversation_manager,
            vault=self._vault,
            mcp=self._mcp,
            discord_user=self._discord_user,
        )

    def register(self, job: ScheduledJob) -> None:
        """Register a job with the scheduler.

        Args:
            job: The job to register.

        Raises:
            ValueError: If a job with the same name is already registered.
        """
        if job.name in self._jobs:
            raise ValueError(f"Job {job.name!r} is already registered")

        self._jobs[job.name] = job
        logger.info(f"Registered job: {job}")

        # If scheduler is already running, add the job immediately
        if self._running and job.cron and job.enabled:
            self._schedule_job(job)

    def unregister(self, job_name: str) -> bool:
        """Unregister a job by name.

        Args:
            job_name: Name of the job to remove.

        Returns:
            True if job was found and removed.
        """
        if job_name not in self._jobs:
            return False

        # Remove from APScheduler
        try:
            self._scheduler.remove_job(job_name)
        except JobLookupError:
            pass  # Job not scheduled, expected

        del self._jobs[job_name]
        logger.info(f"Unregistered job: {job_name}")
        return True

    def enable_job(self, job_name: str) -> bool:
        """Enable a job.

        Args:
            job_name: Name of the job to enable.

        Returns:
            True if job was found and enabled.
        """
        job = self._jobs.get(job_name)
        if not job:
            return False

        job.enabled = True
        if self._running and job.cron:
            self._schedule_job(job)
        logger.info(f"Enabled job: {job_name}")
        return True

    def disable_job(self, job_name: str) -> bool:
        """Disable a job.

        Args:
            job_name: Name of the job to disable.

        Returns:
            True if job was found and disabled.
        """
        job = self._jobs.get(job_name)
        if not job:
            return False

        job.enabled = False
        try:
            self._scheduler.remove_job(job_name)
        except JobLookupError:
            pass  # Job not scheduled, expected
        logger.info(f"Disabled job: {job_name}")
        return True

    def _schedule_job(self, job: ScheduledJob) -> None:
        """Schedule a job with APScheduler.

        Args:
            job: The job to schedule.
        """
        if not job.cron:
            logger.debug(f"Job {job.name} has no cron schedule, skipping")
            return

        # Parse cron expression
        try:
            trigger = CronTrigger.from_crontab(job.cron, timezone=self.timezone)
        except ValueError as e:
            logger.error(f"Invalid cron expression for job {job.name}: {job.cron} - {e}")
            return

        # Add job to scheduler
        self._scheduler.add_job(
            self._run_job,
            trigger=trigger,
            args=[job.name],
            id=job.name,
            name=job.name,
            replace_existing=True,
        )
        logger.info(f"Scheduled job {job.name} with cron: {job.cron}")

    async def _run_job(self, job_name: str) -> None:
        """Execute a job and record the result.

        Args:
            job_name: Name of the job to run.
        """
        job = self._jobs.get(job_name)
        if not job:
            logger.error(f"Job {job_name} not found")
            return

        if not job.enabled:
            logger.debug(f"Job {job_name} is disabled, skipping")
            return

        logger.info(f"Running job: {job_name}")
        result = JobResult(status=JobStatus.FAILED, message="Unknown error")

        try:
            # Set context with current resources
            context = self._build_context()
            job.set_context(context)

            # Run the job
            result = await job.run()
            if result.completed_at is None:
                result.completed_at = datetime.now(UTC)

        except Exception as e:
            logger.exception(f"Job {job_name} raised an exception")
            result = JobResult.failed(f"Exception: {e}", error=e)
            result.completed_at = datetime.now(UTC)

        # Log result
        duration = result.duration_seconds or 0
        if result.status == JobStatus.SUCCESS:
            logger.info(f"Job {job_name} completed: {result.message} ({duration:.2f}s)")
        elif result.status == JobStatus.SKIPPED:
            logger.info(f"Job {job_name} skipped: {result.message}")
        else:
            logger.error(f"Job {job_name} failed: {result.message}")

        # Record in history
        self._history.append((job_name, result))
        if len(self._history) > self.max_history:
            self._history = self._history[-self.max_history :]

    async def run_now(self, job_name: str) -> JobResult | None:
        """Run a job immediately (manual trigger).

        Args:
            job_name: Name of the job to run.

        Returns:
            The job result, or None if job not found.
        """
        if job_name not in self._jobs:
            logger.error(f"Cannot run unknown job: {job_name}")
            return None

        await self._run_job(job_name)

        # Return the most recent result for this job
        for name, result in reversed(self._history):
            if name == job_name:
                return result
        return None

    async def start(self) -> None:
        """Start the scheduler.

        Schedules all enabled jobs with cron expressions.
        """
        if self._running:
            logger.warning("Scheduler already running")
            return

        # Schedule all enabled jobs
        for job in self._jobs.values():
            if job.enabled and job.cron:
                self._schedule_job(job)

        self._scheduler.start()
        self._running = True
        logger.info(f"Scheduler started with {len(self._jobs)} registered jobs")

    async def stop(self) -> None:
        """Stop the scheduler."""
        if not self._running:
            return

        self._scheduler.shutdown(wait=False)
        self._running = False
        logger.info("Scheduler stopped")

    def get_next_run_time(self, job_name: str) -> datetime | None:
        """Get the next scheduled run time for a job.

        Args:
            job_name: Name of the job.

        Returns:
            Next run time, or None if not scheduled.
        """
        try:
            apscheduler_job = self._scheduler.get_job(job_name)
            if apscheduler_job:
                return apscheduler_job.next_run_time
        except Exception:
            pass
        return None

    def get_status(self) -> dict:
        """Get scheduler status summary.

        Returns:
            Dictionary with scheduler state and job info.
        """
        jobs_info = []
        for name, job in self._jobs.items():
            next_run = self.get_next_run_time(name)
            jobs_info.append(
                {
                    "name": name,
                    "description": job.description,
                    "cron": job.cron,
                    "enabled": job.enabled,
                    "next_run": next_run.isoformat() if next_run else None,
                }
            )

        # Recent history (last 10)
        recent = []
        for job_name, result in self._history[-10:]:
            recent.append(
                {
                    "job": job_name,
                    "status": result.status.value,
                    "message": result.message,
                    "started_at": result.started_at.isoformat(),
                }
            )

        return {
            "running": self._running,
            "timezone": self.timezone,
            "jobs": jobs_info,
            "recent_history": recent,
        }
