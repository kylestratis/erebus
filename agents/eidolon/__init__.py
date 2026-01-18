"""EidolonMemory - Letta-powered persistent memory for Erebus.

This module provides stateful, persistent memory for the Erebus Discord bot
using Letta as the backend. Each user gets their own agent with:
- Core memory: Always-visible persona, user profile, and context
- Archival memory: Semantic search for learned patterns
- Recall memory: Full conversation history

Usage:
    from agents.eidolon import EidolonMemory, EidolonConfig

    config = EidolonConfig(
        base_url="http://localhost:8283",
        default_timezone="America/New_York",
    )
    eidolon = EidolonMemory(config)

    # Chat with user's agent
    response = await eidolon.chat(
        user_id=123456789,
        message="Hello!",
        user_name="Kyle",
    )
"""

from agents.eidolon.client import EidolonConfig, EidolonMemory, MCPServerConfig
from agents.eidolon.memory import (
    CONTEXT_BLOCK,
    CONTEXT_LABEL,
    HUMAN_BLOCK_TEMPLATE,
    HUMAN_LABEL,
    PERSONA_BLOCK,
    PERSONA_LABEL,
    create_human_block,
)
from agents.eidolon.system_tools import (
    SystemToolExecutor,
    get_system_tool_definitions,
)
from agents.eidolon.tools import (
    NativeToolExecutor,
    ToolRegistry,
    convert_to_letta_tool_format,
    convert_tools_to_letta_format,
    get_tool_names,
)

__all__ = [
    # Main classes
    "EidolonMemory",
    "EidolonConfig",
    "MCPServerConfig",
    # Memory blocks
    "PERSONA_BLOCK",
    "PERSONA_LABEL",
    "HUMAN_BLOCK_TEMPLATE",
    "HUMAN_LABEL",
    "CONTEXT_BLOCK",
    "CONTEXT_LABEL",
    "create_human_block",
    # Tool registration
    "ToolRegistry",
    "NativeToolExecutor",
    "convert_to_letta_tool_format",
    "convert_tools_to_letta_format",
    "get_tool_names",
    # System tools
    "SystemToolExecutor",
    "get_system_tool_definitions",
]
