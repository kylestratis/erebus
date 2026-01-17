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
    MCPClientManager,
    MCPToolExecutor,
    ModelError,
    RateLimitError,
    create_todoist_config,
)
from agents.eidolon import (
    EidolonConfig,
    EidolonMemory,
    SystemToolExecutor,
    ToolRegistry,
    get_system_tool_definitions,
)
from agents.vault import (
    Vault,
    VaultConfig,
    VaultError,
    VaultToolExecutor,
    get_vault_tool_definitions,
)
from bot.scheduler import Scheduler
from bot.scheduler.jobs import DailyNoteJob, EndOfDaySyncJob, WeeklyReviewJob

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
        eidolon: Letta-powered stateful memory system.
        mcp: MCP client manager for tool integrations (Todoist).
        vault: Obsidian vault for note operations.
        scheduler: Job scheduler for automated tasks.
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
        self.eidolon: EidolonMemory | None = None
        self.mcp: MCPClientManager | None = None
        self.vault: Vault | None = None
        self._tool_registry: ToolRegistry | None = None
        self.scheduler: Scheduler | None = None

    async def setup_hook(self) -> None:
        """Async setup called after login but before connecting.

        Loads cogs, initializes MCP connections, and syncs commands.

        Setup Order (IMPORTANT):
        The setup order matters because of tool registration dependencies:

        1. _setup_mcp() - Connect to MCP servers (Todoist)
        2. _setup_vault() - Create tool registry, register vault + MCP tools
        3. _setup_scheduler() - Initialize scheduler (needed by system tools)
        4. _setup_system_tools() - Register system introspection tools
        5. _setup_eidolon() - Create EidolonMemory with complete tool registry
        6. set_resources() - Give scheduler access to eidolon

        EidolonMemory registers tools with Letta lazily on first agent creation.
        All tools must be in the registry BEFORE _setup_eidolon() is called,
        otherwise they won't be available to the agent.
        """
        # Load core cog with basic commands
        from bot.cogs.core import CoreCog

        await self.add_cog(CoreCog(self))
        logger.info("Loaded CoreCog")

        # Initialize MCP and connect to servers (Todoist)
        # MCP tools are configured in Letta, but we keep the client for direct access
        await self._setup_mcp()

        # Initialize vault (creates tool registry, registers vault + MCP tools)
        self._setup_vault()

        # Initialize scheduler (needed for system tools)
        self._setup_scheduler()

        # Register system introspection tools (needs scheduler reference)
        self._setup_system_tools()

        # Initialize EidolonMemory with Letta (must be after all tools are registered)
        await self._setup_eidolon()

        # Set all resources on scheduler (now that eidolon exists)
        if self.scheduler:
            self.scheduler.set_resources(
                eidolon=self.eidolon,
                vault=self.vault,
                mcp=self.mcp,
            )

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

    def _setup_vault(self) -> None:
        """Initialize Obsidian vault and create tool registry.

        Creates a ToolRegistry with vault tools and MCP tools for EidolonMemory.
        """
        # Always create tool registry (even without vault, for MCP tools)
        self._tool_registry = ToolRegistry()

        # Register vault tools if configured
        if self.config.obsidian_vault_path:
            try:
                vault_config = VaultConfig.from_settings(self.config)
                self.vault = Vault(vault_config)

                tool_definitions = get_vault_tool_definitions()
                executor = VaultToolExecutor(self.vault)
                self._tool_registry.register(tool_definitions, executor)

                logger.info(f"Initialized vault at {self.config.obsidian_vault_path}")

            except VaultError as e:
                logger.error(f"Vault configuration error: {e}. Check OBSIDIAN_VAULT_PATH.")
                self.vault = None

            except Exception as e:
                logger.exception(f"Failed to initialize vault: {e}")
                self.vault = None
        else:
            logger.info("Vault not configured (OBSIDIAN_VAULT_PATH not set)")

        # Register MCP tools if available
        if self.mcp and self.mcp.is_initialized:
            mcp_tools = self.mcp.get_all_tools()
            if mcp_tools:
                mcp_executor = MCPToolExecutor(self.mcp)
                self._tool_registry.register(mcp_tools, mcp_executor)
                logger.info(f"Registered {len(mcp_tools)} MCP tools")

    async def _setup_eidolon(self) -> None:
        """Initialize EidolonMemory with Letta.

        Creates an EidolonMemory instance configured with the tool registry.
        """
        # Check if Letta is configured
        if not self.config.letta_api_url:
            logger.warning(
                "LETTA_API_URL not set - EidolonMemory disabled. "
                "Start the Letta server and configure LETTA_API_URL to enable."
            )
            return

        try:
            eidolon_config = EidolonConfig(
                base_url=self.config.letta_api_url,
                api_key=self.config.letta_api_key,
                default_timezone=self.config.scheduler_timezone,
            )

            self.eidolon = EidolonMemory(
                config=eidolon_config,
                tool_registry=self._tool_registry,
            )

            # Verify connection
            if await self.eidolon.health_check():
                logger.info(f"EidolonMemory connected to Letta at {self.config.letta_api_url}")
            else:
                logger.warning(
                    f"Letta server at {self.config.letta_api_url} is not responding. "
                    "EidolonMemory initialized but may not work until server is available."
                )

        except Exception as e:
            logger.exception(f"Failed to initialize EidolonMemory: {e}")
            self.eidolon = None

    def _setup_scheduler(self) -> None:
        """Initialize the job scheduler and register jobs.

        Jobs are registered but not started until on_ready.
        """
        if not self.config.scheduler_enabled:
            logger.info("Scheduler disabled via configuration")
            return

        self.scheduler = Scheduler(
            config=self.config,
            timezone=self.config.scheduler_timezone,
        )

        # Register daily note job
        daily_note_job = DailyNoteJob()
        daily_note_job.cron = self.config.job_daily_note_cron
        daily_note_job.enabled = self.config.job_daily_note_enabled
        self.scheduler.register(daily_note_job)

        # Register end-of-day sync job
        eod_sync_job = EndOfDaySyncJob()
        eod_sync_job.cron = self.config.job_end_of_day_sync_cron
        eod_sync_job.enabled = self.config.job_end_of_day_sync_enabled
        self.scheduler.register(eod_sync_job)

        # Register weekly review job
        weekly_review_job = WeeklyReviewJob()
        weekly_review_job.cron = self.config.job_weekly_review_cron
        weekly_review_job.enabled = self.config.job_weekly_review_enabled
        self.scheduler.register(weekly_review_job)

        logger.info(f"Scheduler initialized with {len(self.scheduler.jobs)} jobs")

    def _setup_system_tools(self) -> None:
        """Register system introspection tools.

        Must be called after scheduler is set up so system_status
        can report on scheduled jobs.
        """
        if not self._tool_registry:
            logger.debug("No tool registry - skipping system tools")
            return

        system_tools = get_system_tool_definitions()
        system_executor = SystemToolExecutor(
            tool_registry=self._tool_registry,
            scheduler=self.scheduler,
            mcp=self.mcp,
        )
        self._tool_registry.register(system_tools, system_executor)
        logger.info(f"Registered {len(system_tools)} system tools")

    async def _start_scheduler(self) -> None:
        """Start the scheduler after bot is ready.

        Fetches the primary Discord user for DMs and starts the scheduler.
        """
        if not self.scheduler:
            return

        # Fetch the primary user for DMs
        try:
            user = await self.fetch_user(self.config.discord_user_id)
            self.scheduler.set_discord_user(user)
            logger.info(f"Scheduler configured to DM user: {user}")
        except discord.NotFound:
            logger.warning(
                f"Could not find Discord user {self.config.discord_user_id}. "
                "Scheduled jobs will not be able to send DMs."
            )
        except Exception as e:
            logger.exception(f"Failed to fetch Discord user for scheduler: {e}")

        # Start the scheduler
        await self.scheduler.start()
        logger.info("Scheduler started")

    async def on_ready(self) -> None:
        """Called when the bot is ready and connected."""
        self.start_time = datetime.now(UTC)

        logger.info(f"Logged in as {self.user} (ID: {self.user.id})")
        logger.info(f"Connected to {len(self.guilds)} guild(s)")
        logger.info(f"Allowed users: {self.config._allowed_user_ids_set}")

        # Set presence
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="the void",
            )
        )

        # Start scheduler and set up Discord user for DMs
        await self._start_scheduler()

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
        """Handle a message by routing it to EidolonMemory (Letta).

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

        # Check if EidolonMemory is available
        if not self.eidolon:
            await message.channel.send(
                "*Erebus stirs but cannot speak...*\n\n"
                "AI features are disabled. Please start the Letta server and configure "
                "`LETTA_API_URL` to enable me."
            )
            return

        # Show typing indicator while processing
        async with message.channel.typing():
            try:
                response = await asyncio.wait_for(
                    self.eidolon.chat(
                        user_id=message.author.id,
                        message=message.content,
                        user_name=message.author.display_name,
                        timezone=self.config.scheduler_timezone,
                    ),
                    timeout=MODEL_REQUEST_TIMEOUT,
                )

                # Send the response
                if response:
                    await self._send_long_message(message.channel, response)
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
        # Stop scheduler
        if self.scheduler:
            logger.info("Shutting down scheduler...")
            await self.scheduler.stop()

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
