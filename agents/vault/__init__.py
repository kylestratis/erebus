"""Vault module for Obsidian integration.

Provides direct file operations for Obsidian vaults with template support.
"""

from agents.vault.tools import VaultToolExecutor, get_vault_tool_definitions
from agents.vault.vault import (
    NoteMetadata,
    NoteNotFoundError,
    PathTraversalError,
    SearchResult,
    Template,
    TemplateNotFoundError,
    Vault,
    VaultConfig,
    VaultError,
)

__all__ = [
    "NoteMetadata",
    "NoteNotFoundError",
    "PathTraversalError",
    "SearchResult",
    "Template",
    "TemplateNotFoundError",
    "Vault",
    "VaultConfig",
    "VaultError",
    "VaultToolExecutor",
    "get_vault_tool_definitions",
]
