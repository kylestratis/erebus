"""Tests for the scheduler module."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.scheduler.base import JobContext, JobResult, JobStatus, ScheduledJob


class DummyJob(ScheduledJob):
    """Test job implementation."""

    name = "dummy_job"
    description = "A test job"
    cron = "0 * * * *"  # Every hour

    def __init__(self, result: JobResult | None = None) -> None:
        super().__init__()
        self._result = result or JobResult.success("Test completed")

    async def run(self) -> JobResult:
        return self._result


class FailingJob(ScheduledJob):
    """Job that raises an exception."""

    name = "failing_job"
    cron = "0 * * * *"

    async def run(self) -> JobResult:
        raise ValueError("Intentional failure")


class TestJobResult:
    """Tests for JobResult class."""

    def test_success_result(self) -> None:
        """Success result should have correct status."""
        result = JobResult.success("All good", count=5)
        assert result.status == JobStatus.SUCCESS
        assert result.message == "All good"
        assert result.data == {"count": 5}
        assert result.error is None

    def test_failed_result(self) -> None:
        """Failed result should capture error."""
        error = ValueError("Something broke")
        result = JobResult.failed("Bad thing happened", error=error)
        assert result.status == JobStatus.FAILED
        assert result.message == "Bad thing happened"
        assert result.error is error

    def test_skipped_result(self) -> None:
        """Skipped result should have correct status."""
        result = JobResult.skipped("Nothing to do")
        assert result.status == JobStatus.SKIPPED
        assert result.message == "Nothing to do"

    def test_duration_calculation(self) -> None:
        """Duration should be calculated when completed."""
        result = JobResult.success("Done")
        assert result.duration_seconds is None

        result.completed_at = datetime.now(UTC)
        assert result.duration_seconds is not None
        assert result.duration_seconds >= 0


class TestJobContext:
    """Tests for JobContext class."""

    def test_has_ai_property(self) -> None:
        """has_ai should reflect conversation_manager presence."""
        config = MagicMock()

        context = JobContext(config=config, conversation_manager=None)
        assert context.has_ai is False

        context = JobContext(config=config, conversation_manager=MagicMock())
        assert context.has_ai is True

    def test_has_vault_property(self) -> None:
        """has_vault should reflect vault presence."""
        config = MagicMock()

        context = JobContext(config=config, vault=None)
        assert context.has_vault is False

        context = JobContext(config=config, vault=MagicMock())
        assert context.has_vault is True

    def test_has_mcp_property(self) -> None:
        """has_mcp should reflect MCP presence."""
        config = MagicMock()

        context = JobContext(config=config, mcp=None)
        assert context.has_mcp is False

        context = JobContext(config=config, mcp=MagicMock())
        assert context.has_mcp is True

    def test_can_send_dm_property(self) -> None:
        """can_send_dm should reflect discord_user presence."""
        config = MagicMock()

        context = JobContext(config=config, discord_user=None)
        assert context.can_send_dm is False

        context = JobContext(config=config, discord_user=MagicMock())
        assert context.can_send_dm is True


class TestScheduledJob:
    """Tests for ScheduledJob base class."""

    def test_context_not_set_raises_error(self) -> None:
        """Accessing context before set should raise error."""
        job = DummyJob()
        with pytest.raises(RuntimeError, match="context not set"):
            _ = job.context

    def test_set_context(self) -> None:
        """set_context should make context accessible."""
        job = DummyJob()
        context = JobContext(config=MagicMock())
        job.set_context(context)
        assert job.context is context

    def test_repr(self) -> None:
        """String representation should include key info."""
        job = DummyJob()
        assert "dummy_job" in repr(job)
        assert "enabled" in repr(job)

        job.enabled = False
        assert "disabled" in repr(job)

    async def test_send_dm_without_user(self) -> None:
        """send_dm should return False if no user."""
        job = DummyJob()
        context = JobContext(config=MagicMock(), discord_user=None)
        job.set_context(context)

        result = await job.send_dm("Hello")
        assert result is False

    async def test_send_dm_with_user(self) -> None:
        """send_dm should send message to user."""
        job = DummyJob()
        mock_user = AsyncMock()
        context = JobContext(config=MagicMock(), discord_user=mock_user)
        job.set_context(context)

        result = await job.send_dm("Hello")
        assert result is True
        mock_user.send.assert_called_once_with("Hello")

    async def test_chat_without_ai(self) -> None:
        """chat should return None if no AI."""
        job = DummyJob()
        context = JobContext(config=MagicMock(), conversation_manager=None)
        job.set_context(context)

        result = await job.chat("Hello")
        assert result is None

    async def test_chat_with_ai(self) -> None:
        """chat should call conversation manager."""
        job = DummyJob()
        mock_cm = AsyncMock()
        mock_cm.chat.return_value.content = "AI response"
        mock_config = MagicMock()
        mock_config.discord_user_id = 12345

        context = JobContext(config=mock_config, conversation_manager=mock_cm)
        job.set_context(context)

        result = await job.chat("Hello")
        assert result == "AI response"
        mock_cm.chat.assert_called_once_with(user_id=12345, message="Hello")


class TestScheduler:
    """Tests for Scheduler class."""

    @pytest.fixture
    def mock_config(self) -> MagicMock:
        """Create mock config."""
        config = MagicMock()
        config.discord_user_id = 12345
        return config

    def test_register_job(self, mock_config: MagicMock) -> None:
        """Register should add job to scheduler."""
        from bot.scheduler import Scheduler

        scheduler = Scheduler(mock_config)
        job = DummyJob()

        scheduler.register(job)
        assert "dummy_job" in scheduler.jobs
        assert scheduler.jobs["dummy_job"] is job

    def test_register_duplicate_raises(self, mock_config: MagicMock) -> None:
        """Registering duplicate job name should raise error."""
        from bot.scheduler import Scheduler

        scheduler = Scheduler(mock_config)
        scheduler.register(DummyJob())

        with pytest.raises(ValueError, match="already registered"):
            scheduler.register(DummyJob())

    def test_unregister_job(self, mock_config: MagicMock) -> None:
        """Unregister should remove job."""
        from bot.scheduler import Scheduler

        scheduler = Scheduler(mock_config)
        scheduler.register(DummyJob())

        assert scheduler.unregister("dummy_job") is True
        assert "dummy_job" not in scheduler.jobs

    def test_unregister_unknown_returns_false(self, mock_config: MagicMock) -> None:
        """Unregistering unknown job should return False."""
        from bot.scheduler import Scheduler

        scheduler = Scheduler(mock_config)
        assert scheduler.unregister("unknown") is False

    def test_enable_disable_job(self, mock_config: MagicMock) -> None:
        """Enable/disable should toggle job state."""
        from bot.scheduler import Scheduler

        scheduler = Scheduler(mock_config)
        job = DummyJob()
        scheduler.register(job)

        scheduler.disable_job("dummy_job")
        assert job.enabled is False

        scheduler.enable_job("dummy_job")
        assert job.enabled is True

    def test_set_resources(self, mock_config: MagicMock) -> None:
        """set_resources should store resources."""
        from bot.scheduler import Scheduler

        scheduler = Scheduler(mock_config)
        cm = MagicMock()
        vault = MagicMock()
        mcp = MagicMock()

        scheduler.set_resources(conversation_manager=cm, vault=vault, mcp=mcp)

        # Build context and verify resources are included
        context = scheduler._build_context()
        assert context.conversation_manager is cm
        assert context.vault is vault
        assert context.mcp is mcp

    def test_set_discord_user(self, mock_config: MagicMock) -> None:
        """set_discord_user should store user."""
        from bot.scheduler import Scheduler

        scheduler = Scheduler(mock_config)
        user = MagicMock()

        scheduler.set_discord_user(user)
        context = scheduler._build_context()
        assert context.discord_user is user

    async def test_run_now(self, mock_config: MagicMock) -> None:
        """run_now should execute job immediately."""
        from bot.scheduler import Scheduler

        scheduler = Scheduler(mock_config)
        job = DummyJob(JobResult.success("Ran manually"))
        scheduler.register(job)

        result = await scheduler.run_now("dummy_job")
        assert result is not None
        assert result.status == JobStatus.SUCCESS
        assert result.message == "Ran manually"

    async def test_run_now_unknown_job(self, mock_config: MagicMock) -> None:
        """run_now for unknown job should return None."""
        from bot.scheduler import Scheduler

        scheduler = Scheduler(mock_config)
        result = await scheduler.run_now("unknown")
        assert result is None

    async def test_run_job_records_history(self, mock_config: MagicMock) -> None:
        """Running job should record in history."""
        from bot.scheduler import Scheduler

        scheduler = Scheduler(mock_config)
        scheduler.register(DummyJob())

        await scheduler._run_job("dummy_job")

        assert len(scheduler.history) == 1
        job_name, result = scheduler.history[0]
        assert job_name == "dummy_job"
        assert result.status == JobStatus.SUCCESS

    async def test_run_job_handles_exception(self, mock_config: MagicMock) -> None:
        """Running failing job should capture exception."""
        from bot.scheduler import Scheduler

        scheduler = Scheduler(mock_config)
        scheduler.register(FailingJob())

        await scheduler._run_job("failing_job")

        assert len(scheduler.history) == 1
        _, result = scheduler.history[0]
        assert result.status == JobStatus.FAILED
        assert "Intentional failure" in result.message

    async def test_start_stop(self, mock_config: MagicMock) -> None:
        """Start/stop should control scheduler state."""
        from bot.scheduler import Scheduler

        scheduler = Scheduler(mock_config)
        scheduler.register(DummyJob())

        assert scheduler.is_running is False

        await scheduler.start()
        assert scheduler.is_running is True

        await scheduler.stop()
        assert scheduler.is_running is False

    def test_get_status(self, mock_config: MagicMock) -> None:
        """get_status should return scheduler info."""
        from bot.scheduler import Scheduler

        scheduler = Scheduler(mock_config, timezone="America/Chicago")
        scheduler.register(DummyJob())

        status = scheduler.get_status()
        assert status["running"] is False
        assert status["timezone"] == "America/Chicago"
        assert len(status["jobs"]) == 1
        assert status["jobs"][0]["name"] == "dummy_job"


class TestDailyNoteJob:
    """Tests for DailyNoteJob."""

    def test_job_attributes(self) -> None:
        """Job should have correct attributes."""
        from bot.scheduler.jobs import DailyNoteJob

        job = DailyNoteJob()
        assert job.name == "daily_note"
        assert job.cron == "0 6 * * *"
        assert job.enabled is True

    async def test_skips_without_ai(self) -> None:
        """Job should skip if AI not configured."""
        from bot.scheduler.jobs import DailyNoteJob

        job = DailyNoteJob()
        context = JobContext(config=MagicMock(), conversation_manager=None)
        job.set_context(context)

        result = await job.run()
        assert result.status == JobStatus.SKIPPED
        assert "AI not configured" in result.message

    async def test_skips_without_vault(self) -> None:
        """Job should skip if vault not configured."""
        from bot.scheduler.jobs import DailyNoteJob

        job = DailyNoteJob()
        context = JobContext(
            config=MagicMock(),
            conversation_manager=MagicMock(),
            vault=None,
        )
        job.set_context(context)

        result = await job.run()
        assert result.status == JobStatus.SKIPPED
        assert "Vault not configured" in result.message


class TestEndOfDaySyncJob:
    """Tests for EndOfDaySyncJob."""

    def test_job_attributes(self) -> None:
        """Job should have correct attributes."""
        from bot.scheduler.jobs import EndOfDaySyncJob

        job = EndOfDaySyncJob()
        assert job.name == "end_of_day_sync"
        assert job.cron == "55 23 * * *"
        assert job.enabled is True

    async def test_skips_without_mcp(self) -> None:
        """Job should skip if MCP not configured."""
        from bot.scheduler.jobs import EndOfDaySyncJob

        job = EndOfDaySyncJob()
        context = JobContext(
            config=MagicMock(),
            conversation_manager=MagicMock(),
            vault=MagicMock(),
            mcp=None,
        )
        job.set_context(context)

        result = await job.run()
        assert result.status == JobStatus.SKIPPED
        assert "Todoist not configured" in result.message


class TestWeeklyReviewJob:
    """Tests for WeeklyReviewJob."""

    def test_job_attributes(self) -> None:
        """Job should have correct attributes."""
        from bot.scheduler.jobs import WeeklyReviewJob

        job = WeeklyReviewJob()
        assert job.name == "weekly_review"
        assert job.cron == "0 18 * * 0"  # Sunday 6pm
        assert job.enabled is True

    async def test_skips_without_discord_user(self) -> None:
        """Job should skip if no Discord user for DMs."""
        from bot.scheduler.jobs import WeeklyReviewJob

        job = WeeklyReviewJob()
        context = JobContext(config=MagicMock(), discord_user=None)
        job.set_context(context)

        result = await job.run()
        assert result.status == JobStatus.SKIPPED
        assert "no Discord user" in result.message

    async def test_sends_dm_on_success(self) -> None:
        """Job should send DM to user."""
        from bot.scheduler.jobs import WeeklyReviewJob

        job = WeeklyReviewJob()
        mock_user = AsyncMock()
        context = JobContext(config=MagicMock(), discord_user=mock_user)
        job.set_context(context)

        result = await job.run()
        assert result.status == JobStatus.SUCCESS
        mock_user.send.assert_called_once()
        sent_message = mock_user.send.call_args[0][0]
        assert "Weekly Review" in sent_message
