"""Abstract base class for model providers.

Defines the interface that all model providers must implement.
For MVP, only Claude/Anthropic is supported.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Role(Enum):
    """Message role in a conversation."""

    USER = "user"
    ASSISTANT = "assistant"


@dataclass
class ToolDefinition:
    """Definition of a tool the model can call.

    Attributes:
        name: Unique identifier for the tool.
        description: Human-readable description of what the tool does.
        input_schema: JSON Schema defining the tool's input parameters.
    """

    name: str
    description: str
    input_schema: dict[str, Any]


@dataclass
class ToolUse:
    """A request from the model to use a tool.

    Attributes:
        id: Unique identifier for this tool use.
        name: Name of the tool to call.
        input: Input arguments for the tool.
    """

    id: str
    name: str
    input: dict[str, Any]


@dataclass
class ToolResult:
    """Result of executing a tool.

    Attributes:
        tool_use_id: ID of the tool use this is a response to.
        content: The result content.
        is_error: Whether the tool execution resulted in an error.
    """

    tool_use_id: str
    content: str
    is_error: bool = False


@dataclass
class Message:
    """A message in a conversation.

    Attributes:
        role: The role of the message sender.
        content: The text content of the message (may be None for tool-only responses).
        tool_uses: Tool uses in this message (assistant role only).
        tool_results: Tool results in this message (user role only).
    """

    role: Role
    content: str | None = None
    tool_uses: list[ToolUse] = field(default_factory=list)
    tool_results: list[ToolResult] = field(default_factory=list)


@dataclass
class Response:
    """Response from a model completion.

    Attributes:
        content: The text content of the response (may be None if only tool use).
        tool_uses: Any tool uses the model wants to make.
        stop_reason: Why the model stopped generating.
        usage: Token usage information.
        model: The model that generated the response.
    """

    content: str | None
    tool_uses: list[ToolUse] = field(default_factory=list)
    stop_reason: str | None = None
    usage: dict[str, int] = field(default_factory=dict)
    model: str | None = None

    @property
    def has_tool_use(self) -> bool:
        """Check if the response contains tool uses."""
        return len(self.tool_uses) > 0


class ModelProvider(ABC):
    """Abstract base class for model providers.

    Defines the interface for interacting with language models.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the provider name."""
        ...

    @property
    @abstractmethod
    def default_model(self) -> str:
        """Return the default model identifier."""
        ...

    @abstractmethod
    async def complete(
        self,
        messages: list[Message],
        *,
        system: str | None = None,
        tools: list[ToolDefinition] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> Response:
        """Generate a completion for the given messages.

        Args:
            messages: The conversation history. Messages can contain tool_uses
                (for assistant messages) or tool_results (for user messages).
            system: System prompt to use.
            tools: Tools available for the model to call.
            model: Model to use (defaults to provider's default).
            max_tokens: Maximum tokens to generate.
            temperature: Sampling temperature (0-1).

        Returns:
            The model's response.

        Raises:
            ModelError: If the request fails.
        """
        ...


class ModelError(Exception):
    """Base exception for model provider errors."""

    pass


class RateLimitError(ModelError):
    """Raised when rate limited by the provider.

    Attributes:
        retry_after: Seconds to wait before retrying (if known).
    """

    def __init__(self, message: str, retry_after: float | None = None) -> None:
        """Initialize rate limit error.

        Args:
            message: Error message.
            retry_after: Seconds to wait before retrying.
        """
        super().__init__(message)
        self.retry_after = retry_after


class AuthenticationError(ModelError):
    """Raised when authentication fails."""

    pass
