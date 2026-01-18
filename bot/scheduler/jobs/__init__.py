"""Scheduled job implementations for Erebus.

Each job is a standalone automation task that runs on a schedule.
"""

from bot.scheduler.jobs.daily_note import DailyNoteJob
from bot.scheduler.jobs.end_of_day_sync import EndOfDaySyncJob
from bot.scheduler.jobs.erebus_journal import ErebusJournalJob
from bot.scheduler.jobs.weekly_review import WeeklyReviewJob

__all__ = [
    "DailyNoteJob",
    "EndOfDaySyncJob",
    "ErebusJournalJob",
    "WeeklyReviewJob",
]
