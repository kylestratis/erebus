"""Agents module for Erebus.

Contains AI model providers and agent implementations.
"""

from agents.config import AgentConfig
from agents.conversation import Conversation, ConversationManager
from agents.mcp import MCPClientManager, MCPServerConfig
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
    # Conversation
    "Conversation",
    "ConversationManager",
    # MCP
    "MCPClientManager",
    "MCPServerConfig",
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
