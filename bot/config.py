"""Bot configuration - compatibility layer.

This module provides backward compatibility for code importing from bot.config.
The canonical configuration is now in the config/ module.

Migration:
    # Old (still works):
    from bot.config import Settings, get_settings

    # New (preferred):
    from config import ErebusConfig, get_config
"""

from __future__ import annotations

# Re-export everything from the unified config module
from config import (
    AgentConfig,
    DiscordConfig,
    Environment,
    ErebusConfig,
    JobConfig,
    LettaConfig,
    MCPServerConfig,
    SchedulerConfig,
    SchedulerJobsConfig,
    VaultConfig,
    clear_config_cache,
    get_config,
)

# Backward compatibility aliases
Settings = ErebusConfig
get_settings = get_config  # Direct alias, no deprecation warning to avoid noise


__all__ = [
    # Backward compatibility
    "Settings",
    "get_settings",
    # Re-exports from config module
    "ErebusConfig",
    "Environment",
    "MCPServerConfig",
    "DiscordConfig",
    "LettaConfig",
    "VaultConfig",
    "AgentConfig",
    "SchedulerConfig",
    "SchedulerJobsConfig",
    "JobConfig",
    "get_config",
    "clear_config_cache",
]
