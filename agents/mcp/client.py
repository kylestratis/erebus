"""MCP client manager for connecting to MCP servers.

Handles connection lifecycle, tool discovery, and tool execution
for one or more MCP servers.
"""

from __future__ import annotations

import logging
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from agents.models.base import ToolDefinition

logger = logging.getLogger(__name__)


@dataclass
class MCPServerConfig:
    """Configuration for an MCP server connection.

    Attributes:
        name: Unique identifier for this server.
        command: Command to run the server (e.g., "npx", "node", "python").
        args: Arguments to pass to the command.
        env: Environment variables to pass to the server.
    """

    name: str
    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] | None = None


@dataclass
class MCPConnection:
    """An active connection to an MCP server.

    Attributes:
        config: The server configuration.
        session: The MCP client session.
        tools: Available tools from this server.
    """

    config: MCPServerConfig
    session: ClientSession
    tools: list[ToolDefinition]


class MCPClientManager:
    """Manages connections to MCP servers.

    Handles lifecycle management, tool discovery, and tool execution
    across multiple MCP servers.

    Attributes:
        connections: Active server connections by name.
    """

    def __init__(self) -> None:
        """Initialize the MCP client manager."""
        self._exit_stack = AsyncExitStack()
        self._connections: dict[str, MCPConnection] = {}
        self._initialized = False

    @property
    def connections(self) -> dict[str, MCPConnection]:
        """Get active connections."""
        return self._connections

    @property
    def is_initialized(self) -> bool:
        """Check if the manager has been initialized."""
        return self._initialized

    async def start(self) -> None:
        """Start the client manager.

        Must be called before connecting to servers.
        """
        if self._initialized:
            return
        await self._exit_stack.__aenter__()
        self._initialized = True
        logger.info("MCP client manager started")

    async def stop(self) -> None:
        """Stop the client manager and close all connections.

        Handles cleanup errors gracefully to ensure resources are released.
        """
        if not self._initialized:
            return

        try:
            await self._exit_stack.aclose()
        except Exception as e:
            logger.exception(f"Error during MCP cleanup: {e}")
        finally:
            self._connections.clear()
            self._initialized = False
            logger.info("MCP client manager stopped")

    async def connect(self, config: MCPServerConfig) -> MCPConnection:
        """Connect to an MCP server.

        Args:
            config: Server configuration.

        Returns:
            The established connection.

        Raises:
            RuntimeError: If manager not started or server already connected.
            ConnectionError: If connection fails.
        """
        if not self._initialized:
            raise RuntimeError("MCPClientManager not started. Call start() first.")

        if config.name in self._connections:
            raise RuntimeError(f"Server '{config.name}' already connected")

        logger.info(f"Connecting to MCP server: {config.name}")
        logger.debug(f"Server command: {config.command} {' '.join(config.args)}")

        try:
            # Create server parameters
            server_params = StdioServerParameters(
                command=config.command,
                args=config.args,
                env=config.env,
            )

            # Establish stdio transport
            stdio_transport = await self._exit_stack.enter_async_context(
                stdio_client(server_params)
            )
            read_stream, write_stream = stdio_transport

            # Create and initialize session
            session = await self._exit_stack.enter_async_context(
                ClientSession(read_stream, write_stream)
            )
            await session.initialize()

            # Discover available tools
            tools_response = await session.list_tools()
            tools = [
                ToolDefinition(
                    name=f"{config.name}_{tool.name}",  # Prefix with server name
                    description=tool.description or f"Tool from {config.name}",
                    input_schema=tool.inputSchema,
                )
                for tool in tools_response.tools
            ]

            connection = MCPConnection(
                config=config,
                session=session,
                tools=tools,
            )
            self._connections[config.name] = connection

            logger.info(
                f"Connected to {config.name} with {len(tools)} tools: {[t.name for t in tools]}"
            )
            return connection

        except Exception as e:
            logger.exception(f"Failed to connect to MCP server {config.name}: {e}")
            raise ConnectionError(f"Failed to connect to {config.name}: {e}") from e

    async def disconnect(self, server_name: str) -> None:
        """Disconnect from an MCP server.

        Args:
            server_name: Name of the server to disconnect.

        Note:
            The actual cleanup happens when the exit stack closes.
            This method just removes the connection from tracking.
        """
        if server_name in self._connections:
            del self._connections[server_name]
            logger.info(f"Disconnected from MCP server: {server_name}")

    def get_all_tools(self) -> list[ToolDefinition]:
        """Get all available tools from all connected servers.

        Returns:
            List of all available tools.
        """
        tools: list[ToolDefinition] = []
        for connection in self._connections.values():
            tools.extend(connection.tools)
        return tools

    def get_tools_for_server(self, server_name: str) -> list[ToolDefinition]:
        """Get tools available from a specific server.

        Args:
            server_name: Name of the server.

        Returns:
            List of tools from that server.
        """
        if server_name not in self._connections:
            return []
        return self._connections[server_name].tools

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> str:
        """Call a tool on the appropriate MCP server.

        Tool names are prefixed with server name (e.g., "todoist_addTasks").
        This method parses the prefix to route to the correct server.

        Args:
            tool_name: Full tool name including server prefix.
            arguments: Arguments to pass to the tool.

        Returns:
            Tool execution result as a string.

        Raises:
            ValueError: If tool not found or server not connected.
        """
        # Parse server name from tool name prefix
        parts = tool_name.split("_", 1)
        if len(parts) != 2:
            raise ValueError(f"Invalid tool name format: {tool_name}")

        server_name, actual_tool_name = parts

        if server_name not in self._connections:
            raise ValueError(f"Server '{server_name}' not connected")

        connection = self._connections[server_name]

        logger.debug(f"Calling tool {actual_tool_name} on {server_name} with args: {arguments}")

        try:
            result = await connection.session.call_tool(actual_tool_name, arguments)

            # Extract content from result
            if result.content:
                # MCP returns content as a list of content blocks
                text_parts = []
                for block in result.content:
                    if hasattr(block, "text"):
                        text_parts.append(block.text)
                    elif hasattr(block, "data"):
                        text_parts.append(str(block.data))
                    else:
                        text_parts.append(str(block))
                return "\n".join(text_parts)
            return ""

        except Exception as e:
            logger.exception(f"Tool call failed: {tool_name}")
            raise RuntimeError(f"Tool call failed: {e}") from e


def create_todoist_config(api_key: str) -> MCPServerConfig:
    """Create configuration for the Todoist MCP server.

    Args:
        api_key: Todoist API key.

    Returns:
        Server configuration for Todoist.
    """
    return MCPServerConfig(
        name="todoist",
        command="npx",
        args=["@doist/todoist-ai"],
        env={
            "TODOIST_API_KEY": api_key,
            # Suppress dotenv debug output that interferes with JSONRPC
            "DOTENV_CONFIG_QUIET": "true",
        },
    )
