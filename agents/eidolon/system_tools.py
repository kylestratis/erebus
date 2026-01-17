"""System introspection tools for EidolonMemory.

Provides tools that allow the agent to inspect its own capabilities,
scheduled jobs, and connection status.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Coroutine
from typing import TYPE_CHECKING, Any

from agents.models.base import ToolDefinition

if TYPE_CHECKING:
    from agents.eidolon.tools import ToolRegistry
    from agents.mcp.client import MCPClientManager
    from bot.scheduler import Scheduler

logger = logging.getLogger(__name__)


def get_system_tool_definitions() -> list[ToolDefinition]:
    """Get system introspection tool definitions.

    Returns:
        List of tool definitions for system introspection.
    """
    return [
        ToolDefinition(
            name="system_status",
            description=(
                "ALWAYS call this tool when asked about your capabilities, tools, "
                "or what you can do. Returns the real-time list of available tools, "
                "scheduled jobs, and MCP connections. Do NOT answer from memory - "
                "this tool provides accurate, up-to-date information about your "
                "actual capabilities. Call with include_tool_details=true for "
                "full descriptions."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "include_tool_details": {
                        "type": "boolean",
                        "description": (
                            "Set to true to include detailed descriptions for each tool. "
                            "Recommended when the user asks what tools do or how they work."
                        ),
                    },
                },
                "required": [],
            },
        ),
    ]


class SystemToolExecutor:
    """Executes system introspection tool calls.

    Provides the agent with visibility into its own configuration,
    available tools, and scheduled jobs.

    Attributes:
        tool_registry: Registry of available tools.
        scheduler: Job scheduler (optional).
        mcp: MCP client manager (optional).
    """

    def __init__(
        self,
        tool_registry: ToolRegistry,
        scheduler: Scheduler | None = None,
        mcp: MCPClientManager | None = None,
    ) -> None:
        """Initialize the executor.

        Args:
            tool_registry: The tool registry to query.
            scheduler: Optional scheduler for job status.
            mcp: Optional MCP client for connection status.
        """
        self._registry = tool_registry
        self._scheduler = scheduler
        self._mcp = mcp

        self._handlers: dict[str, Callable[..., Coroutine[Any, Any, str]]] = {
            "system_status": self._handle_system_status,
        }

    def can_handle(self, tool_name: str) -> bool:
        """Check if this executor handles a tool.

        Args:
            tool_name: Name of the tool.

        Returns:
            True if this executor handles the tool.
        """
        return tool_name in self._handlers

    async def execute(self, tool_name: str, arguments: dict[str, Any]) -> str:
        """Execute a system tool.

        Args:
            tool_name: Name of the tool to execute.
            arguments: Tool arguments.

        Returns:
            Tool execution result as a string.

        Raises:
            ValueError: If tool is not handled by this executor.
        """
        logger.debug(f"SystemToolExecutor.execute: {tool_name} with args={arguments}")
        handler = self._handlers.get(tool_name)
        if handler is None:
            logger.debug(f"Unknown system tool: {tool_name}")
            raise ValueError(f"Unknown system tool: {tool_name}")

        result = await handler(**arguments)
        logger.debug(f"System tool {tool_name} returned {len(result)} chars")
        return result

    async def _handle_system_status(
        self,
        include_tool_details: bool = False,
    ) -> str:
        """Handle system_status tool call.

        Args:
            include_tool_details: Whether to include tool descriptions.

        Returns:
            Formatted system status report.
        """
        sections = []

        # Tool status
        sections.append(self._format_tools_section(include_tool_details))

        # Scheduler status
        if self._scheduler:
            sections.append(self._format_scheduler_section())

        # MCP status
        if self._mcp:
            sections.append(self._format_mcp_section())

        return "\n\n".join(sections)

    def _format_tools_section(self, include_details: bool) -> str:
        """Format the tools section of the status report."""
        tools = self._registry.tools
        lines = [f"## Available Tools ({len(tools)} total)"]

        if not tools:
            lines.append("No tools registered.")
            return "\n".join(lines)

        # Group by prefix (vault_, todoist_, system_)
        groups: dict[str, list[ToolDefinition]] = {}
        for tool in tools:
            prefix = tool.name.split("_")[0] if "_" in tool.name else "other"
            groups.setdefault(prefix, []).append(tool)

        for prefix, group_tools in sorted(groups.items()):
            lines.append(f"\n### {prefix.title()} Tools ({len(group_tools)})")
            for tool in sorted(group_tools, key=lambda t: t.name):
                if include_details:
                    lines.append(f"- **{tool.name}**: {tool.description}")
                else:
                    lines.append(f"- {tool.name}")

        return "\n".join(lines)

    def _format_scheduler_section(self) -> str:
        """Format the scheduler section of the status report."""
        lines = ["## Scheduled Jobs"]

        if not self._scheduler:
            lines.append("Scheduler not available.")
            return "\n".join(lines)

        jobs = self._scheduler.jobs
        if not jobs:
            lines.append("No jobs registered.")
            return "\n".join(lines)

        for job in jobs.values():
            status = "✓ enabled" if job.enabled else "✗ disabled"
            lines.append(f"- **{job.name}** ({status})")
            lines.append(f"  - Schedule: `{job.cron}`")
            if job.description:
                lines.append(f"  - {job.description}")

        return "\n".join(lines)

    def _format_mcp_section(self) -> str:
        """Format the MCP connections section of the status report."""
        lines = ["## MCP Connections"]

        if not self._mcp or not self._mcp.is_initialized:
            lines.append("MCP client not initialized.")
            return "\n".join(lines)

        connections = self._mcp.connections
        if not connections:
            lines.append("No MCP servers connected.")
            return "\n".join(lines)

        for name, conn in connections.items():
            tool_count = len(conn.tools)
            lines.append(f"- **{name}**: {tool_count} tools available")

        return "\n".join(lines)
