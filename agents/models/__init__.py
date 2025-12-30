"""Model providers for AI interactions.

This module provides abstraction over different AI model providers.
For MVP, only Anthropic/Claude is supported.
"""

from agents.models.anthropic import AnthropicProvider
from agents.models.base import (
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
    # Provider
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
