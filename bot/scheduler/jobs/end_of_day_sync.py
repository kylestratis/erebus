"""End-of-day sync job.

Performs bidirectional sync between Obsidian and Todoist at the end of each day
and optionally rolls over incomplete tasks.
"""

from __future__ import annotations

import asyncio
import logging

from bot.scheduler.base import JobResult, ScheduledJob

logger = logging.getLogger(__name__)

# Timeout for AI operations (seconds)
AI_TIMEOUT = 120.0

# Prompt for end-of-day sync (matches /sync command with end-of-day mode)
END_OF_DAY_SYNC_PROMPT = """Synchronize task status between Obsidian and Todoist.

Mode: end-of-day

## Mode-Specific Behavior:

This is an **end-of-day** sync which includes:
- Full bidirectional sync of completion status
- Rollover of incomplete tasks to tomorrow

## Steps:

1. **Read today's daily note**
   - Use vault_get_daily_note to get today's note
   - If no note exists, skip sync

2. **Find completed tasks in Obsidian**
   - Look for `- [x]` items with `(@todoist-TASK_ID)` pattern
   - Extract the task IDs from these completed items

3. **Mark tasks complete in Todoist**
   - Use todoist tools to mark extracted task IDs as complete
   - Report any errors (task not found, already complete, etc.)

4. **Check Todoist for completed tasks**
   - Query Todoist for tasks completed today
   - Find any that are still unchecked in the daily note
   - Update those checkboxes: `- [ ]` → `- [x]`
   - Write the updated note back using vault_write_note

5. **Handle incomplete tasks for rollover**
   - Get or create tomorrow's daily note
   - Find unchecked `- [ ]` items with `(@todoist-TASK_ID)` in today's note
   - Copy them to tomorrow's Tasks section if not already present
   - Do NOT modify the due dates in Todoist (they're already set)

6. **Summary report:**
   - Tasks synced from Obsidian → Todoist (completed)
   - Tasks synced from Todoist → Obsidian (completed)
   - Tasks rolled over to tomorrow
   - Any conflicts or issues

Keep responses concise. Todoist is the source of truth for task metadata."""

# Prompt for end-of-day summary DM
END_OF_DAY_SUMMARY_PROMPT = """Generate a brief end-of-day summary.

1. **Check today's daily note** using vault_get_daily_note
2. **Count completed vs incomplete tasks** in the Tasks section
3. **Summarize** in this format:

**End of Day Summary**

**Completed:** [count] tasks
**Rolling over:** [count] tasks to tomorrow

**Wins:**
- [1-2 notable completions if any]

**Tomorrow's Focus:**
- [1-2 priority items rolling over]

Keep it brief. If no daily note, just say "No activity tracked today."
"""

# Prompt for writing review questions to daily note
DAILY_REVIEW_PROMPT = """Add reflection prompts to today's daily note.

1. **Read today's daily note** using vault_get_daily_note
2. **Analyze the day's activity:**
   - Count completed tasks vs incomplete
   - Note any patterns (what projects had most activity, blockers)
   - Identify if there were unexpected tasks or interruptions

3. **Generate 2-3 personalized reflection questions** based on:
   - If many tasks completed: "What made today productive?"
   - If tasks rolled over: "What blocked [specific task]? What would help tomorrow?"
   - If one project dominated: "How does [project] align with larger goals?"
   - If mixed progress: "What's the ONE thing that would unlock the most tomorrow?"

4. **Add to the daily note:**
   - Read the current content with vault_read_note
   - Look for a `## Reflection` section (create if not exists)
   - Add the questions under `## Reflection` as a bulleted list
   - Use vault_write_note with overwrite=true to save

5. **Format example:**
```markdown
## Reflection

- What made today productive? (You completed 8 tasks!)
- What blocked the API migration? What would help tomorrow?
- How does the Erebus project align with your Q1 goals?
```

Keep questions specific and actionable. Base them on actual tasks and projects from the note.
"""


class EndOfDaySyncJob(ScheduledJob):
    """Performs end-of-day sync and sends summary.

    This job runs at the end of the day (default 11:55pm) to:
    1. Sync task completion bidirectionally
    2. Roll over incomplete tasks to tomorrow
    3. Send an end-of-day summary DM

    Requires:
    - AI (eidolon)
    - Vault
    - MCP (for Todoist)
    - Discord user (for DM, optional)
    """

    name = "end_of_day_sync"
    description = "Sync tasks and rollover incomplete items"
    cron = "55 23 * * *"  # Default: 11:55 PM daily

    async def run(self) -> JobResult:
        """Execute the end-of-day sync workflow."""
        # Check prerequisites
        if not self.context.has_ai:
            return JobResult.skipped("AI not configured")

        if not self.context.has_vault:
            return JobResult.skipped("Vault not configured")

        if not self.context.has_mcp:
            return JobResult.skipped("Todoist not configured")

        # Perform sync
        try:
            logger.info("Running end-of-day sync...")
            response = await asyncio.wait_for(
                self.chat(END_OF_DAY_SYNC_PROMPT),
                timeout=AI_TIMEOUT,
            )

            if not response:
                return JobResult.failed("AI returned no response for sync")

            logger.info("End-of-day sync completed")

        except TimeoutError:
            return JobResult.failed("End-of-day sync timed out")
        except Exception as e:
            logger.exception("Failed to complete end-of-day sync")
            return JobResult.failed(f"Sync failed: {e}", error=e)

        # Add review prompts to daily note
        review_added = False
        try:
            logger.info("Adding reflection prompts to daily note...")
            review_response = await asyncio.wait_for(
                self.chat(DAILY_REVIEW_PROMPT),
                timeout=AI_TIMEOUT,
            )

            if review_response:
                review_added = True
                logger.info("Reflection prompts added to daily note")
            else:
                logger.warning("AI returned no response for review prompts")

        except TimeoutError:
            logger.warning("Review prompt generation timed out")
        except Exception:
            logger.exception("Failed to add review prompts")

        # Send summary DM if we can
        summary_sent = False
        if self.context.can_send_dm:
            try:
                logger.info("Generating end-of-day summary...")
                summary = await asyncio.wait_for(
                    self.chat(END_OF_DAY_SUMMARY_PROMPT),
                    timeout=AI_TIMEOUT,
                )

                if summary:
                    summary_sent = await self.send_dm(summary)
                    if summary_sent:
                        logger.info("End-of-day summary sent")
                    else:
                        logger.warning("Failed to send summary DM")

            except TimeoutError:
                logger.warning("Summary generation timed out")
            except Exception as e:
                logger.exception(f"Failed to generate summary: {e}")
        else:
            logger.info("Skipping summary DM: no Discord user configured")

        # Build result message
        result_parts = ["End-of-day sync complete"]
        if review_added:
            result_parts.append("reflection prompts added")
        if summary_sent:
            result_parts.append("summary sent")

        return JobResult.success(
            ", ".join(result_parts),
            summary_sent=summary_sent,
            review_added=review_added,
        )
