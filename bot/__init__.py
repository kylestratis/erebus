"""Erebus Discord bot.

A stateful, continuously-learning AI assistant accessible via Discord.
"""

from bot.client import ErebusBot
from config import ErebusConfig

# Backward compatibility alias
Settings = ErebusConfig

__all__ = ["ErebusBot", "ErebusConfig", "Settings"]
