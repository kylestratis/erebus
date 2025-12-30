"""Erebus Discord client with security controls.

Custom Discord client that enforces user whitelist and DM-only mode
for secure, personal assistant operation.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import discord
from discord.ext import commands

if TYPE_CHECKING:
    from bot.config import Config

logger = logging.getLogger(__name__)

# Rate limiting for placeholder responses (seconds between responses per user)
PLACEHOLDER_RESPONSE_COOLDOWN = 30


class ErebusBot(commands.Bot):
    """Erebus Discord bot with user whitelist and DM-only mode.

    This bot only responds to whitelisted users in DM channels,
    providing a secure personal assistant experience.

    Attributes:
        config: Bot configuration instance.
        start_time: When the bot started (for uptime tracking).
    """

    def __init__(self, config: Config) -> None:
        """Initialize the Erebus bot.

        Args:
            config: Bot configuration with credentials and settings.
        """
        # Set up intents - we need messages and DMs
        intents = discord.Intents.default()
        intents.message_content = True  # Required to read message content
        intents.dm_messages = True  # Required for DM functionality

        super().__init__(
            command_prefix="!",  # Fallback prefix, we primarily use slash commands
            intents=intents,
            description=config.BOT_DESCRIPTION,
        )

        self.config = config
        self.start_time: datetime | None = None
        self._last_placeholder_response: dict[int, datetime] = {}

    async def setup_hook(self) -> None:
        """Async setup called after login but before connecting.

        Loads cogs and syncs commands.
        """
        # Load core cog with basic commands
        from bot.cogs.core import CoreCog

        await self.add_cog(CoreCog(self))
        logger.info("Loaded CoreCog")

        # Sync commands
        if self.config.discord_guild_id:
            # Sync to specific guild for faster updates during development
            guild = discord.Object(id=self.config.discord_guild_id)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            logger.info(f"Synced commands to guild {self.config.discord_guild_id}")
        else:
            # Global sync (can take up to an hour to propagate)
            await self.tree.sync()
            logger.info("Synced commands globally")

    async def on_ready(self) -> None:
        """Called when the bot is ready and connected."""
        self.start_time = datetime.now(UTC)

        logger.info(f"Logged in as {self.user} (ID: {self.user.id})")
        logger.info(f"Connected to {len(self.guilds)} guild(s)")
        logger.info(f"Allowed users: {self.config.allowed_user_ids}")

        # Set presence
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="the void",
            )
        )

    async def on_message(self, message: discord.Message) -> None:
        """Handle incoming messages with security checks.

        Only processes messages from whitelisted users in DM channels.

        Args:
            message: The incoming Discord message.
        """
        # Ignore messages from the bot itself
        if message.author.id == self.user.id:
            return

        # Security check: only respond to whitelisted users
        if not self.config.is_user_allowed(message.author.id):
            logger.warning(
                f"Rejected message from non-whitelisted user: "
                f"{message.author} (ID: {message.author.id})"
            )
            return

        # Security check: only respond in DMs
        if not isinstance(message.channel, discord.DMChannel):
            logger.debug(f"Ignoring non-DM message from {message.author} in {message.channel}")
            # Optionally inform user to use DMs
            if message.guild:
                try:
                    await message.reply(
                        "I only respond in DMs for privacy. Send me a direct message!",
                        delete_after=10,
                    )
                except discord.Forbidden:
                    pass  # Can't reply in this channel
            return

        # Log the incoming message
        logger.info(f"Message from {message.author}: {message.content[:100]}...")

        # Process commands (slash commands handled separately by discord.py)
        await self.process_commands(message)

        # TODO: Route non-command messages to the AI agent
        # For now, just acknowledge with rate limiting to prevent spam
        if not message.content.startswith(self.command_prefix):
            now = datetime.now(UTC)
            last_response = self._last_placeholder_response.get(message.author.id)

            if last_response is None or (
                now - last_response > timedelta(seconds=PLACEHOLDER_RESPONSE_COOLDOWN)
            ):
                self._last_placeholder_response[message.author.id] = now
                await message.channel.send(
                    "*Erebus stirs in the darkness...*\n\n"
                    "I'm still learning to speak. "
                    "Use `/ping` or `/status` for now."
                )

    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError) -> None:
        """Handle command errors gracefully.

        Args:
            ctx: Command context.
            error: The error that occurred.
        """
        if isinstance(error, commands.CommandNotFound):
            return  # Ignore unknown commands silently

        if isinstance(error, commands.CheckFailure):
            await ctx.send("You don't have permission to use this command.")
            return

        # Log unexpected errors
        logger.exception(f"Command error: {error}")
        await ctx.send("An error occurred while processing your command. Please try again later.")

    @property
    def uptime(self) -> str:
        """Get formatted uptime string."""
        if not self.start_time:
            return "Not started"

        delta = datetime.now(UTC) - self.start_time
        days = delta.days
        hours, remainder = divmod(delta.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)

        parts = []
        if days:
            parts.append(f"{days}d")
        if hours:
            parts.append(f"{hours}h")
        if minutes:
            parts.append(f"{minutes}m")
        parts.append(f"{seconds}s")

        return " ".join(parts)
