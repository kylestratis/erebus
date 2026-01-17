"""Core bot commands.

Provides essential commands for bot health checking and status monitoring,
as well as workflow commands like /daily.
"""

from __future__ import annotations

import asyncio
import logging
import platform
import sys
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from agents import ModelError, RateLimitError

if TYPE_CHECKING:
    from bot.client import ErebusBot

logger = logging.getLogger(__name__)

# Timeout for workflow commands that involve AI processing
WORKFLOW_TIMEOUT = 120.0

# Input validation limits
MAX_IDEA_TITLE_LENGTH = 100
MAX_TASK_DESCRIPTION_LENGTH = 500

# Daily workflow prompt - instructs the AI to execute the daily note workflow
DAILY_WORKFLOW_PROMPT = """Execute my daily planning workflow:

1. **Determine today's date** (YYYY-MM-DD format)

2. **Check if today's daily note exists**
   - Use vault_get_daily_note to check
   - If it doesn't exist, create it with vault_create_daily_note (uses template automatically)

3. **Query Todoist for relevant tasks:**
   - Use todoist_find-tasks-by-date for tasks due today
   - Use todoist_find-tasks to find overdue and high priority (P1, P2) tasks
   - Group results by project

4. **Update the Tasks section** in the daily note:
   - Use vault_read_note to get the FULL current content
   - IMPORTANT: Preserve ALL existing content including the header (# YYYY-MM-DD Day)
   - Only modify the content between `## Tasks` and the next `##` heading
   - Format tasks as: `- [ ] Task name (@todoist-TASK_ID) [[Project Name]]`
   - Sort by priority, then due date
   - Use vault_write_note with overwrite=true to save the COMPLETE note (header + all sections)

5. **Present summary:**
   - Path to the daily note
   - Total tasks for today
   - Number of overdue items
   - Top 3 priorities

Keep it concise."""

# Idea capture workflow prompt
IDEA_WORKFLOW_PROMPT = """Help me capture a new idea seed.

The user wants to create an idea with title: "{title}"

Follow these steps:

1. **Gather details** (ask the user):
   - Description: What's the idea about? (required)
   - Confidence: low/medium/high (default: low)
   - Could become: task/project/evergreen/article (can be multiple)

2. **Ideation conversation** (2-3 quick exchanges):
   - Ask a clarifying question to develop the idea
   - Explore why it's interesting or valuable
   - Identify potential next steps or open questions

3. **Create the idea file**:
   - Use vault_write_note to create the file at path: Bins/Ideas/{title}.md
   - Use this exact format:

```
---
fileClass: idea
tags:
  - idea
status: seed
confidence: {{confidence}}
could-become:
  - {{could-become items}}
last-reviewed:
converted-to:
created: {{today's date YYYY-MM-DD}}
---

# {{title}}

## The Idea

{{description}}

## Why It's Interesting

{{insights from conversation}}

## Next Steps

- [ ] {{next steps from conversation}}

## Related

-
```

4. **Confirm creation**:
   - Show the file path
   - Brief summary of what was captured

Keep the conversation focused and concise. Ask one question at a time."""

# Capture task workflow prompt
CAPTURE_WORKFLOW_PROMPT = """Help me quickly capture a task.

The user said: "{task_description}"

Follow these steps:

1. **Parse the task input** and extract:
   - Task content (the main task description)
   - Priority: Look for P1/P2/P3/P4 or "urgent"/"high"/"low" (default: P3/normal)
   - Due date: Parse natural language like "today", "tomorrow", "Friday", "next week"
   - Project: Check for project names or keywords
   - Labels: Look for @tags

2. **Create the task in Todoist**:
   - Use todoist_add-tasks with the parsed parameters
   - Priority mapping: P1=1 (urgent), P2=2 (high), P3=3 (normal), P4=4 (low)

3. **Ask about daily note** (brief):
   - Ask if they want to add it to today's daily note
   - If yes, use vault_get_daily_note to check if it exists
   - If note exists, read it, add the task to the Tasks section, and write it back
   - Format: `- [ ] Task name (@todoist-TASK_ID) [[Project]]`

4. **Confirm creation** (concise):
   - Task details (what was created)
   - Todoist task ID
   - Whether added to daily note

Keep it quick and minimal. Don't over-explain."""

# Sync workflow prompt
SYNC_WORKFLOW_PROMPT = """Synchronize task status between Obsidian and Todoist.

Mode: {mode}

## Mode-Specific Behavior:

**quick** (default): Sync completion status bidirectionally, no rollover.
**end-of-day**: Full sync + rollover incomplete tasks to tomorrow.
**project**: Ask which project to sync, then sync only tasks for that project.

## Steps:

1. **Read today's daily note**
   - Use vault_get_daily_note to get today's note
   - If mode is "end-of-day", also read yesterday's note
   - If mode is "project", ask user which project to sync first

2. **Find completed tasks in Obsidian**
   - Look for `- [x]` items with `(@todoist-TASK_ID)` pattern
   - Extract the task IDs from these completed items
   - If mode is "project", filter to tasks matching the selected project

3. **Mark tasks complete in Todoist**
   - Use todoist tools to mark extracted task IDs as complete
   - Report any errors (task not found, already complete, etc.)

4. **Check Todoist for completed tasks**
   - Query Todoist for tasks completed today
   - Find any that are still unchecked in the daily note
   - Update those checkboxes: `- [ ]` → `- [x]`
   - Write the updated note back using vault_write_note

5. **Handle incomplete tasks** (end-of-day mode only):
   - If mode is "end-of-day", ask if user wants to rollover incomplete tasks
   - If yes:
     - Get or create tomorrow's daily note
     - Copy unchecked `- [ ]` items with `(@todoist-TASK_ID)` to tomorrow's Tasks section
     - Optionally reschedule in Todoist

6. **Summary report:**
   - Tasks synced from Obsidian → Todoist (completed)
   - Tasks synced from Todoist → Obsidian (completed)
   - Tasks rolled over (if end-of-day)
   - Any conflicts or issues

Keep responses concise. Todoist is the source of truth for task metadata."""

# Weekly review workflow prompt
WEEKLY_WORKFLOW_PROMPT = """Guide me through my weekly review.

This should feel like a conversation with a trusted chief of staff helping me
reflect on the week and plan ahead. Work through each phase conversationally.

## Phase 1: Mechanical Review
- Ask about key accomplishments and what got completed
- What tasks remain incomplete? What got moved vs. archived?
- Any upcoming hard deadlines to be aware of?

## Phase 2: Emotional Reality Check
Ask these questions one at a time, giving space to reflect:
- What's causing the most unease right now?
- What are you afraid of doing or avoiding?
- What brought the most joy or energy this week?

## Phase 3: Constraint Analysis
Help identify real constraints vs. imagined ones:
- Money: What's the real financial picture?
- Time: What's actually locked in vs. self-imposed?
- Energy: Where is energy being drained vs. gained?
- What could be cut or eliminated?

## Phase 4: Finding Unlocks
Explore opportunities:
- Who could help? What can be delegated or automated?
- What's the 80/20 here? What would unlock everything else?
- What if the opposite of current assumptions were true?

## Phase 5: Energy-Aware Priorities for Next Week
Help set priorities considering:
- What MUST happen (external commitments)
- What unlocks everything else
- What maintains momentum
- What preserves energy and sanity
- Protected recharge time and power hours for deep work

## Outputs
After completing the review:
1. Summarize key insights and decisions
2. Create a weekly review log at `logs/weekly/YYYY-WW.md` using vault_write_note
3. List the top 3-5 priorities for next week

Keep the conversation flowing naturally. Don't rush through phases.
Ask follow-up questions to dig deeper when needed."""

# Journal entry workflow prompt
JOURNAL_WORKFLOW_PROMPT = """Help me add a journal entry to today's daily note.

{entry_context}

## Steps:

1. **Get today's daily note**
   - Use vault_get_daily_note to fetch today's note
   - If it doesn't exist, tell the user to run /daily first

2. **Locate the Journal section**
   - Find the `## Journal` section in the note
   - If no entry text provided, ask: "What would you like to journal about?"

3. **Create the entry**
   - Format: `### HH:MM - [Optional Title]`
   - Use current time in 24-hour format
   - Add the journal content below the heading
   - If the entry seems to have a natural title, use it; otherwise omit

4. **Insert the entry**
   - Add new entries at the TOP of the Journal section (reverse chronological)
   - Keep the "Outside Journals" query section intact below entries
   - Use vault_write_note to save the updated note (with overwrite=true)

5. **Confirm**
   - Show the timestamp
   - Show the first line of content as confirmation
   - Show the path to the daily note

Keep it brief. If user provided entry text, add it directly without asking."""


def is_allowed_user():
    """Check decorator that verifies user is in the whitelist."""

    async def predicate(interaction: discord.Interaction) -> bool:
        bot: ErebusBot = interaction.client  # type: ignore
        if not bot.config.is_user_allowed(interaction.user.id):
            logger.warning(
                f"Rejected command from non-whitelisted user: "
                f"{interaction.user} (ID: {interaction.user.id})"
            )
            return False
        return True

    return app_commands.check(predicate)


def is_dm_channel():
    """Check decorator that verifies command is used in DMs."""

    async def predicate(interaction: discord.Interaction) -> bool:
        if not isinstance(interaction.channel, discord.DMChannel):
            await interaction.response.send_message(
                "This command can only be used in DMs for privacy.",
                ephemeral=True,
            )
            return False
        return True

    return app_commands.check(predicate)


class CoreCog(commands.Cog, name="Core"):
    """Core commands for bot health and status.

    Provides essential functionality like ping, status, and help.
    """

    def __init__(self, bot: ErebusBot) -> None:
        """Initialize the cog.

        Args:
            bot: The Erebus bot instance.
        """
        self.bot = bot

    @app_commands.command(name="ping", description="Check if Erebus is responsive")
    @is_allowed_user()
    async def ping(self, interaction: discord.Interaction) -> None:
        """Simple ping command to verify bot is responsive.

        Args:
            interaction: The Discord interaction.
        """
        latency_ms = round(self.bot.latency * 1000)
        await interaction.response.send_message(
            f"*The darkness responds...*\n\nLatency: **{latency_ms}ms**"
        )
        logger.info(f"Ping from {interaction.user}: {latency_ms}ms")

    @app_commands.command(name="status", description="Show Erebus status and health")
    @is_allowed_user()
    async def status(self, interaction: discord.Interaction) -> None:
        """Show detailed bot status information.

        Args:
            interaction: The Discord interaction.
        """
        embed = discord.Embed(
            title="Erebus Status",
            description="*The void through which all things pass*",
            color=discord.Color.dark_purple(),
            timestamp=datetime.now(UTC),
        )

        # Bot info
        embed.add_field(
            name="Uptime",
            value=self.bot.uptime,
            inline=True,
        )
        embed.add_field(
            name="Latency",
            value=f"{round(self.bot.latency * 1000)}ms",
            inline=True,
        )
        embed.add_field(
            name="Environment",
            value=self.bot.config.environment.value.capitalize(),
            inline=True,
        )

        # System info
        embed.add_field(
            name="Python",
            value=f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            inline=True,
        )
        embed.add_field(
            name="discord.py",
            value=discord.__version__,
            inline=True,
        )
        embed.add_field(
            name="Platform",
            value=platform.system(),
            inline=True,
        )

        # Integration status (placeholders for now)
        integrations = []
        integrations.append("Claude API: Not configured")
        integrations.append("Todoist: Not configured")
        integrations.append("Obsidian MCP: Not configured")
        integrations.append("EidolonMemory: Not configured")

        embed.add_field(
            name="Integrations",
            value="\n".join(integrations),
            inline=False,
        )

        embed.set_footer(text="Erebus - The darkness that works")

        await interaction.response.send_message(embed=embed)
        logger.info(f"Status request from {interaction.user}")

    @app_commands.command(
        name="daily",
        description="Generate or update today's daily note with Todoist tasks",
    )
    @is_allowed_user()
    @is_dm_channel()
    async def daily(self, interaction: discord.Interaction) -> None:
        """Execute the daily planning workflow.

        Creates or updates today's daily note, fetches tasks from Todoist,
        and provides a summary to start the day.

        Args:
            interaction: The Discord interaction.
        """
        # Check prerequisites
        if not self.bot.eidolon:
            await interaction.response.send_message(
                "*Erebus cannot plan without a voice...*\n\n"
                "AI features are disabled. Start Letta server and configure `LETTA_API_URL` to use /daily.",
                ephemeral=True,
            )
            return

        if not self.bot.vault:
            await interaction.response.send_message(
                "*Erebus has no vault to write to...*\n\n"
                "Vault not configured. Set `OBSIDIAN_VAULT_PATH` to use /daily.",
                ephemeral=True,
            )
            return

        # Defer response since this workflow takes time
        await interaction.response.defer(thinking=True)
        logger.info(f"Daily workflow started by {interaction.user}")

        try:
            response = await asyncio.wait_for(
                self.bot.eidolon.chat(
                    user_id=interaction.user.id,
                    message=DAILY_WORKFLOW_PROMPT,
                    user_name=interaction.user.display_name,
                    timezone=self.bot.config.scheduler_timezone,
                ),
                timeout=WORKFLOW_TIMEOUT,
            )

            if response:
                # Clean up over-escaped backticks from model output
                content = response.replace("\\`", "`")
                await self._send_long_followup(interaction, content)
            else:
                await interaction.followup.send(
                    "*Erebus completed the ritual but has nothing to say...*\n\n"
                    "The daily note was processed but no summary was generated."
                )

            logger.info(f"Daily workflow completed for {interaction.user}")

        except TimeoutError:
            logger.error(f"Daily workflow timed out for {interaction.user}")
            await interaction.followup.send(
                "The daily workflow took too long. Please try again or check the vault manually."
            )

        except RateLimitError as e:
            logger.warning(f"Rate limited during daily workflow: {e}")
            retry_msg = f" Try again in {e.retry_after:.0f}s." if e.retry_after else ""
            await interaction.followup.send(f"Rate limited by AI provider.{retry_msg}")

        except ModelError as e:
            logger.exception(f"Model error during daily workflow: {e}")
            await interaction.followup.send(
                "An error occurred while processing the daily workflow. Please try again."
            )

        except Exception as e:
            logger.exception(f"Unexpected error in daily workflow: {e}")
            await interaction.followup.send(
                "Something went wrong with the daily workflow. Please try again later."
            )

    @app_commands.command(
        name="idea",
        description="Capture a new idea seed with guided conversation",
    )
    @app_commands.describe(title="Short, descriptive title for the idea")
    @is_allowed_user()
    @is_dm_channel()
    async def idea(self, interaction: discord.Interaction, title: str) -> None:
        """Capture a new idea seed.

        Guides the user through capturing an idea with structured questions
        and a brief ideation conversation, then creates the idea file.

        Args:
            interaction: The Discord interaction.
            title: The title for the idea.
        """
        # Validate input
        title = title.strip()
        if not title:
            await interaction.response.send_message(
                "Idea title cannot be empty.",
                ephemeral=True,
            )
            return

        if len(title) > MAX_IDEA_TITLE_LENGTH:
            await interaction.response.send_message(
                f"Title too long ({len(title)} chars). "
                f"Please keep it under {MAX_IDEA_TITLE_LENGTH} characters.",
                ephemeral=True,
            )
            return

        if not self.bot.eidolon:
            await interaction.response.send_message(
                "*Erebus cannot capture ideas without a voice...*\n\n"
                "AI features are disabled. Start Letta server and configure `LETTA_API_URL` to use /idea.",
                ephemeral=True,
            )
            return

        if not self.bot.vault:
            await interaction.response.send_message(
                "*Erebus has no vault to store ideas...*\n\n"
                "Vault not configured. Set `OBSIDIAN_VAULT_PATH` to use /idea.",
                ephemeral=True,
            )
            return

        # Defer response since this workflow takes time
        await interaction.response.defer(thinking=True)
        logger.info(f"Idea capture started by {interaction.user}: {title}")

        try:
            prompt = IDEA_WORKFLOW_PROMPT.format(title=title)
            response = await asyncio.wait_for(
                self.bot.eidolon.chat(
                    user_id=interaction.user.id,
                    message=prompt,
                    user_name=interaction.user.display_name,
                    timezone=self.bot.config.scheduler_timezone,
                ),
                timeout=WORKFLOW_TIMEOUT,
            )

            if response:
                content = response.replace("\\`", "`")
                await self._send_long_followup(interaction, content)
            else:
                await interaction.followup.send(
                    "*Erebus pondered your idea but lost it in the void...*\n\n"
                    "Something went wrong. Please try again."
                )

            logger.info(f"Idea capture initiated for {interaction.user}: {title}")

        except TimeoutError:
            logger.error(f"Idea workflow timed out for {interaction.user}")
            await interaction.followup.send("The idea capture took too long. Please try again.")

        except RateLimitError as e:
            logger.warning(f"Rate limited during idea capture: {e}")
            retry_msg = f" Try again in {e.retry_after:.0f}s." if e.retry_after else ""
            await interaction.followup.send(f"Rate limited by AI provider.{retry_msg}")

        except ModelError as e:
            logger.exception(f"Model error during idea capture: {e}")
            await interaction.followup.send(
                "An error occurred while capturing the idea. Please try again."
            )

        except Exception as e:
            logger.exception(f"Unexpected error in idea capture: {e}")
            await interaction.followup.send("Something went wrong. Please try again later.")

    @app_commands.command(
        name="capture",
        description="Quickly capture a task to Todoist",
    )
    @app_commands.describe(
        task="Task description (can include priority like P1, due date, @labels)"
    )
    @is_allowed_user()
    @is_dm_channel()
    async def capture(self, interaction: discord.Interaction, task: str) -> None:
        """Quickly capture a task to Todoist.

        Parses the task description for priority, due date, project, and labels,
        creates the task in Todoist, and optionally adds it to the daily note.

        Args:
            interaction: The Discord interaction.
            task: The task description with optional metadata.
        """
        # Validate input
        task = task.strip()
        if not task:
            await interaction.response.send_message(
                "Task description cannot be empty.",
                ephemeral=True,
            )
            return

        if len(task) > MAX_TASK_DESCRIPTION_LENGTH:
            await interaction.response.send_message(
                f"Task description too long ({len(task)} chars). "
                f"Please keep it under {MAX_TASK_DESCRIPTION_LENGTH} characters.",
                ephemeral=True,
            )
            return

        if not self.bot.eidolon:
            await interaction.response.send_message(
                "*Erebus cannot capture tasks without a voice...*\n\n"
                "AI features are disabled. Start Letta server and configure `LETTA_API_URL` to use /capture.",
                ephemeral=True,
            )
            return

        if not self.bot.mcp:
            await interaction.response.send_message(
                "*Erebus has no connection to Todoist...*\n\n"
                "Todoist not configured. Set `TODOIST_API_TOKEN` to use /capture.",
                ephemeral=True,
            )
            return

        # Defer response since this workflow takes time
        await interaction.response.defer(thinking=True)
        logger.info(f"Task capture started by {interaction.user}: {task}")

        try:
            prompt = CAPTURE_WORKFLOW_PROMPT.format(task_description=task)
            response = await asyncio.wait_for(
                self.bot.eidolon.chat(
                    user_id=interaction.user.id,
                    message=prompt,
                    user_name=interaction.user.display_name,
                    timezone=self.bot.config.scheduler_timezone,
                ),
                timeout=WORKFLOW_TIMEOUT,
            )

            if response:
                content = response.replace("\\`", "`")
                await self._send_long_followup(interaction, content)
            else:
                await interaction.followup.send(
                    "*Erebus tried to capture the task but it slipped away...*\n\n"
                    "Something went wrong. Please try again."
                )

            logger.info(f"Task capture completed for {interaction.user}")

        except TimeoutError:
            logger.error(f"Capture workflow timed out for {interaction.user}")
            await interaction.followup.send("The task capture took too long. Please try again.")

        except RateLimitError as e:
            logger.warning(f"Rate limited during task capture: {e}")
            retry_msg = f" Try again in {e.retry_after:.0f}s." if e.retry_after else ""
            await interaction.followup.send(f"Rate limited by AI provider.{retry_msg}")

        except ModelError as e:
            logger.exception(f"Model error during task capture: {e}")
            await interaction.followup.send(
                "An error occurred while capturing the task. Please try again."
            )

        except Exception as e:
            logger.exception(f"Unexpected error in task capture: {e}")
            await interaction.followup.send("Something went wrong. Please try again later.")

    @app_commands.command(
        name="sync",
        description="Sync task status between Obsidian and Todoist",
    )
    @app_commands.describe(mode="Sync mode: quick (default), end-of-day, or project")
    @app_commands.choices(
        mode=[
            app_commands.Choice(name="Quick sync (just completion status)", value="quick"),
            app_commands.Choice(name="End of day (rollover incomplete tasks)", value="end-of-day"),
            app_commands.Choice(name="Project sync (specific project)", value="project"),
        ]
    )
    @is_allowed_user()
    @is_dm_channel()
    async def sync(
        self,
        interaction: discord.Interaction,
        mode: app_commands.Choice[str] | None = None,
    ) -> None:
        """Sync task status between Obsidian and Todoist.

        Performs bidirectional sync of task completion status and optionally
        handles rollover of incomplete tasks.

        Args:
            interaction: The Discord interaction.
            mode: The sync mode (quick, end-of-day, or project).
        """
        if not self.bot.eidolon:
            await interaction.response.send_message(
                "*Erebus cannot sync without a voice...*\n\n"
                "AI features are disabled. Start Letta server and configure `LETTA_API_URL` to use /sync.",
                ephemeral=True,
            )
            return

        if not self.bot.vault:
            await interaction.response.send_message(
                "*Erebus has no vault to sync...*\n\n"
                "Vault not configured. Set `OBSIDIAN_VAULT_PATH` to use /sync.",
                ephemeral=True,
            )
            return

        if not self.bot.mcp:
            await interaction.response.send_message(
                "*Erebus has no connection to Todoist...*\n\n"
                "Todoist not configured. Set `TODOIST_API_TOKEN` to use /sync.",
                ephemeral=True,
            )
            return

        # Default to quick mode
        sync_mode = mode.value if mode else "quick"

        # Defer response since this workflow takes time
        await interaction.response.defer(thinking=True)
        logger.info(f"Sync started by {interaction.user}: mode={sync_mode}")

        try:
            prompt = SYNC_WORKFLOW_PROMPT.format(mode=sync_mode)
            response = await asyncio.wait_for(
                self.bot.eidolon.chat(
                    user_id=interaction.user.id,
                    message=prompt,
                    user_name=interaction.user.display_name,
                    timezone=self.bot.config.scheduler_timezone,
                ),
                timeout=WORKFLOW_TIMEOUT,
            )

            if response:
                content = response.replace("\\`", "`")
                await self._send_long_followup(interaction, content)
            else:
                await interaction.followup.send(
                    "*Erebus attempted the sync but found nothing to report...*\n\n"
                    "Something went wrong. Please try again."
                )

            logger.info(f"Sync completed for {interaction.user}: mode={sync_mode}")

        except TimeoutError:
            logger.error(f"Sync workflow timed out for {interaction.user}")
            await interaction.followup.send("The sync took too long. Please try again.")

        except RateLimitError as e:
            logger.warning(f"Rate limited during sync: {e}")
            retry_msg = f" Try again in {e.retry_after:.0f}s." if e.retry_after else ""
            await interaction.followup.send(f"Rate limited by AI provider.{retry_msg}")

        except ModelError as e:
            logger.exception(f"Model error during sync: {e}")
            await interaction.followup.send("An error occurred while syncing. Please try again.")

        except Exception as e:
            logger.exception(f"Unexpected error in sync: {e}")
            await interaction.followup.send("Something went wrong. Please try again later.")

    @app_commands.command(
        name="weekly",
        description="Start a guided weekly review conversation",
    )
    @is_allowed_user()
    @is_dm_channel()
    async def weekly(self, interaction: discord.Interaction) -> None:
        """Start a guided weekly review.

        Guides the user through a 5-phase weekly review covering mechanical
        review, emotional check-in, constraint analysis, finding unlocks,
        and setting energy-aware priorities.

        Args:
            interaction: The Discord interaction.
        """
        if not self.bot.eidolon:
            await interaction.response.send_message(
                "*Erebus cannot guide a review without a voice...*\n\n"
                "AI features are disabled. Start Letta server and configure `LETTA_API_URL` to use /weekly.",
                ephemeral=True,
            )
            return

        if not self.bot.vault:
            await interaction.response.send_message(
                "*Erebus has no vault to record the review...*\n\n"
                "Vault not configured. Set `OBSIDIAN_VAULT_PATH` to use /weekly.",
                ephemeral=True,
            )
            return

        # Defer response since this workflow takes time
        await interaction.response.defer(thinking=True)
        logger.info(f"Weekly review started by {interaction.user}")

        try:
            response = await asyncio.wait_for(
                self.bot.eidolon.chat(
                    user_id=interaction.user.id,
                    message=WEEKLY_WORKFLOW_PROMPT,
                    user_name=interaction.user.display_name,
                    timezone=self.bot.config.scheduler_timezone,
                ),
                timeout=WORKFLOW_TIMEOUT,
            )

            if response:
                content = response.replace("\\`", "`")
                await self._send_long_followup(interaction, content)
            else:
                await interaction.followup.send(
                    "*Erebus tried to begin the review but lost focus...*\n\n"
                    "Something went wrong. Please try again."
                )

            logger.info(f"Weekly review initiated for {interaction.user}")

        except TimeoutError:
            logger.error(f"Weekly review timed out for {interaction.user}")
            await interaction.followup.send("The weekly review took too long. Please try again.")

        except RateLimitError as e:
            logger.warning(f"Rate limited during weekly review: {e}")
            retry_msg = f" Try again in {e.retry_after:.0f}s." if e.retry_after else ""
            await interaction.followup.send(f"Rate limited by AI provider.{retry_msg}")

        except ModelError as e:
            logger.exception(f"Model error during weekly review: {e}")
            await interaction.followup.send(
                "An error occurred during the review. Please try again."
            )

        except Exception as e:
            logger.exception(f"Unexpected error in weekly review: {e}")
            await interaction.followup.send("Something went wrong. Please try again later.")

    @app_commands.command(
        name="journal",
        description="Add a journal entry to today's daily note",
    )
    @app_commands.describe(entry="Optional: Your journal entry text (if omitted, you'll be asked)")
    @is_allowed_user()
    @is_dm_channel()
    async def journal(
        self,
        interaction: discord.Interaction,
        entry: str | None = None,
    ) -> None:
        """Add a journal entry to today's daily note.

        Adds a timestamped journal entry to the Journal section of today's
        daily note. If no entry text is provided, prompts for input.

        Args:
            interaction: The Discord interaction.
            entry: Optional journal entry text.
        """
        if not self.bot.eidolon:
            await interaction.response.send_message(
                "*Erebus cannot journal without a voice...*\n\n"
                "AI features are disabled. Start Letta server and configure `LETTA_API_URL` to use /journal.",
                ephemeral=True,
            )
            return

        if not self.bot.vault:
            await interaction.response.send_message(
                "*Erebus has no vault to write in...*\n\n"
                "Vault not configured. Set `OBSIDIAN_VAULT_PATH` to use /journal.",
                ephemeral=True,
            )
            return

        # Defer response since this workflow takes time
        await interaction.response.defer(thinking=True)

        # Build context based on whether entry was provided
        if entry:
            entry_context = f'The user provided this entry:\n\n"{entry}"'
            logger.info(f"Journal entry started by {interaction.user} (with text)")
        else:
            entry_context = (
                "No entry text provided. Ask the user what they'd like to journal about."
            )
            logger.info(f"Journal entry started by {interaction.user} (interactive)")

        try:
            prompt = JOURNAL_WORKFLOW_PROMPT.format(entry_context=entry_context)
            response = await asyncio.wait_for(
                self.bot.eidolon.chat(
                    user_id=interaction.user.id,
                    message=prompt,
                    user_name=interaction.user.display_name,
                    timezone=self.bot.config.scheduler_timezone,
                ),
                timeout=WORKFLOW_TIMEOUT,
            )

            if response:
                content = response.replace("\\`", "`")
                await self._send_long_followup(interaction, content)
            else:
                await interaction.followup.send(
                    "*Erebus tried to record your thoughts but they faded...*\n\n"
                    "Something went wrong. Please try again."
                )

            logger.info(f"Journal entry completed for {interaction.user}")

        except TimeoutError:
            logger.error(f"Journal entry timed out for {interaction.user}")
            await interaction.followup.send("The journal entry took too long. Please try again.")

        except RateLimitError as e:
            logger.warning(f"Rate limited during journal entry: {e}")
            retry_msg = f" Try again in {e.retry_after:.0f}s." if e.retry_after else ""
            await interaction.followup.send(f"Rate limited by AI provider.{retry_msg}")

        except ModelError as e:
            logger.exception(f"Model error during journal entry: {e}")
            await interaction.followup.send("An error occurred while journaling. Please try again.")

        except Exception as e:
            logger.exception(f"Unexpected error in journal entry: {e}")
            await interaction.followup.send("Something went wrong. Please try again later.")

    @app_commands.command(name="reset", description="[DEV] Reset your Erebus agent")
    async def reset(self, interaction: discord.Interaction) -> None:
        """Reset the user's Letta agent (development only).

        Deletes the agent and all its memory, forcing a fresh start.
        Only available in development mode.

        Args:
            interaction: The Discord interaction.
        """
        # Only allow in development mode
        if not self.bot.config.is_development:
            await interaction.response.send_message(
                "This command is only available in development mode.",
                ephemeral=True,
            )
            return

        if not self.bot.eidolon:
            await interaction.response.send_message(
                "EidolonMemory is not configured.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(thinking=True)
        logger.info(f"Agent reset requested by {interaction.user}")

        try:
            deleted = await self.bot.eidolon.clear_agent(interaction.user.id)

            if deleted:
                await interaction.followup.send(
                    "*The shadow dissolves into the void...*\n\n"
                    "Your Erebus agent has been reset. A new agent will be created "
                    "on your next message."
                )
                logger.info(f"Agent reset completed for {interaction.user}")
            else:
                await interaction.followup.send(
                    "*There is nothing to reset...*\n\nNo agent found for your user ID."
                )

        except Exception as e:
            logger.exception(f"Failed to reset agent: {e}")
            await interaction.followup.send(f"Failed to reset agent: {e}")

    async def _send_long_followup(
        self,
        interaction: discord.Interaction,
        content: str,
        max_length: int = 2000,
    ) -> None:
        """Send a followup message, splitting if necessary.

        Args:
            interaction: The Discord interaction.
            content: The message content.
            max_length: Maximum message length.
        """
        if len(content) <= max_length:
            await interaction.followup.send(content)
            return

        # Split on newlines, then by length
        chunks: list[str] = []
        current_chunk = ""

        for line in content.split("\n"):
            if len(current_chunk) + len(line) + 1 > max_length:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                while len(line) > max_length:
                    chunks.append(line[:max_length])
                    line = line[max_length:]
                current_chunk = line
            else:
                current_chunk += "\n" + line if current_chunk else line

        if current_chunk:
            chunks.append(current_chunk.strip())

        for chunk in chunks:
            if chunk:
                await interaction.followup.send(chunk)

    @ping.error
    @status.error
    @daily.error
    @idea.error
    @capture.error
    @sync.error
    @weekly.error
    @journal.error
    @reset.error
    async def command_error_handler(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        """Handle errors for commands in this cog.

        Args:
            interaction: The Discord interaction.
            error: The error that occurred.
        """
        if isinstance(error, app_commands.CheckFailure):
            # User not allowed or not in DMs - already handled by check
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "You don't have permission to use this command.",
                    ephemeral=True,
                )
            return

        logger.exception(f"Command error: {error}")
        if not interaction.response.is_done():
            await interaction.response.send_message(
                "An error occurred. Please try again later.",
                ephemeral=True,
            )


async def setup(bot: ErebusBot) -> None:
    """Set up the cog.

    Args:
        bot: The Erebus bot instance.
    """
    await bot.add_cog(CoreCog(bot))
