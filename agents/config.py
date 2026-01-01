"""Agent configuration for Erebus.

Contains configuration settings for agent behavior (not authorization).
Authorization is handled at the boundary layer (Discord client).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AgentConfig:
    """Configuration for agent behavior.

    This is intentionally separate from bot/Discord configuration.
    Authorization is handled at the boundary layer, not here.

    Attributes:
        max_tool_iterations: Maximum tool call iterations per request.
        tool_call_timeout: Timeout for individual tool calls in seconds.
        log_tool_calls: Whether to log tool call details.
    """

    max_tool_iterations: int = 10
    tool_call_timeout: float = 30.0
    log_tool_calls: bool = True

    def __post_init__(self) -> None:
        """Validate configuration values."""
        if self.max_tool_iterations <= 0:
            raise ValueError("max_tool_iterations must be positive")
        if self.tool_call_timeout <= 0:
            raise ValueError("tool_call_timeout must be positive")


# Default configuration instance
DEFAULT_AGENT_CONFIG = AgentConfig()
