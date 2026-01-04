"""Scheduled job framework for Erebus.

Provides an abstraction for time-based automation jobs that can interact
with the AI model, vault, and Discord.
"""

from bot.scheduler.base import JobContext, JobResult, ScheduledJob
from bot.scheduler.scheduler import Scheduler

__all__ = [
    "JobContext",
    "JobResult",
    "ScheduledJob",
    "Scheduler",
]
