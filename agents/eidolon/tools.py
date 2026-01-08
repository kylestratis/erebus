"""Tool registration helpers for EidolonMemory.

Provides utilities for registering native tools (like vault operations)
and converting between tool formats.

Note: Native tools are executed by the bot, not by Letta directly.
This is because vault operations need access to the local filesystem.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from agents.models.base import ToolDefinition

logger = logging.getLogger(__name__)


class NativeToolExecutor(Protocol):
    """Protocol for native tool executors.

    Native tools are executed directly in-process rather than by Letta.
    This allows tools like Vault operations to run with local filesystem access.
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


def convert_to_letta_tool_format(tool: ToolDefinition) -> dict[str, Any]:
    """Convert a ToolDefinition to Letta's tool format.

    Args:
        tool: Internal tool definition.

    Returns:
        Dict in Letta's expected format.
    """
    return {
        "name": tool.name,
        "description": tool.description,
        "parameters": tool.input_schema,
    }


def convert_tools_to_letta_format(
    tools: list[ToolDefinition],
) -> list[dict[str, Any]]:
    """Convert a list of ToolDefinitions to Letta format.

    Args:
        tools: List of internal tool definitions.

    Returns:
        List of dicts in Letta's expected format.
    """
    return [convert_to_letta_tool_format(tool) for tool in tools]


def get_tool_names(tools: list[ToolDefinition]) -> list[str]:
    """Extract tool names from a list of definitions.

    Args:
        tools: List of tool definitions.

    Returns:
        List of tool names.
    """
    return [tool.name for tool in tools]


class ToolRegistry:
    """Registry for native tools available to EidolonMemory.

    Manages tool definitions and executors for native tools that
    run in the bot process (not in Letta's environment).
    """

    def __init__(self) -> None:
        """Initialize empty tool registry."""
        self._tools: list[ToolDefinition] = []
        self._executors: list[NativeToolExecutor] = []

    def register(
        self,
        tools: list[ToolDefinition],
        executor: NativeToolExecutor,
    ) -> None:
        """Register tools with their executor.

        Args:
            tools: Tool definitions to register.
            executor: Executor that handles these tools.
        """
        self._tools.extend(tools)
        self._executors.append(executor)
        logger.info(f"Registered {len(tools)} native tools")

    @property
    def tools(self) -> list[ToolDefinition]:
        """Get all registered tool definitions."""
        return self._tools.copy()

    @property
    def tool_names(self) -> list[str]:
        """Get names of all registered tools."""
        return get_tool_names(self._tools)

    async def execute(self, tool_name: str, arguments: dict[str, Any]) -> str:
        """Execute a tool by name.

        Args:
            tool_name: Name of the tool to execute.
            arguments: Tool arguments.

        Returns:
            Tool execution result as a string.

        Raises:
            ValueError: If no executor can handle the tool.
        """
        for executor in self._executors:
            if executor.can_handle(tool_name):
                return await executor.execute(tool_name, arguments)

        raise ValueError(f"No executor found for tool: {tool_name}")

    def can_handle(self, tool_name: str) -> bool:
        """Check if any executor can handle a tool.

        Args:
            tool_name: Name of the tool to check.

        Returns:
            True if any executor can handle the tool.
        """
        return any(executor.can_handle(tool_name) for executor in self._executors)
