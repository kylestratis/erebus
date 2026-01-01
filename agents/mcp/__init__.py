"""MCP (Model Context Protocol) client integration for Erebus.

Provides connectivity to MCP servers for tool access.
"""

from agents.mcp.client import MCPClientManager, MCPServerConfig

__all__ = [
    "MCPClientManager",
    "MCPServerConfig",
]
