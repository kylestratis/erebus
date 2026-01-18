"""Agent configuration for Erebus - compatibility layer.

This module provides backward compatibility for code importing from agents.config.
The canonical configuration is now in the config/ module.

Migration:
    # Old (still works):
    from agents.config import AgentConfig, DEFAULT_AGENT_CONFIG

    # New (preferred):
    from config import AgentConfig, get_config
    config = get_config()
    agent_config = config.agent
"""

from __future__ import annotations

# Re-export from unified config module
from config import AgentConfig

# Default configuration instance
DEFAULT_AGENT_CONFIG = AgentConfig()

__all__ = ["AgentConfig", "DEFAULT_AGENT_CONFIG"]
