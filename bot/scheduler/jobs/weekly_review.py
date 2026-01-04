"""Weekly review prompt job.

Sends a reminder to start the weekly review on a configured day/time
(default: Sunday 6pm).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from bot.scheduler.base import JobResult, ScheduledJob

logger = logging.getLogger(__name__)

# Timeout for AI operations (seconds)
AI_TIMEOUT = 60.0

# Prompt to generate weekly review context
WEEKLY_PREP_PROMPT = """Prepare a brief preview for my weekly review.

Look at:
1. **This week's daily notes** (use vault operations)
2. **Task completion rate** if visible from notes

Generate a brief message like:

**Weekly Review Time** 🗓️

Here's a quick preview of your week:

**Days tracked:** [count of daily notes this week]
**Tasks visible:** [rough estimate if you can see them]

When you're ready, use `/weekly` to start the guided review.

Keep it very brief - just enough to set context. If you can't access the vault,
just send the reminder without the preview."""


class WeeklyReviewJob(ScheduledJob):
    """Sends weekly review reminder.

    This job runs weekly (default Sunday 6pm) to:
    1. Optionally gather some context from the week
    2. Send a reminder DM to start the weekly review

    The actual review is done interactively via /weekly command.

    Requires:
    - Discord user (for DM)
    - AI (optional, for context preview)
    - Vault (optional, for context preview)
    """

    name = "weekly_review"
    description = "Send weekly review reminder"
    cron = "0 18 * * 0"  # Default: Sunday 6:00 PM

    async def run(self) -> JobResult:
        """Send the weekly review reminder."""
        # DM is required for this job to be useful
        if not self.context.can_send_dm:
            return JobResult.skipped("Cannot send DM: no Discord user configured")

        message: str | None = None

        # Try to get a context-aware reminder if AI is available
        if self.context.has_ai and self.context.has_vault:
            try:
                logger.info("Generating weekly review preview...")
                message = await asyncio.wait_for(
                    self.chat(WEEKLY_PREP_PROMPT),
                    timeout=AI_TIMEOUT,
                )
            except TimeoutError:
                logger.warning("Weekly preview generation timed out, using fallback")
            except Exception as e:
                logger.exception(f"Failed to generate preview: {e}")

        # Fallback to simple reminder
        if not message:
            now = datetime.now(UTC)
            week_num = now.isocalendar()[1]
            message = (
                f"**Weekly Review Time** 🗓️\n\n"
                f"It's time for your Week {week_num} review!\n\n"
                f"When you're ready, use `/weekly` to start the guided review process.\n\n"
                f"This will help you reflect on the week and set priorities for the next one."
            )

        # Send the reminder
        sent = await self.send_dm(message)
        if sent:
            return JobResult.success("Weekly review reminder sent")
        else:
            return JobResult.failed("Failed to send weekly review reminder")
