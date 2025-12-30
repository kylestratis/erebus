"""Agents module for Erebus.

Contains AI model providers and agent implementations.
"""

from agents.conversation import Conversation, ConversationManager
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
    # Conversation
    "Conversation",
    "ConversationManager",
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
