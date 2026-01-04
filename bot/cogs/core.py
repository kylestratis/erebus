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
        if not self.bot.conversation_manager:
            await interaction.response.send_message(
                "*Erebus cannot plan without a voice...*\n\n"
                "AI features are disabled. Configure `CLAUDE_API_KEY` to use /daily.",
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
                self.bot.conversation_manager.chat(
                    user_id=interaction.user.id,
                    message=DAILY_WORKFLOW_PROMPT,
                ),
                timeout=WORKFLOW_TIMEOUT,
            )

            if response.content:
                # Clean up over-escaped backticks from model output
                content = response.content.replace("\\`", "`")
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
            await interaction.followup.send(
                f"Rate limited by AI provider.{retry_msg}"
            )

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

        if not self.bot.conversation_manager:
            await interaction.response.send_message(
                "*Erebus cannot capture ideas without a voice...*\n\n"
                "AI features are disabled. Configure `CLAUDE_API_KEY` to use /idea.",
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
                self.bot.conversation_manager.chat(
                    user_id=interaction.user.id,
                    message=prompt,
                ),
                timeout=WORKFLOW_TIMEOUT,
            )

            if response.content:
                content = response.content.replace("\\`", "`")
                await self._send_long_followup(interaction, content)
            else:
                await interaction.followup.send(
                    "*Erebus pondered your idea but lost it in the void...*\n\n"
                    "Something went wrong. Please try again."
                )

            logger.info(f"Idea capture initiated for {interaction.user}: {title}")

        except TimeoutError:
            logger.error(f"Idea workflow timed out for {interaction.user}")
            await interaction.followup.send(
                "The idea capture took too long. Please try again."
            )

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
            await interaction.followup.send(
                "Something went wrong. Please try again later."
            )

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

        if not self.bot.conversation_manager:
            await interaction.response.send_message(
                "*Erebus cannot capture tasks without a voice...*\n\n"
                "AI features are disabled. Configure `CLAUDE_API_KEY` to use /capture.",
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
                self.bot.conversation_manager.chat(
                    user_id=interaction.user.id,
                    message=prompt,
                ),
                timeout=WORKFLOW_TIMEOUT,
            )

            if response.content:
                content = response.content.replace("\\`", "`")
                await self._send_long_followup(interaction, content)
            else:
                await interaction.followup.send(
                    "*Erebus tried to capture the task but it slipped away...*\n\n"
                    "Something went wrong. Please try again."
                )

            logger.info(f"Task capture completed for {interaction.user}")

        except TimeoutError:
            logger.error(f"Capture workflow timed out for {interaction.user}")
            await interaction.followup.send(
                "The task capture took too long. Please try again."
            )

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
            await interaction.followup.send(
                "Something went wrong. Please try again later."
            )

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
