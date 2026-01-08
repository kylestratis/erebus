"""Daily note auto-generation job.

Generates the daily note at a configured time (default: 6am) and sends
a morning briefing DM to the user.
"""

from __future__ import annotations

import asyncio
import logging

from bot.scheduler.base import JobResult, ScheduledJob

logger = logging.getLogger(__name__)

# Timeout for AI operations (seconds)
AI_TIMEOUT = 120.0

# Prompt for daily note generation (matches /daily command)
DAILY_NOTE_PROMPT = """Execute my daily planning workflow:

1. **Determine today's date** (YYYY-MM-DD format)

2. **Check if today's daily note exists**
   - Use vault_get_daily_note to check
   - If it doesn't exist, create it with vault_create_daily_note (uses template automatically)

3. **Fetch tasks from Todoist**
   - Use todoist_find-tasks to get tasks due today
   - Include overdue tasks

4. **Update the daily note**
   - If Tasks section needs updating, add/update tasks
   - Format: `- [ ] Task name (@todoist-TASK_ID)`
   - Preserve ALL existing content in the note (user may have added sections)
   - Write the FULL note content back, never partial

5. **Provide a brief summary:**
   - Path to the daily note
   - Total tasks for today
   - Number of overdue items
   - Top 3 priorities (if identifiable)

Keep it concise."""

# Prompt for morning briefing
MORNING_BRIEFING_PROMPT = """Generate a concise morning briefing for me.

1. **Check today's daily note** using vault_get_daily_note
2. **Review tasks** from the Tasks section
3. **Summarize** in this format:

**Good morning!** Here's your day at a glance:

**Tasks Today:** [count]
- [Top 3 tasks with priorities]

**Overdue:** [count if any]

**Focus:** [One sentence on what seems most important based on priorities/deadlines]

Keep it brief and actionable. If no daily note exists, just say so."""


class DailyNoteJob(ScheduledJob):
    """Generates daily note and sends morning briefing.

    This job runs in the morning (default 6am) to:
    1. Create or update today's daily note with Todoist tasks
    2. Send a morning briefing DM to the user

    Requires:
    - AI (eidolon)
    - Vault
    - MCP (for Todoist)
    - Discord user (for DM)
    """

    name = "daily_note"
    description = "Generate daily note and send morning briefing"
    cron = "0 6 * * *"  # Default: 6:00 AM daily

    async def run(self) -> JobResult:
        """Execute the daily note workflow."""
        # Check prerequisites
        if not self.context.has_ai:
            return JobResult.skipped("AI not configured")

        if not self.context.has_vault:
            return JobResult.skipped("Vault not configured")

        # Generate daily note
        try:
            logger.info("Generating daily note...")
            response = await asyncio.wait_for(
                self.chat(DAILY_NOTE_PROMPT),
                timeout=AI_TIMEOUT,
            )

            if not response:
                return JobResult.failed("AI returned no response for daily note")

            logger.info("Daily note generated successfully")

        except TimeoutError:
            return JobResult.failed("Daily note generation timed out")
        except Exception as e:
            logger.exception("Failed to generate daily note")
            return JobResult.failed(f"Daily note generation failed: {e}", error=e)

        # Send morning briefing if we can
        briefing_sent = False
        if self.context.can_send_dm:
            try:
                logger.info("Generating morning briefing...")
                briefing = await asyncio.wait_for(
                    self.chat(MORNING_BRIEFING_PROMPT),
                    timeout=AI_TIMEOUT,
                )

                if briefing:
                    briefing_sent = await self.send_dm(briefing)
                    if briefing_sent:
                        logger.info("Morning briefing sent")
                    else:
                        logger.warning("Failed to send morning briefing DM")

            except TimeoutError:
                logger.warning("Morning briefing generation timed out")
            except Exception as e:
                logger.exception(f"Failed to generate morning briefing: {e}")
        else:
            logger.info("Skipping morning briefing: no Discord user configured")

        return JobResult.success(
            "Daily note generated" + (" and briefing sent" if briefing_sent else ""),
            briefing_sent=briefing_sent,
        )
