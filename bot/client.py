"""Erebus Discord client with security controls.

Custom Discord client that enforces user whitelist and DM-only mode
for secure, personal assistant operation.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import discord
from discord.ext import commands

from agents import (
    AnthropicProvider,
    ConversationManager,
    MCPClientManager,
    ModelError,
    RateLimitError,
    create_todoist_config,
)

if TYPE_CHECKING:
    from bot.config import Settings

logger = logging.getLogger(__name__)

# Discord message length limit
DISCORD_MESSAGE_MAX_LENGTH = 2000

# Timeout for model API requests (seconds)
MODEL_REQUEST_TIMEOUT = 60.0


class ErebusBot(commands.Bot):
    """Erebus Discord bot with user whitelist and DM-only mode.

    This bot only responds to whitelisted users in DM channels,
    providing a secure personal assistant experience.

    Attributes:
        config: Bot configuration instance.
        start_time: When the bot started (for uptime tracking).
        conversation_manager: Manages conversations with the AI model.
        mcp: MCP client manager for tool integrations.
    """

    def __init__(self, config: Settings) -> None:
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
        self.conversation_manager: ConversationManager | None = None
        self.mcp: MCPClientManager | None = None
        self._model: AnthropicProvider | None = None

        # Initialize AI model if API key is available
        if config.claude_api_key:
            self._model = AnthropicProvider(api_key=config.claude_api_key)
            logger.info(f"Initialized AI model: {self._model.name} ({self._model.default_model})")
        else:
            logger.warning(
                "CLAUDE_API_KEY not set - AI features disabled. "
                "Set CLAUDE_API_KEY in your .env file to enable AI responses."
            )

    async def setup_hook(self) -> None:
        """Async setup called after login but before connecting.

        Loads cogs, initializes MCP connections, and syncs commands.
        """
        # Load core cog with basic commands
        from bot.cogs.core import CoreCog

        await self.add_cog(CoreCog(self))
        logger.info("Loaded CoreCog")

        # Initialize MCP and connect to servers
        await self._setup_mcp()

        # Initialize conversation manager with model and MCP
        if self._model:
            self.conversation_manager = ConversationManager(
                model=self._model,
                mcp=self.mcp,
            )
            logger.info("Initialized conversation manager")

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

    async def _setup_mcp(self) -> None:
        """Initialize MCP client and connect to configured servers."""
        # Only initialize if we have integrations configured
        if not self.config.todoist_api_token:
            logger.info("No MCP integrations configured (TODOIST_API_TOKEN not set)")
            return

        try:
            self.mcp = MCPClientManager()
            await self.mcp.start()

            # Connect to Todoist MCP server
            if self.config.todoist_api_token:
                todoist_config = create_todoist_config(self.config.todoist_api_token)
                await self.mcp.connect(todoist_config)
                logger.info("Connected to Todoist MCP server")

        except Exception as e:
            logger.exception(f"Failed to initialize MCP: {e}")
            # Continue without MCP - AI will work but without tools
            self.mcp = None

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

        # Ignore empty messages early
        if not message.content or not message.content.strip():
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

        # Route non-command messages to the AI agent
        if not message.content.startswith(self.command_prefix):
            await self._handle_ai_message(message)

    async def _handle_ai_message(self, message: discord.Message) -> None:
        """Handle a message by routing it to the AI model.

        Security: This method performs its own authorization check as defense-in-depth,
        even though callers should have already verified the user is authorized.

        Args:
            message: The Discord message to process.
        """
        # Defense-in-depth: verify authorization even though caller should have checked
        if not self.config.is_user_allowed(message.author.id):
            logger.error(
                f"SECURITY: _handle_ai_message called for unauthorized user "
                f"{message.author.id} - this should not happen"
            )
            return

        # Check if AI is available
        if not self.conversation_manager:
            await message.channel.send(
                "*Erebus stirs but cannot speak...*\n\n"
                "AI features are disabled. Please configure `CLAUDE_API_KEY` to enable me."
            )
            return

        # Show typing indicator while processing
        async with message.channel.typing():
            try:
                response = await asyncio.wait_for(
                    self.conversation_manager.chat(
                        user_id=message.author.id,
                        message=message.content,
                    ),
                    timeout=MODEL_REQUEST_TIMEOUT,
                )

                # Send the response
                if response.content:
                    await self._send_long_message(message.channel, response.content)
                else:
                    # Model returned no content (shouldn't happen in normal chat)
                    logger.warning(f"Model returned empty response for user {message.author.id}")
                    await message.channel.send(
                        "*Erebus ponders in silence...*\n\nI'm not sure how to respond to that."
                    )

            except TimeoutError:
                logger.error(f"Model request timed out for user {message.author.id}")
                await message.channel.send(
                    "The request took too long to process. Please try again."
                )

            except RateLimitError as e:
                logger.warning(f"Rate limited: {e}")
                retry_msg = f" Try again in {e.retry_after:.0f} seconds." if e.retry_after else ""
                await message.channel.send(
                    f"I'm being rate limited by my AI provider.{retry_msg} Please wait a moment."
                )

            except ModelError as e:
                logger.exception(f"Model error for user {message.author.id}: {e}")
                await message.channel.send(
                    "I encountered an error while thinking. Please try again."
                )

            except Exception as e:
                logger.exception(f"Unexpected error handling message: {e}")
                await message.channel.send(
                    "Something unexpected went wrong. Please try again later."
                )

    async def _send_long_message(
        self,
        channel: discord.abc.Messageable,
        content: str,
        max_length: int = DISCORD_MESSAGE_MAX_LENGTH,
    ) -> None:
        """Send a message, splitting it if it exceeds Discord's limit.

        Args:
            channel: The channel to send to.
            content: The message content.
            max_length: Maximum message length (Discord limit is 2000).
        """
        if len(content) <= max_length:
            await channel.send(content)
            return

        # Split on newlines first, then by length
        chunks: list[str] = []
        current_chunk = ""

        for line in content.split("\n"):
            # If adding this line would exceed the limit, start a new chunk
            if len(current_chunk) + len(line) + 1 > max_length:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                # If the line itself is too long, split it
                while len(line) > max_length:
                    chunks.append(line[:max_length])
                    line = line[max_length:]
                current_chunk = line
            else:
                current_chunk += "\n" + line if current_chunk else line

        if current_chunk:
            chunks.append(current_chunk.strip())

        # Send all chunks
        for chunk in chunks:
            if chunk:
                await channel.send(chunk)

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

    async def close(self) -> None:
        """Clean up resources before shutting down."""
        # Clean up MCP connections
        if self.mcp:
            logger.info("Shutting down MCP connections...")
            await self.mcp.stop()

        # Call parent close
        await super().close()

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
