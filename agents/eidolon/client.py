"""EidolonMemory client for Letta integration.

Provides a wrapper around the Letta SDK for managing per-user agents
with persistent memory.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from letta_client import AsyncLetta

from agents.eidolon.memory import (
    CONTEXT_BLOCK,
    CONTEXT_LABEL,
    HUMAN_LABEL,
    PERSONA_BLOCK,
    PERSONA_LABEL,
    create_human_block,
)
from agents.eidolon.tools import ToolRegistry
from bot.diagnostics import RequestMetrics, ToolCallMetrics
from config import MCPServerConfig

if TYPE_CHECKING:
    from letta_client.types import AgentState

logger = logging.getLogger(__name__)

# Default model configuration
DEFAULT_MODEL = "anthropic/claude-sonnet-4-20250514"
DEFAULT_EMBEDDING = "openai/text-embedding-3-small"


@dataclass
class EidolonConfig:
    """Configuration for EidolonMemory.

    Attributes:
        base_url: Letta server API URL.
        api_key: Optional API key for authentication.
        model: Model identifier for the agent.
        embedding: Embedding model for archival memory search.
        default_timezone: Default timezone for new users.
        mcp_servers: MCP servers to register with Letta (native MCP support).
    """

    base_url: str = "http://localhost:8283"
    api_key: str | None = None
    model: str = DEFAULT_MODEL
    embedding: str = DEFAULT_EMBEDDING
    default_timezone: str = "America/New_York"
    mcp_servers: list[MCPServerConfig] = field(default_factory=list)


class EidolonMemory:
    """Manages Letta agents with persistent memory per user.

    Each Discord user gets their own Letta agent that persists across
    sessions. The agent maintains three types of memory:
    - Core memory: Always visible (persona, user profile, context)
    - Archival memory: Semantic search for learned patterns
    - Recall memory: Conversation history

    Native tools (like vault operations) are executed locally in the bot
    process rather than in Letta's environment. This allows tools to access
    local resources like the filesystem.

    MCP tools (like Todoist) can be registered with Letta's native MCP support,
    allowing Letta to execute them directly in its Docker environment.

    Attributes:
        config: EidolonMemory configuration.
        client: Letta SDK client.
        tool_registry: Registry for native tools.
    """

    # Maximum tool execution iterations to prevent infinite loops
    MAX_TOOL_ITERATIONS = 10
    # Timeout for individual tool execution in seconds
    TOOL_EXECUTION_TIMEOUT = 30.0

    def __init__(
        self,
        config: EidolonConfig | None = None,
        tool_registry: ToolRegistry | None = None,
    ) -> None:
        """Initialize EidolonMemory.

        Args:
            config: Configuration for the Letta connection.
                   If None, uses default configuration.
            tool_registry: Optional registry for native tools.
                          If None, creates an empty registry.
        """
        self.config = config or EidolonConfig()
        self.tool_registry = tool_registry or ToolRegistry()

        # Initialize async Letta client
        self.client = AsyncLetta(
            base_url=self.config.base_url,
            api_key=self.config.api_key,
        )

        # Cache of user_id -> agent_id mappings
        self._agent_cache: dict[int, str] = {}

        # Tool registration state (lazy initialization)
        self._tool_ids: list[str] = []
        self._tools_registered: bool = False

        # MCP server registration state
        self._mcp_server_ids: dict[str, str] = {}  # name -> server_id
        self._mcp_tool_ids: set[str] = set()  # Tool IDs from MCP servers (set for dedup)
        self._mcp_tool_names: set[str] = set()  # Tool names from MCP servers (for approval)
        self._mcp_registered: bool = False

        # Async locks to prevent race conditions during lazy initialization
        self._mcp_registration_lock = asyncio.Lock()
        self._tools_registration_lock = asyncio.Lock()

        logger.info(f"EidolonMemory initialized with Letta at {self.config.base_url}")

    async def get_or_create_agent(
        self,
        user_id: int,
        user_name: str = "User",
        timezone: str | None = None,
    ) -> str:
        """Get existing agent or create new one for a user.

        Args:
            user_id: Discord user ID.
            user_name: User's display name.
            timezone: User's timezone (IANA format).

        Returns:
            Agent ID for the user.
        """
        # Ensure MCP servers are registered with Letta
        await self._ensure_mcp_servers_registered()

        # Ensure tools are registered with Letta (needed for both new and existing agents)
        await self._ensure_tools_registered()

        # Check cache first
        if user_id in self._agent_cache:
            return self._agent_cache[user_id]

        # Try to find existing agent by name
        agent_name = self._get_agent_name(user_id)
        existing = await self._find_agent_by_name(agent_name)

        if existing:
            self._agent_cache[user_id] = existing.id
            logger.info(f"Found existing agent for user {user_id}: {existing.id}")

            # Update agent's tools to include any new ones
            await self._sync_agent_tools(existing.id)

            # Cancel any pending approvals from previous sessions
            # This handles the case where the bot crashed during tool execution
            await self._cancel_pending_approvals(existing.id)

            return existing.id

        # Create new agent
        agent = await self._create_agent(
            user_id=user_id,
            user_name=user_name,
            timezone=timezone or self.config.default_timezone,
        )

        self._agent_cache[user_id] = agent.id
        logger.info(f"Created new agent for user {user_id}: {agent.id}")
        return agent.id

    async def chat(
        self,
        user_id: int,
        message: str,
        user_name: str = "User",
        timezone: str | None = None,
        metrics: RequestMetrics | None = None,
    ) -> str:
        """Send a message to the user's agent and get a response.

        Handles tool execution loops: if the agent requests a native tool,
        executes it locally and sends the result back to continue the
        conversation until a final text response is received.

        Args:
            user_id: Discord user ID.
            message: User's message.
            user_name: User's display name (for new agents).
            timezone: User's timezone (for new agents).
            metrics: Optional RequestMetrics for tracking diagnostics.

        Returns:
            Agent's response text.
        """
        # Ensure agent exists
        agent_id = await self.get_or_create_agent(
            user_id=user_id,
            user_name=user_name,
            timezone=timezone,
        )

        # Send message to agent
        logger.debug(f"Sending message to agent {agent_id}: {message[:100]}...")
        letta_start = time.perf_counter()
        response = await self.client.agents.messages.create(
            agent_id=agent_id,
            messages=[{"role": "user", "content": message}],
        )
        letta_elapsed = (time.perf_counter() - letta_start) * 1000
        logger.debug(
            f"Received response from Letta: {type(response).__name__} ({letta_elapsed:.0f}ms)"
        )

        # Handle tool execution loop
        iterations = 0
        while iterations < self.MAX_TOOL_ITERATIONS:
            # Check for function calls that need local execution
            tool_call = self._extract_function_call(response)

            if tool_call is None:
                # No function call, we have a final response
                logger.debug("No tool call in response, returning final text")
                break

            tool_name, tool_args, call_id = tool_call
            logger.debug(f"Extracted tool call: {tool_name} (id={call_id}) args={tool_args}")

            # Check if this is a native tool we handle locally
            if not self.tool_registry.can_handle(tool_name):
                # Check if this is an MCP tool (Letta executes server-side)
                # MCP tool names are stored when registering with Letta
                if tool_name in self._mcp_tool_names:
                    # MCP tools are executed by Letta server-side after we send approval.
                    # We send an approval with a placeholder tool_return (required by API)
                    # to tell Letta to proceed with executing the MCP tool.
                    logger.info(f"MCP tool {tool_name} - sending approval to Letta")
                    tool_metrics = ToolCallMetrics(tool_name=tool_name)
                    if metrics:
                        metrics.tool_calls.append(tool_metrics)

                    try:
                        # Send approval with placeholder tool_return (API requires this field)
                        # Letta will execute the MCP tool after receiving this approval
                        response = await self.client.agents.messages.create(
                            agent_id=agent_id,
                            messages=[
                                {
                                    "type": "approval",
                                    "approvals": [
                                        {
                                            "type": "tool",
                                            "tool_call_id": call_id,
                                            "tool_return": "[Approved for Letta execution]",
                                            "status": "success",
                                        }
                                    ],
                                }
                            ],
                        )
                        tool_metrics.finish(success=True)
                        logger.info(
                            f"MCP tool {tool_name} approved ({tool_metrics.elapsed_ms:.0f}ms)"
                        )
                    except Exception as e:
                        tool_metrics.finish(success=False, error=str(e))
                        logger.exception(f"MCP tool approval failed: {tool_name}")
                        # Approval failed - return error to user
                        return f"I encountered an error while processing your request: {e}"

                    iterations += 1
                    continue
                else:
                    # Unknown tool - send error response so agent can handle gracefully
                    logger.warning(f"Unknown tool {tool_name} not in registry or MCP tools")
                    try:
                        response = await self.client.agents.messages.create(
                            agent_id=agent_id,
                            messages=[
                                {
                                    "type": "approval",
                                    "approvals": [
                                        {
                                            "type": "tool",
                                            "tool_call_id": call_id,
                                            "tool_return": f"Tool '{tool_name}' is not available",
                                            "status": "error",
                                        }
                                    ],
                                }
                            ],
                        )
                        iterations += 1
                        continue
                    except Exception as e:
                        logger.exception(f"Failed to send error for unknown tool: {e}")
                        return f"I encountered an error while processing your request: {e}"

            # Execute native tool locally with timeout
            logger.info(f"Executing native tool: {tool_name}")
            logger.debug(f"Tool arguments: {tool_args}")

            # Track tool execution timing
            tool_metrics = ToolCallMetrics(tool_name=tool_name)
            if metrics:
                metrics.tool_calls.append(tool_metrics)

            status = "success"
            try:
                result = await asyncio.wait_for(
                    self.tool_registry.execute(tool_name, tool_args),
                    timeout=self.TOOL_EXECUTION_TIMEOUT,
                )
                tool_metrics.finish(success=True)
                logger.debug(
                    f"Tool result ({len(result)} chars, {tool_metrics.elapsed_ms:.0f}ms): "
                    f"{result[:200]}..."
                )
            except TimeoutError:
                tool_metrics.finish(success=False, error="timeout")
                logger.error(
                    f"Tool execution timed out: {tool_name} ({tool_metrics.elapsed_ms:.0f}ms)"
                )
                result = f"Tool execution timed out after {self.TOOL_EXECUTION_TIMEOUT}s"
                status = "error"
            except Exception as e:
                tool_metrics.finish(success=False, error=str(e))
                logger.exception(
                    f"Tool execution failed: {tool_name} ({tool_metrics.elapsed_ms:.0f}ms)"
                )
                result = f"Error executing tool: {e}"
                status = "error"

            # Send result back as an approval response with ToolReturnParam
            # This is required for tools registered with default_requires_approval=True
            # The approval message tells Letta we executed the tool and provides the result
            logger.debug(f"Sending tool result back to agent (iteration {iterations + 1})")
            response = await self.client.agents.messages.create(
                agent_id=agent_id,
                messages=[
                    {
                        "type": "approval",
                        "approvals": [
                            {
                                "type": "tool",
                                "tool_call_id": call_id,
                                "tool_return": result,
                                "status": status,
                            }
                        ],
                    }
                ],
            )
            logger.debug(f"Received response after tool result: {type(response).__name__}")

            iterations += 1

        if iterations >= self.MAX_TOOL_ITERATIONS:
            logger.error(f"Tool execution loop hit max iterations for user {user_id}")
            if metrics:
                metrics.add_metadata("tool_iterations", iterations)
            return "I hit my processing limit while working on your request. Please try again."

        # Record iteration count in metrics
        if metrics:
            metrics.add_metadata("tool_iterations", iterations)

        # Extract text response
        final_text = self._extract_response_text(response)
        logger.debug(f"Final response ({len(final_text)} chars): {final_text[:100]}...")
        return final_text

    async def get_agent_id(self, user_id: int) -> str | None:
        """Get the agent ID for a user if it exists.

        Args:
            user_id: Discord user ID.

        Returns:
            Agent ID if found, None otherwise.
        """
        if user_id in self._agent_cache:
            return self._agent_cache[user_id]

        agent_name = self._get_agent_name(user_id)
        existing = await self._find_agent_by_name(agent_name)

        if existing:
            self._agent_cache[user_id] = existing.id
            return existing.id

        return None

    async def clear_agent(self, user_id: int) -> bool:
        """Delete an agent and its memory.

        Args:
            user_id: Discord user ID.

        Returns:
            True if agent was deleted, False if not found.
        """
        agent_id = await self.get_agent_id(user_id)
        if not agent_id:
            return False

        await self.client.agents.delete(agent_id=agent_id)
        self._agent_cache.pop(user_id, None)

        logger.info(f"Deleted agent for user {user_id}")
        return True

    async def delete_agent_by_id(self, user_id: int, agent_id: str) -> bool:
        """Delete an agent by its ID directly.

        Use this when you already have the agent_id and want to avoid
        additional API calls that might hang or fail.

        Args:
            user_id: Discord user ID (for cache cleanup).
            agent_id: The agent ID to delete.

        Returns:
            True if deletion succeeded.
        """
        await self.client.agents.delete(agent_id=agent_id)
        self._agent_cache.pop(user_id, None)
        logger.info(f"Deleted agent {agent_id} for user {user_id}")
        return True

    async def _find_agent_by_name(self, name: str) -> AgentState | None:
        """Find an agent by name.

        Args:
            name: Agent name to search for.

        Returns:
            AgentState if found, None otherwise.
        """
        try:
            agents_page = await self.client.agents.list()

            # Defensive: ensure we have a valid page with items
            if not agents_page or not hasattr(agents_page, "items"):
                logger.warning("agents.list() returned unexpected structure")
                return None

            # items could be None in some edge cases
            items = agents_page.items or []

            for agent in items:
                if agent.name == name:
                    return agent

            return None
        except Exception as e:
            logger.exception(f"Failed to list agents while searching for {name}: {e}")
            return None

    async def _create_agent(
        self,
        user_id: int,
        user_name: str,
        timezone: str,
    ) -> AgentState:
        """Create a new agent for a user.

        Note: Caller must ensure _ensure_tools_registered() was called first.

        Args:
            user_id: Discord user ID.
            user_name: User's display name.
            timezone: User's timezone.

        Returns:
            Created AgentState.
        """
        agent_name = self._get_agent_name(user_id)

        # Create memory blocks
        memory_blocks = [
            {"label": PERSONA_LABEL, "value": PERSONA_BLOCK},
            {
                "label": HUMAN_LABEL,
                "value": create_human_block(
                    name=user_name,
                    timezone=timezone,
                    discord_id=user_id,
                ),
            },
            {"label": CONTEXT_LABEL, "value": CONTEXT_BLOCK},
        ]

        # Create agent with tools if available
        create_kwargs: dict[str, Any] = {
            "name": agent_name,
            "model": self.config.model,
            "embedding": self.config.embedding,
            "memory_blocks": memory_blocks,
        }

        # Combine native tool IDs and MCP tool IDs (convert set to list)
        all_tool_ids = self._tool_ids + list(self._mcp_tool_ids)
        if all_tool_ids:
            create_kwargs["tool_ids"] = all_tool_ids
            logger.info(
                f"Creating agent with {len(all_tool_ids)} tools "
                f"({len(self._tool_ids)} native, {len(self._mcp_tool_ids)} MCP)"
            )
        else:
            # Warn if tools were configured but none registered
            if self.config.mcp_servers or self.tool_registry.tools:
                logger.warning(
                    "Agent created with NO tools despite configuration. "
                    f"MCP servers configured: {len(self.config.mcp_servers)}, "
                    f"Native tools registered: {len(self.tool_registry.tools)}. "
                    "Check logs for registration failures."
                )
            else:
                logger.info("Agent created without tools (none configured)")

        agent = await self.client.agents.create(**create_kwargs)

        return agent

    def _get_agent_name(self, user_id: int) -> str:
        """Generate agent name from user ID.

        Args:
            user_id: Discord user ID.

        Returns:
            Agent name in format "erebus-{user_id}".
        """
        return f"erebus-{user_id}"

    async def _sync_agent_tools(self, agent_id: str) -> None:
        """Sync an existing agent's tools with the current registry.

        Adds any new tools that aren't already attached to the agent.
        This ensures existing agents get new tools when the bot is updated.

        Args:
            agent_id: The agent ID to update.
        """
        # Combine native and MCP tool IDs (convert set to list)
        all_tool_ids = self._tool_ids + list(self._mcp_tool_ids)

        if not all_tool_ids:
            logger.debug("No tools to sync")
            return

        try:
            # Get agent's current tools
            agent = await self.client.agents.retrieve(agent_id=agent_id)
            current_tool_ids = set(agent.tool_ids or [])
            new_tool_ids = set(all_tool_ids)

            # Find tools that need to be added
            missing_tools = new_tool_ids - current_tool_ids

            if not missing_tools:
                logger.debug(f"Agent {agent_id} already has all {len(new_tool_ids)} tools")
                return

            # Add missing tools to agent
            logger.info(
                f"Syncing {len(missing_tools)} new tools to agent {agent_id} "
                f"(had {len(current_tool_ids)}, now {len(new_tool_ids)})"
            )

            attached_count = 0
            failed_tools: list[str] = []
            for tool_id in missing_tools:
                try:
                    await self.client.agents.tools.attach(
                        agent_id=agent_id,
                        tool_id=tool_id,
                    )
                    attached_count += 1
                    logger.debug(f"Attached tool {tool_id} to agent")
                except Exception as e:
                    failed_tools.append(tool_id)
                    logger.warning(f"Failed to attach tool {tool_id}: {e}")

            # Log summary
            if failed_tools:
                logger.warning(
                    f"Tool sync completed with errors: {attached_count} attached, "
                    f"{len(failed_tools)} failed ({', '.join(failed_tools)})"
                )
            else:
                logger.info(f"Tool sync completed: {attached_count} tools attached")

        except Exception as e:
            logger.warning(f"Failed to sync tools for agent {agent_id}: {e}")

    # Maximum messages to check for pending approvals on startup.
    # Letta blocks new messages when in approval state, so pending requests
    # should be in recent history. Set conservatively to catch edge cases
    # where multiple rapid tool calls were made before the crash.
    PENDING_APPROVAL_CHECK_LIMIT = 50

    async def _cancel_pending_approvals(self, agent_id: str) -> int:
        """Cancel all pending tool approval requests for an agent.

        This is a recovery mechanism for when the bot crashes while tools are
        awaiting client-side approval. Letta agents enter PENDING_APPROVAL state
        when a tool with default_requires_approval=True is called, and remain in
        this state until an approval/rejection message is sent.

        Called on startup when finding an existing agent to ensure the agent
        isn't stuck from a previous session.

        Args:
            agent_id: The agent ID to check for pending approvals.

        Returns:
            Number of pending approvals that were cancelled (0 if none found
            or if an error occurred).
        """
        logger.debug(f"Checking for pending approvals on agent {agent_id}")

        try:
            # List recent messages to check for pending approvals
            messages = await self.client.agents.messages.list(
                agent_id=agent_id,
                limit=self.PENDING_APPROVAL_CHECK_LIMIT,
            )

            if not messages:
                logger.debug(f"No messages found for agent {agent_id}")
                return 0

            # Process ALL pending approval requests, not just the first
            cancelled_count = 0
            for msg in messages:
                msg_type = getattr(msg, "message_type", None)
                if msg_type != "approval_request_message":
                    continue

                # Extract the tool call ID from the pending request
                tool_call = getattr(msg, "tool_call", None)
                if tool_call is None:
                    logger.warning("Found approval_request_message without tool_call")
                    continue

                tool_call_id = getattr(tool_call, "tool_call_id", None)
                tool_name = getattr(tool_call, "name", "unknown")

                if not tool_call_id:
                    logger.warning(f"Pending approval for {tool_name} missing tool_call_id")
                    continue

                # Cancel the pending approval by sending an error response
                logger.warning(
                    f"RECOVERY: Found pending approval for tool '{tool_name}' "
                    f"(id={tool_call_id}). Cancelling due to bot restart."
                )

                try:
                    await self.client.agents.messages.create(
                        agent_id=agent_id,
                        messages=[
                            {
                                "type": "approval",
                                "approvals": [
                                    {
                                        "type": "tool",
                                        "tool_call_id": tool_call_id,
                                        "tool_return": (
                                            "Tool execution was interrupted. "
                                            "Please try your request again."
                                        ),
                                        "status": "error",
                                    }
                                ],
                            }
                        ],
                    )
                    cancelled_count += 1
                    logger.warning(
                        f"RECOVERY: Successfully cancelled pending approval for '{tool_name}'"
                    )
                except Exception as e:
                    logger.error(
                        f"Failed to cancel pending approval for '{tool_name}': {e}",
                        exc_info=True,
                    )

            if cancelled_count > 0:
                logger.warning(
                    f"RECOVERY: Cancelled {cancelled_count} pending approval(s) for agent {agent_id}"
                )
            else:
                logger.debug(f"No pending approvals found for agent {agent_id}")

            return cancelled_count

        except Exception as e:
            logger.error(
                f"Failed to check pending approvals for agent {agent_id}: {e}",
                exc_info=True,
            )
            return 0

    async def _ensure_mcp_servers_registered(self) -> None:
        """Register MCP servers with Letta (lazy initialization).

        MCP servers are registered once on first use. Letta handles the MCP
        connection and tool execution in its Docker environment.

        Note: stdio transport only works when Letta runs in Docker.
        """
        async with self._mcp_registration_lock:
            if self._mcp_registered:
                return

            if not self.config.mcp_servers:
                self._mcp_registered = True
                return

            logger.info(
                f"Registering {len(self.config.mcp_servers)} MCP servers with Letta..."
            )

            # Clear any stale data from previous registration attempts
            self._mcp_tool_ids.clear()
            self._mcp_tool_names.clear()
            failed_servers: list[str] = []

            for mcp_config in self.config.mcp_servers:
                try:
                    # Check if server already exists (upsert pattern)
                    existing = await self._find_mcp_server_by_name(mcp_config.name)
                    if existing:
                        self._mcp_server_ids[mcp_config.name] = existing
                        logger.info(
                            f"MCP server '{mcp_config.name}' already exists ({existing}). "
                            f"Reusing existing configuration."
                        )
                    else:
                        # Register new MCP server
                        # SECURITY: env dict contains API keys. Letta SDK should not log it.
                        server = await self.client.mcp_servers.create(
                            server_name=mcp_config.name,
                            config={
                                "mcp_server_type": "stdio",
                                "command": mcp_config.command,
                                "args": mcp_config.args,
                                "env": mcp_config.env,
                            },
                        )
                        self._mcp_server_ids[mcp_config.name] = server.id
                        logger.info(
                            f"Registered MCP server: {mcp_config.name} ({server.id})"
                        )

                    # List tools from this server
                    server_id = self._mcp_server_ids[mcp_config.name]
                    tools = await self.client.mcp_servers.tools.list(server_id)

                    # Defensive validation
                    if not tools:
                        logger.warning(
                            f"MCP server '{mcp_config.name}' returned no tools. "
                            f"Check Letta logs for server startup errors."
                        )
                        continue

                    # Collect tool IDs and names for agent creation (set prevents duplicates)
                    tool_count = 0
                    tools_without_names = 0
                    for tool in tools:
                        if not hasattr(tool, "id") or not tool.id:
                            logger.warning(
                                f"MCP tool missing ID in {mcp_config.name}: {tool}"
                            )
                            continue
                        tool_name = getattr(tool, "name", None)
                        self._mcp_tool_ids.add(tool.id)
                        if tool_name:
                            self._mcp_tool_names.add(tool_name)
                            tool_count += 1
                            logger.debug(
                                f"Found MCP tool: {tool_name} ({tool.id})"
                            )
                        else:
                            tools_without_names += 1
                            logger.warning(
                                f"MCP tool missing name in {mcp_config.name} (id={tool.id})"
                            )

                    if tools_without_names > 0:
                        logger.warning(
                            f"MCP server {mcp_config.name}: {tools_without_names} tools "
                            f"missing names and cannot be called"
                        )

                    logger.info(
                        f"MCP server {mcp_config.name} provides {tool_count} tools"
                    )

                except Exception as e:
                    failed_servers.append(mcp_config.name)
                    logger.exception(
                        f"Failed to register MCP server {mcp_config.name}: {e}. "
                        f"Check: (1) Letta server is running, "
                        f"(2) '{mcp_config.command}' is available in Letta container, "
                        f"(3) API credentials are valid, (4) Letta logs for errors."
                    )

            self._mcp_registered = True

            # Surface failures clearly
            if failed_servers:
                logger.error(
                    f"MCP registration completed with failures: "
                    f"{', '.join(failed_servers)}. "
                    f"Agents will be created without these MCP tools."
                )

            logger.info(
                f"MCP registration complete: {len(self._mcp_server_ids)} servers, "
                f"{len(self._mcp_tool_ids)} tools"
            )

    async def _find_mcp_server_by_name(self, name: str) -> str | None:
        """Find an MCP server by name.

        Args:
            name: Server name to search for.

        Returns:
            Server ID if found, None otherwise.
        """
        try:
            servers = await self.client.mcp_servers.list()
            for server in servers:
                if server.server_name == name:
                    return server.id
            return None
        except Exception as e:
            logger.warning(f"Failed to list MCP servers: {e}")
            return None

    async def _ensure_tools_registered(self) -> None:
        """Register native tools with Letta server (lazy initialization).

        Tools are registered once on first use. Each tool is created with
        a stub implementation since actual execution happens locally.
        """
        async with self._tools_registration_lock:
            if self._tools_registered:
                return

            if not self.tool_registry.tools:
                self._tools_registered = True
                return

            logger.info(
                f"Registering {len(self.tool_registry.tools)} tools with Letta..."
            )

            for tool_def in self.tool_registry.tools:
                try:
                    import json

                    # Sanitize name to be a valid Python identifier
                    safe_name = self._sanitize_tool_name(tool_def.name)

                    # Escape description for use in docstring
                    safe_desc = json.dumps(tool_def.description)[1:-1]

                    # Create a stub function - actual execution happens locally
                    stub_code = f'''def {safe_name}(**kwargs):
    """{safe_desc}"""
    raise RuntimeError("This tool executes client-side only")
'''
                    # Using upsert to handle existing tools gracefully
                    # default_requires_approval=True makes Letta return an approval
                    # request instead of executing server-side
                    tool = await self.client.tools.upsert(
                        source_code=stub_code,
                        json_schema={
                            "name": safe_name,
                            "description": tool_def.description,
                            "parameters": tool_def.input_schema,
                        },
                        default_requires_approval=True,
                    )
                    self._tool_ids.append(tool.id)
                    logger.debug(f"Registered tool: {safe_name} (id={tool.id})")

                except Exception as e:
                    logger.exception(f"Failed to register tool {tool_def.name}: {e}")

            self._tools_registered = True
            logger.info(f"Registered {len(self._tool_ids)} tools with Letta")

    def _sanitize_tool_name(self, name: str) -> str:
        """Sanitize a tool name to be a valid Python identifier.

        Args:
            name: Original tool name.

        Returns:
            Sanitized name safe for use in generated code.

        Raises:
            ValueError: If name cannot be sanitized to a valid identifier.
        """
        import keyword
        import re

        # Replace non-alphanumeric chars (except underscore) with underscore
        sanitized = re.sub(r"[^a-zA-Z0-9_]", "_", name)
        # Ensure it doesn't start with a digit
        if sanitized and sanitized[0].isdigit():
            sanitized = "_" + sanitized
        # Fallback if empty
        if not sanitized:
            sanitized = "tool"

        # Check for Python keywords
        if keyword.iskeyword(sanitized):
            sanitized = f"{sanitized}_tool"

        return sanitized

    def _extract_function_call(self, response: Any) -> tuple[str, dict[str, Any], str] | None:
        """Extract the most recent PENDING function call from Letta response.

        Looks for both approval_request_message (for client-side tools with
        default_requires_approval=True) and tool_call_message (for server-side tools).

        IMPORTANT: After an MCP tool executes, Letta returns a response containing
        both historical tool calls AND any new pending tool call. We must:
        1. Filter out already-resolved tool calls (those with tool_return_message)
        2. Find the most recent pending tool call (iterate in reverse order)

        Args:
            response: Letta API response.

        Returns:
            Tuple of (tool_name, arguments, call_id) for the most recent pending
            function call, or None if no pending calls exist.
        """
        if not hasattr(response, "messages") or response.messages is None:
            logger.debug("Response has no messages")
            return None

        messages = response.messages
        logger.debug(f"Response has {len(messages)} messages")

        # First pass: collect all resolved tool_call_ids from tool_return_message
        # These are tool calls that have already been executed and returned
        resolved_call_ids: set[str] = set()
        for msg in messages:
            msg_type = getattr(msg, "message_type", None) or type(msg).__name__
            if msg_type == "tool_return_message":
                tool_call = getattr(msg, "tool_call", None)
                if tool_call:
                    call_id = getattr(tool_call, "tool_call_id", None)
                    if call_id:
                        resolved_call_ids.add(call_id)

        if resolved_call_ids:
            logger.debug(f"Found {len(resolved_call_ids)} resolved tool calls")

        # Second pass: iterate in reverse to find the MOST RECENT PENDING tool call
        for i in range(len(messages) - 1, -1, -1):
            msg = messages[i]
            msg_type = getattr(msg, "message_type", None) or type(msg).__name__
            logger.debug(f"  Message {i}: type={msg_type}")

            # Check for client-side tools (approval_request_message) and
            # server-side tools (tool_call_message)
            if msg_type in ("approval_request_message", "tool_call_message"):
                tool_call = getattr(msg, "tool_call", None)
                if tool_call is None:
                    logger.debug(f"  Message {i} has no tool_call attribute")
                    continue

                name = getattr(tool_call, "name", None)
                args = getattr(tool_call, "arguments", "{}")
                call_id = getattr(tool_call, "tool_call_id", None)

                # Validate required fields
                if not name:
                    logger.warning(f"  Tool call missing name in message {i}")
                    continue
                if not call_id:
                    logger.warning(f"  Tool call {name} missing tool_call_id in message {i}")
                    continue

                # Skip already-resolved tool calls
                if call_id in resolved_call_ids:
                    logger.debug(f"  Skipping resolved tool call: {name} ({call_id})")
                    continue

                logger.debug(f"  Found pending tool call: {name} ({call_id})")

                # Parse arguments (stored as JSON string)
                if isinstance(args, str):
                    import json

                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        logger.warning(f"Failed to parse tool arguments: {args}")
                        args = {}

                return (name, args, call_id)

        return None

    def _extract_response_text(self, response: Any) -> str:
        """Extract text content from Letta response.

        Args:
            response: Letta API response.

        Returns:
            Text content from the response.
        """
        # Skip message types that don't contain user-facing text
        skip_types = {
            "approval_request_message",
            "tool_call_message",
            "tool_return_message",
            "reasoning_message",
            "hidden_reasoning_message",
        }

        if hasattr(response, "messages"):
            for msg in response.messages:
                msg_type = getattr(msg, "message_type", None) or type(msg).__name__
                if msg_type in skip_types:
                    continue

                # assistant_message contains the actual response to the user
                if hasattr(msg, "content") and msg.content:
                    return msg.content
        elif hasattr(response, "content"):
            return response.content

        # Fallback: convert to string
        return str(response)

    async def health_check(self) -> bool:
        """Check if Letta server is healthy.

        Returns:
            True if server is responding, False otherwise.
        """
        try:
            # Try to list agents as a health check
            await self.client.agents.list()
            return True
        except Exception as e:
            logger.warning(f"Letta health check failed: {e}")
            return False
