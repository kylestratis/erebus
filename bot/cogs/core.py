"""Core bot commands.

Provides essential commands for bot health checking and status monitoring.
"""

from __future__ import annotations

import logging
import platform
import sys
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

if TYPE_CHECKING:
    from bot.client import ErebusBot

logger = logging.getLogger(__name__)


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

    @ping.error
    @status.error
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
