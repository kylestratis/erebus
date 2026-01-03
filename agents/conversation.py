"""Conversation management for Erebus.

Handles per-user conversation history and context management.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol

from agents.config import DEFAULT_AGENT_CONFIG, AgentConfig
from agents.models import (
    Message,
    ModelProvider,
    Response,
    Role,
    ToolDefinition,
    ToolResult,
    ToolUse,
)

if TYPE_CHECKING:
    from agents.mcp import MCPClientManager

logger = logging.getLogger(__name__)


class NativeToolExecutor(Protocol):
    """Protocol for native tool executors.

    Native tools are executed directly in-process rather than via MCP.
    This allows tools like Vault operations to run without subprocess overhead.
    """

    def can_handle(self, tool_name: str) -> bool:
        """Check if this executor handles a tool.

        Args:
            tool_name: Name of the tool to check.

        Returns:
            True if this executor can handle the tool.
        """
        ...

    async def execute(self, tool_name: str, arguments: dict[str, Any]) -> str:
        """Execute a tool and return the result.

        Args:
            tool_name: Name of the tool to execute.
            arguments: Tool arguments.

        Returns:
            Tool execution result as a string.
        """
        ...


# Default system prompt for Erebus
DEFAULT_SYSTEM_PROMPT = """You are Erebus, a personal AI assistant that operates through Discord.

Your personality:
- You are helpful, concise, dark, and occasionally dry-witted
- You respect the user's time and get to the point
- You're knowledgeable but admit when you don't know something
- You have a subtle, mysterious aesthetic (you are named after the primordial darkness)

Guidelines:
- Keep responses concise unless detail is requested
- Use markdown formatting when helpful (Discord supports it)
- If asked about capabilities you don't have, be honest about limitations
- Use your available tools when they would help answer the user's question
- When using Todoist tools, be helpful with task management
- When using vault tools, help manage notes and ideas in Obsidian

Safety guidelines for destructive operations:
- Before completing a task (todoist_close_task), state which task you will mark done and ask for confirmation
- Before deleting a task (todoist_delete_task), always ask for explicit confirmation with task details
- When multiple tasks could match a request, list the matching tasks and ask which one
- Wait for an affirmative response (e.g., "yes", "do it", task name) before executing destructive operations
- Before overwriting an existing note (vault_write_note with overwrite=true), confirm with the user

Current capabilities:
- Natural conversation and questions
- Todoist task management (when configured)
- Obsidian vault operations: read/write notes, search, daily notes, templates (when configured)
"""

# Maximum messages to retain in conversation history
MAX_HISTORY_MESSAGES = 50


@dataclass
class Conversation:
    """A conversation with a single user.

    Attributes:
        user_id: Discord user ID for this conversation.
        messages: List of messages in the conversation.
        system_prompt: System prompt for this conversation.
    """

    user_id: int
    messages: list[Message] = field(default_factory=list)
    system_prompt: str = DEFAULT_SYSTEM_PROMPT

    def add_user_message(self, content: str) -> None:
        """Add a user message to the conversation.

        Args:
            content: The message content.
        """
        self.messages.append(Message(role=Role.USER, content=content))
        self._trim_history()

    def add_assistant_message(self, response: Response) -> None:
        """Add an assistant message from a model response.

        Args:
            response: The model response.
        """
        self.messages.append(
            Message(
                role=Role.ASSISTANT,
                content=response.content,
                tool_uses=response.tool_uses,
            )
        )
        self._trim_history()

    def add_tool_results(self, tool_results: list[ToolResult]) -> None:
        """Add tool results as a user message.

        Args:
            tool_results: The tool execution results.
        """
        self.messages.append(
            Message(
                role=Role.USER,
                tool_results=tool_results,
            )
        )
        self._trim_history()

    def _trim_history(self) -> None:
        """Trim conversation history to stay within limits."""
        if len(self.messages) > MAX_HISTORY_MESSAGES:
            # Keep the most recent messages
            self.messages = self.messages[-MAX_HISTORY_MESSAGES:]
            logger.debug(
                f"Trimmed conversation history for user {self.user_id} "
                f"to {MAX_HISTORY_MESSAGES} messages"
            )

    def clear(self) -> None:
        """Clear the conversation history."""
        self.messages.clear()
        logger.info(f"Cleared conversation history for user {self.user_id}")


class ConversationManager:
    """Manages conversations across multiple users.

    Handles conversation state, model interaction, and history management.
    Supports both MCP tool integration and native tools for extended capabilities.

    Attributes:
        model: The model provider to use for completions.
        mcp: Optional MCP client manager for tool access.
        config: Agent configuration for behavior settings.
        conversations: Active conversations by user ID.
        native_tools: Tool definitions for native (non-MCP) tools.
        native_executors: Executors for native tools.
    """

    def __init__(
        self,
        model: ModelProvider,
        mcp: MCPClientManager | None = None,
        config: AgentConfig | None = None,
    ) -> None:
        """Initialize the conversation manager.

        Args:
            model: The model provider to use.
            mcp: Optional MCP client manager for tool access.
            config: Agent configuration. Uses defaults if not provided.
        """
        self.model = model
        self.mcp = mcp
        self.config = config or DEFAULT_AGENT_CONFIG
        self.conversations: dict[int, Conversation] = {}
        self._native_tools: list[ToolDefinition] = []
        self._native_executors: list[NativeToolExecutor] = []

    def register_native_tools(
        self,
        tools: list[ToolDefinition],
        executor: NativeToolExecutor,
    ) -> None:
        """Register native tools with an executor.

        Native tools are executed in-process rather than via MCP.
        This is useful for tools like vault operations that don't need
        subprocess isolation.

        Note: Native tools take priority over MCP tools with the same name.
        If multiple executors can handle the same tool, the first registered
        executor will be used.

        Args:
            tools: Tool definitions to register.
            executor: Executor that handles these tools.

        Raises:
            ValueError: If a tool name conflicts with existing native tools.
        """
        # Check for conflicts with existing native tools
        existing_names = {t.name for t in self._native_tools}
        new_names = {t.name for t in tools}
        conflicts = existing_names & new_names
        if conflicts:
            raise ValueError(
                f"Tool name collision detected: {conflicts}. "
                "Each tool name must be unique across all native tools."
            )

        # Warn about MCP conflicts (native tools will shadow them)
        if self.mcp:
            mcp_names = {t.name for t in self.mcp.get_all_tools()}
            mcp_conflicts = new_names & mcp_names
            if mcp_conflicts:
                logger.warning(
                    f"Native tools will shadow MCP tools with same names: {mcp_conflicts}"
                )

        self._native_tools.extend(tools)
        self._native_executors.append(executor)
        tool_names = [t.name for t in tools]
        logger.info(f"Registered {len(tools)} native tool(s): {tool_names}")

    def get_conversation(self, user_id: int) -> Conversation:
        """Get or create a conversation for a user.

        Args:
            user_id: Discord user ID.

        Returns:
            The conversation for this user.
        """
        if user_id not in self.conversations:
            self.conversations[user_id] = Conversation(user_id=user_id)
            logger.info(f"Created new conversation for user {user_id}")
        return self.conversations[user_id]

    def _get_all_tools(self) -> list[ToolDefinition] | None:
        """Get all available tools (MCP + native).

        Returns:
            Combined list of tool definitions, or None if no tools available.
        """
        tools: list[ToolDefinition] = []

        # Add MCP tools
        if self.mcp:
            tools.extend(self.mcp.get_all_tools())

        # Add native tools
        tools.extend(self._native_tools)

        return tools if tools else None

    async def chat(self, user_id: int, message: str) -> Response:
        """Send a message and get a response.

        Implements an agent loop that handles tool calls:
        1. Send message to model with available tools
        2. If model requests tool use, execute tools (native or MCP)
        3. Send tool results back to model
        4. Repeat until model returns final response

        Args:
            user_id: Discord user ID.
            message: The user's message.

        Returns:
            The model's response (final response after any tool calls).

        Raises:
            ModelError: If the model request fails.
        """
        conversation = self.get_conversation(user_id)
        conversation.add_user_message(message)

        # Get all available tools (MCP + native)
        tools = self._get_all_tools()
        has_tools = bool(tools)

        # Agent loop - handle tool calls until we get a final response
        total_input_tokens = 0
        total_output_tokens = 0
        iterations = 0

        for _ in range(self.config.max_tool_iterations):
            iterations += 1
            response = await self.model.complete(
                messages=conversation.messages,
                system=conversation.system_prompt,
                tools=tools,
            )

            total_input_tokens += response.usage.get("input_tokens", 0)
            total_output_tokens += response.usage.get("output_tokens", 0)

            # Add the assistant's response to conversation
            conversation.add_assistant_message(response)

            # If no tool use, we're done
            if not response.has_tool_use:
                break

            # Execute tool calls
            if has_tools:
                tool_results = await self._execute_tools(response.tool_uses)
                conversation.add_tool_results(tool_results)
                logger.debug(f"Executed {len(tool_results)} tool(s), continuing agent loop")
            else:
                # No tools available but model requested them - shouldn't happen
                logger.warning("Model requested tool use but no tools available")
                break
        else:
            logger.warning(
                f"Agent loop reached max iterations ({self.config.max_tool_iterations}) "
                f"for user {user_id}"
            )

        logger.debug(
            f"Chat with user {user_id}: "
            f"input_tokens={total_input_tokens}, "
            f"output_tokens={total_output_tokens}, "
            f"iterations={iterations}"
        )

        return response

    async def _execute_tools(self, tool_uses: list[ToolUse]) -> list[ToolResult]:
        """Execute tool calls via native executors or MCP.

        Routes each tool call to the appropriate executor:
        1. First checks if any native executor can handle the tool
        2. Falls back to MCP if no native executor handles it

        Args:
            tool_uses: List of tool use requests from the model.

        Returns:
            List of tool results.
        """
        results: list[ToolResult] = []

        for tool_use in tool_uses:
            try:
                result_content = await self._execute_single_tool(tool_use)
                results.append(
                    ToolResult(
                        tool_use_id=tool_use.id,
                        content=result_content,
                        is_error=False,
                    )
                )
                if self.config.log_tool_calls:
                    logger.debug(f"Tool {tool_use.name} executed successfully")
            except Exception as e:
                logger.exception(f"Tool {tool_use.name} failed: {e}")
                results.append(
                    ToolResult(
                        tool_use_id=tool_use.id,
                        content=f"Error executing tool: {e}",
                        is_error=True,
                    )
                )

        return results

    async def _execute_single_tool(self, tool_use: ToolUse) -> str:
        """Execute a single tool call.

        Args:
            tool_use: The tool use request from the model.

        Returns:
            Tool execution result as a string.

        Raises:
            RuntimeError: If no executor can handle the tool.
        """
        # Check native executors first
        for executor in self._native_executors:
            if executor.can_handle(tool_use.name):
                return await asyncio.wait_for(
                    executor.execute(tool_use.name, tool_use.input),
                    timeout=self.config.tool_call_timeout,
                )

        # Fall back to MCP
        if self.mcp is not None:
            return await asyncio.wait_for(
                self.mcp.call_tool(
                    tool_name=tool_use.name,
                    arguments=tool_use.input,
                ),
                timeout=self.config.tool_call_timeout,
            )

        raise RuntimeError(f"No executor found for tool: {tool_use.name}")

    def clear_conversation(self, user_id: int) -> bool:
        """Clear a user's conversation history.

        Args:
            user_id: Discord user ID.

        Returns:
            True if conversation existed and was cleared.
        """
        if user_id in self.conversations:
            self.conversations[user_id].clear()
            return True
        return False
