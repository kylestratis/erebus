"""Erebus Discord bot.

A stateful, continuously-learning AI assistant accessible via Discord.
"""

from config import ErebusConfig

# Backward compatibility alias
Settings = ErebusConfig


def get_bot_class():
    """Lazy import of ErebusBot to avoid circular imports.

    The ErebusBot class depends on agents.eidolon which imports from
    bot.diagnostics, creating a circular import if we import ErebusBot
    at the top level.

    Returns:
        The ErebusBot class.
    """
    from bot.client import ErebusBot

    return ErebusBot


__all__ = ["get_bot_class", "ErebusConfig", "Settings"]
