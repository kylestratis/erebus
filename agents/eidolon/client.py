"""EidolonMemory client for Letta integration.

Provides a wrapper around the Letta SDK for managing per-user agents
with persistent memory.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from letta_client import Letta

from agents.eidolon.memory import (
    CONTEXT_BLOCK,
    CONTEXT_LABEL,
    HUMAN_LABEL,
    PERSONA_BLOCK,
    PERSONA_LABEL,
    create_human_block,
)
from agents.eidolon.tools import ToolRegistry

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
    """

    base_url: str = "http://localhost:8283"
    api_key: str | None = None
    model: str = DEFAULT_MODEL
    embedding: str = DEFAULT_EMBEDDING
    default_timezone: str = "America/New_York"


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

    Attributes:
        config: EidolonMemory configuration.
        client: Letta SDK client.
        tool_registry: Registry for native tools.
    """

    # Maximum tool execution iterations to prevent infinite loops
    MAX_TOOL_ITERATIONS = 10

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

        # Initialize Letta client
        self.client = Letta(
            base_url=self.config.base_url,
            token=self.config.api_key,
        )

        # Cache of user_id -> agent_id mappings
        self._agent_cache: dict[int, str] = {}

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
        # Check cache first
        if user_id in self._agent_cache:
            return self._agent_cache[user_id]

        # Try to find existing agent by name
        agent_name = self._get_agent_name(user_id)
        existing = await self._find_agent_by_name(agent_name)

        if existing:
            self._agent_cache[user_id] = existing.id
            logger.info(f"Found existing agent for user {user_id}: {existing.id}")
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
        response = self.client.agents.messages.create(
            agent_id=agent_id,
            messages=[{"role": "user", "content": message}],
        )

        # Handle tool execution loop
        iterations = 0
        while iterations < self.MAX_TOOL_ITERATIONS:
            # Check for function calls that need local execution
            tool_call = self._extract_function_call(response)

            if tool_call is None:
                # No function call, we have a final response
                break

            tool_name, tool_args, call_id = tool_call

            # Check if this is a native tool we handle
            if not self.tool_registry.can_handle(tool_name):
                # Letta should handle this tool internally
                logger.debug(f"Tool {tool_name} not in registry, skipping")
                break

            # Execute tool locally
            logger.info(f"Executing native tool: {tool_name}")
            try:
                result = await self.tool_registry.execute(tool_name, tool_args)
            except Exception as e:
                logger.exception(f"Tool execution failed: {tool_name}")
                result = f"Error executing tool: {e}"

            # Send result back to agent
            response = self.client.agents.messages.create(
                agent_id=agent_id,
                messages=[
                    {
                        "role": "tool",
                        "tool_call_id": call_id,
                        "content": result,
                    }
                ],
            )

            iterations += 1

        if iterations >= self.MAX_TOOL_ITERATIONS:
            logger.warning(f"Tool execution loop hit max iterations for user {user_id}")

        # Extract text response
        return self._extract_response_text(response)

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

        self.client.agents.delete(agent_id=agent_id)
        self._agent_cache.pop(user_id, None)

        logger.info(f"Deleted agent for user {user_id}")
        return True

    async def _find_agent_by_name(self, name: str) -> AgentState | None:
        """Find an agent by name.

        Args:
            name: Agent name to search for.

        Returns:
            AgentState if found, None otherwise.
        """
        agents = self.client.agents.list()
        for agent in agents:
            if agent.name == name:
                return agent
        return None

    async def _create_agent(
        self,
        user_id: int,
        user_name: str,
        timezone: str,
    ) -> AgentState:
        """Create a new agent for a user.

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

        # Create agent
        agent = self.client.agents.create(
            name=agent_name,
            model=self.config.model,
            embedding=self.config.embedding,
            memory_blocks=memory_blocks,
        )

        return agent

    def _get_agent_name(self, user_id: int) -> str:
        """Generate agent name from user ID.

        Args:
            user_id: Discord user ID.

        Returns:
            Agent name in format "erebus-{user_id}".
        """
        return f"erebus-{user_id}"

    def _extract_function_call(
        self, response: Any
    ) -> tuple[str, dict[str, Any], str] | None:
        """Extract function call from Letta response if present.

        Args:
            response: Letta API response.

        Returns:
            Tuple of (tool_name, arguments, call_id) if a function call
            is present, None otherwise.
        """
        if not hasattr(response, "messages"):
            return None

        for msg in response.messages:
            # Check for function/tool call message types
            # Letta uses different message types for tool calls
            msg_type = getattr(msg, "message_type", None) or type(msg).__name__

            if msg_type in ("function_call", "tool_call", "FunctionCallMessage"):
                # Extract tool call details
                name = getattr(msg, "function_call", {}).get("name") or getattr(
                    msg, "name", None
                )
                args = getattr(msg, "function_call", {}).get("arguments") or getattr(
                    msg, "arguments", {}
                )
                call_id = getattr(msg, "id", "") or getattr(msg, "tool_call_id", "")

                if name:
                    # Parse arguments if they're a string (JSON)
                    if isinstance(args, str):
                        import json

                        try:
                            args = json.loads(args)
                        except json.JSONDecodeError:
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
        # The response structure depends on Letta version
        # Handle both possible formats
        if hasattr(response, "messages"):
            for msg in response.messages:
                # Skip function call messages
                msg_type = getattr(msg, "message_type", None) or type(msg).__name__
                if msg_type in ("function_call", "tool_call", "FunctionCallMessage"):
                    continue

                if hasattr(msg, "content") and msg.content:
                    return msg.content
        elif hasattr(response, "content"):
            return response.content

        # Fallback: convert to string
        return str(response)

    def health_check(self) -> bool:
        """Check if Letta server is healthy.

        Returns:
            True if server is responding, False otherwise.
        """
        try:
            # Try to list agents as a health check
            self.client.agents.list()
            return True
        except Exception as e:
            logger.warning(f"Letta health check failed: {e}")
            return False
