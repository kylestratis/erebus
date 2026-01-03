"""Tool definitions for Obsidian vault integration.

Defines the tools that the AI model can use to interact with the vault,
and provides an executor to handle tool calls.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Coroutine
from typing import TYPE_CHECKING, Any

from agents.models.base import ToolDefinition

if TYPE_CHECKING:
    from agents.vault.vault import Vault

logger = logging.getLogger(__name__)


def get_vault_tool_definitions() -> list[ToolDefinition]:
    """Get all vault tool definitions for the model.

    Returns:
        List of tool definitions for vault operations.
    """
    return [
        ToolDefinition(
            name="vault_read_note",
            description=(
                "Read the contents of a note from the Obsidian vault. "
                "Use this to retrieve existing notes, daily notes, or any markdown file."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": (
                            "Relative path to the note within the vault "
                            "(e.g., 'Ideas/my-idea.md' or 'Daily Notes/2024-01-15.md'). "
                            "The .md extension is optional."
                        ),
                    },
                },
                "required": ["path"],
            },
        ),
        ToolDefinition(
            name="vault_write_note",
            description=(
                "Create or update a note in the Obsidian vault. "
                "If a matching template exists for the path, it will be used automatically. "
                "Use this for creating new notes, idea seeds, or updating existing content."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": (
                            "Relative path for the note within the vault "
                            "(e.g., 'Ideas/new-idea.md'). Parent directories are created automatically."
                        ),
                    },
                    "content": {
                        "type": "string",
                        "description": (
                            "The markdown content to write. If omitted, a matching template "
                            "will be used based on the path (e.g., 'Ideas/' uses 'Idea Seed' template)."
                        ),
                    },
                    "template": {
                        "type": "string",
                        "description": (
                            "Optional template name to use (e.g., 'Idea Seed', 'Daily Note'). "
                            "Overrides automatic template detection."
                        ),
                    },
                    "overwrite": {
                        "type": "boolean",
                        "description": "If true, overwrite existing note. Default is false.",
                    },
                },
                "required": ["path"],
            },
        ),
        ToolDefinition(
            name="vault_delete_note",
            description=(
                "Delete a note from the Obsidian vault. "
                "IMPORTANT: This is a destructive operation. Before deleting, "
                "always confirm with the user by stating the note path and asking for confirmation. "
                "Only proceed after receiving explicit approval."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": (
                            "Relative path to the note to delete "
                            "(e.g., 'Ideas/old-idea.md'). The .md extension is optional."
                        ),
                    },
                },
                "required": ["path"],
            },
        ),
        ToolDefinition(
            name="vault_search_notes",
            description=(
                "Search for text across notes in the vault. "
                "Returns matching lines with file paths and line numbers. "
                "Use this to find notes containing specific topics or keywords."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Text to search for (case-insensitive).",
                    },
                    "directory": {
                        "type": "string",
                        "description": (
                            "Optional directory to limit search to "
                            "(e.g., 'Ideas' or 'Daily Notes'). Searches entire vault if omitted."
                        ),
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of results to return. Default is 20.",
                    },
                },
                "required": ["query"],
            },
        ),
        ToolDefinition(
            name="vault_list_notes",
            description=(
                "List notes (markdown files) in a directory of the vault. "
                "Returns note names, paths, and last modified dates. "
                "Only lists files in the immediate directory, not subdirectories."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "directory": {
                        "type": "string",
                        "description": (
                            "Full path to directory (e.g., 'Bins/Evergreen Notes'). "
                            "Use vault_list_directories first to explore the vault structure. "
                            "Lists vault root if omitted."
                        ),
                    },
                },
                "required": [],
            },
        ),
        ToolDefinition(
            name="vault_list_directories",
            description=(
                "List subdirectories in a vault directory. "
                "Use this to explore the vault structure and find the correct paths "
                "before searching or listing notes. Returns full paths from vault root."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "directory": {
                        "type": "string",
                        "description": (
                            "Directory to list subdirectories of (e.g., 'Bins' or 'Spaces'). "
                            "Lists vault root directories if omitted."
                        ),
                    },
                },
                "required": [],
            },
        ),
        ToolDefinition(
            name="vault_get_daily_note",
            description=(
                "Get today's daily note or check if it exists. "
                "Returns the content if the note exists, or indicates it doesn't exist yet."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "date": {
                        "type": "string",
                        "description": ("Optional date in YYYY-MM-DD format. Defaults to today."),
                    },
                },
                "required": [],
            },
        ),
        ToolDefinition(
            name="vault_create_daily_note",
            description=(
                "Create a daily note for today (or specified date). "
                "Uses the 'Daily Note' template if available. "
                "Returns an error if the note already exists."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "date": {
                        "type": "string",
                        "description": ("Optional date in YYYY-MM-DD format. Defaults to today."),
                    },
                    "extra_content": {
                        "type": "string",
                        "description": "Optional additional content to append to the template.",
                    },
                },
                "required": [],
            },
        ),
        ToolDefinition(
            name="vault_list_templates",
            description=(
                "List all available templates in the vault. "
                "Use this to see what templates are available for creating notes."
            ),
            input_schema={
                "type": "object",
                "properties": {},
                "required": [],
            },
        ),
    ]


class VaultToolExecutor:
    """Executes vault tool calls.

    Bridges tool definitions to actual Vault operations.

    Attributes:
        vault: The vault instance to operate on.
    """

    def __init__(self, vault: Vault) -> None:
        """Initialize the executor.

        Args:
            vault: The vault instance to use for operations.
        """
        self.vault = vault
        self._handlers: dict[str, Callable[..., Coroutine[Any, Any, str]]] = {
            "vault_read_note": self._handle_read_note,
            "vault_write_note": self._handle_write_note,
            "vault_delete_note": self._handle_delete_note,
            "vault_search_notes": self._handle_search_notes,
            "vault_list_notes": self._handle_list_notes,
            "vault_list_directories": self._handle_list_directories,
            "vault_get_daily_note": self._handle_get_daily_note,
            "vault_create_daily_note": self._handle_create_daily_note,
            "vault_list_templates": self._handle_list_templates,
        }

    def can_handle(self, tool_name: str) -> bool:
        """Check if this executor handles a tool.

        Args:
            tool_name: Name of the tool.

        Returns:
            True if this executor handles the tool.
        """
        return tool_name in self._handlers

    async def execute(self, tool_name: str, arguments: dict[str, Any]) -> str:
        """Execute a vault tool.

        Args:
            tool_name: Name of the tool to execute.
            arguments: Tool arguments.

        Returns:
            Tool execution result as a string.

        Raises:
            ValueError: If tool is not handled by this executor.
        """
        handler = self._handlers.get(tool_name)
        if handler is None:
            raise ValueError(f"Unknown vault tool: {tool_name}")

        return await handler(**arguments)

    async def _handle_read_note(self, path: str) -> str:
        """Handle vault_read_note tool call."""
        try:
            content = self.vault.read_note(path)
            return content
        except Exception as e:
            return f"Error reading note: {e}"

    async def _handle_write_note(
        self,
        path: str,
        content: str | None = None,
        template: str | None = None,
        overwrite: bool = False,
    ) -> str:
        """Handle vault_write_note tool call."""
        try:
            written_path = self.vault.write_note(
                path=path,
                content=content,
                template=template,
                overwrite=overwrite,
            )
            return f"Successfully wrote note: {written_path}"
        except Exception as e:
            return f"Error writing note: {e}"

    async def _handle_delete_note(self, path: str) -> str:
        """Handle vault_delete_note tool call."""
        try:
            self.vault.delete_note(path)
            return f"Successfully deleted note: {path}"
        except Exception as e:
            return f"Error deleting note: {e}"

    async def _handle_search_notes(
        self,
        query: str,
        directory: str = "",
        max_results: int = 20,
    ) -> str:
        """Handle vault_search_notes tool call."""
        try:
            results = self.vault.search_notes(
                query=query,
                directory=directory,
                max_results=max_results,
            )
            if not results:
                return f"No notes found matching '{query}'"

            lines = [f"Found {len(results)} match(es) for '{query}':\n"]
            for r in results:
                lines.append(f"- {r.path}:{r.line_number}: {r.line[:100]}")
            return "\n".join(lines)
        except Exception as e:
            return f"Error searching notes: {e}"

    async def _handle_list_notes(self, directory: str = "") -> str:
        """Handle vault_list_notes tool call."""
        try:
            notes = self.vault.list_notes(directory=directory)
            if not notes:
                loc = f"'{directory}'" if directory else "vault root"
                return f"No notes found in {loc}"

            lines = [f"Notes in '{directory or 'vault root'}' ({len(notes)} total):\n"]
            for note in notes[:30]:  # Limit to 30 results
                modified = note.modified.strftime("%Y-%m-%d %H:%M")
                lines.append(f"- {note.name} ({modified})")
            if len(notes) > 30:
                lines.append(f"... and {len(notes) - 30} more")
            return "\n".join(lines)
        except Exception as e:
            return f"Error listing notes: {e}"

    async def _handle_list_directories(self, directory: str = "") -> str:
        """Handle vault_list_directories tool call."""
        try:
            directories = self.vault.list_directories(directory=directory)
            if not directories:
                loc = f"'{directory}'" if directory else "vault root"
                return f"No subdirectories in {loc}"

            loc = f"'{directory}'" if directory else "vault root"
            lines = [f"Subdirectories in {loc} ({len(directories)} total):\n"]
            for path in directories:
                lines.append(f"- {path}")
            return "\n".join(lines)
        except Exception as e:
            return f"Error listing directories: {e}"

    async def _handle_get_daily_note(self, date: str | None = None) -> str:
        """Handle vault_get_daily_note tool call."""
        try:
            from datetime import datetime

            target_date = None
            if date:
                target_date = datetime.strptime(date, "%Y-%m-%d")

            content = self.vault.get_daily_note(date=target_date)
            if content is None:
                path = self.vault.get_daily_note_path(date=target_date)
                return f"Daily note does not exist yet: {path}"
            return content
        except Exception as e:
            return f"Error getting daily note: {e}"

    async def _handle_create_daily_note(
        self,
        date: str | None = None,
        extra_content: str | None = None,
    ) -> str:
        """Handle vault_create_daily_note tool call."""
        try:
            from datetime import datetime

            target_date = None
            if date:
                target_date = datetime.strptime(date, "%Y-%m-%d")

            path = self.vault.create_daily_note(
                date=target_date,
                content=extra_content,  # If provided, overrides template
            )
            return f"Successfully created daily note: {path}"
        except Exception as e:
            return f"Error creating daily note: {e}"

    async def _handle_list_templates(self) -> str:
        """Handle vault_list_templates tool call."""
        try:
            templates = self.vault.list_templates()
            if not templates:
                return "No templates found in vault"

            lines = [f"Available templates ({len(templates)}):\n"]
            for name in sorted(templates):
                lines.append(f"- {name}")
            return "\n".join(lines)
        except Exception as e:
            return f"Error listing templates: {e}"
