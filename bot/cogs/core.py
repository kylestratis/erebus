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
