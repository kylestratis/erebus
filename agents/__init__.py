"""Agents module for Erebus.

Contains AI model providers, MCP integrations, and EidolonMemory wrapper.
"""

from agents.config import AgentConfig
from agents.mcp import MCPClientManager, MCPServerConfig, MCPToolExecutor
from agents.mcp.client import create_todoist_config
from agents.models import (
    AnthropicProvider,
    AuthenticationError,
    Message,
    ModelError,
    ModelProvider,
    RateLimitError,
    Response,
    Role,
    ToolDefinition,
    ToolResult,
    ToolUse,
)

__all__ = [
    # Config
    "AgentConfig",
    # MCP
    "MCPClientManager",
    "MCPServerConfig",
    "MCPToolExecutor",
    "create_todoist_config",
    # Providers
    "AnthropicProvider",
    "ModelProvider",
    # Data classes
    "Message",
    "Response",
    "Role",
    "ToolDefinition",
    "ToolResult",
    "ToolUse",
    # Errors
    "AuthenticationError",
    "ModelError",
    "RateLimitError",
]
