"""Vault operations for Obsidian integration.

Handles file reading, writing, and searching within an Obsidian vault.
All paths are validated to prevent directory traversal attacks.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bot.config import Settings

logger = logging.getLogger(__name__)


class VaultError(Exception):
    """Base exception for vault operations."""


class PathTraversalError(VaultError):
    """Raised when a path attempts to escape the vault root."""


class NoteNotFoundError(VaultError):
    """Raised when a requested note does not exist."""


class TemplateNotFoundError(VaultError):
    """Raised when a requested template does not exist."""


@dataclass
class VaultConfig:
    """Configuration for a vault.

    Attributes:
        root: Absolute path to the vault root.
        templates_path: Relative path to templates directory.
        daily_notes_path: Relative path to daily notes directory.
        daily_note_format: Date format for daily note filenames.
    """

    root: Path
    templates_path: str = "Templates"
    daily_notes_path: str = "Calendar/Daily Notes"
    daily_note_format: str = "%Y-%m-%d"

    @classmethod
    def from_settings(cls, settings: Settings) -> VaultConfig:
        """Create config from application settings.

        Args:
            settings: Application settings instance.

        Returns:
            Configured VaultConfig instance.

        Raises:
            VaultError: If obsidian_vault_path is not configured.
        """
        if settings.obsidian_vault_path is None:
            raise VaultError("Obsidian vault path not configured in settings")

        return cls(
            root=settings.obsidian_vault_path.resolve(),
            templates_path=settings.obsidian_templates_path,
            daily_notes_path=settings.obsidian_daily_notes_path,
            daily_note_format=settings.obsidian_daily_note_format,
        )


@dataclass
class NoteMetadata:
    """Metadata for a note.

    Attributes:
        path: Relative path from vault root.
        name: Note name without extension.
        modified: Last modification time.
        size: File size in bytes.
    """

    path: str
    name: str
    modified: datetime
    size: int


@dataclass
class SearchResult:
    """A search result.

    Attributes:
        path: Relative path from vault root.
        line_number: Line number of the match.
        line: The matching line content.
        match: The matched text.
    """

    path: str
    line_number: int
    line: str
    match: str


@dataclass
class Template:
    """A note template.

    Attributes:
        name: Template name (filename without extension).
        path: Relative path to template file.
        content: Template content.
    """

    name: str
    path: str
    content: str


class Vault:
    """Represents an Obsidian vault.

    Provides safe file operations within the vault boundaries,
    with template support for note creation.

    Attributes:
        config: Vault configuration.
        templates: Cached templates by name.
    """

    # Validation constants
    MAX_PATH_LENGTH = 500
    DEFAULT_MAX_SEARCH_RESULTS = 50
    MAX_SEARCH_RESULTS = 500

    def __init__(self, config: VaultConfig) -> None:
        """Initialize the vault.

        Args:
            config: Vault configuration.

        Raises:
            VaultError: If the root path does not exist or is not a directory.
        """
        self.config = config
        self._templates: dict[str, Template] = {}

        if not config.root.exists():
            raise VaultError(f"Vault root does not exist: {config.root}")
        if not config.root.is_dir():
            raise VaultError(f"Vault root is not a directory: {config.root}")

        logger.info(f"Initialized vault at: {config.root}")

    @property
    def root(self) -> Path:
        """Get the vault root path."""
        return self.config.root

    def _resolve_path(self, relative_path: str) -> Path:
        """Resolve a relative path within the vault.

        Args:
            relative_path: Path relative to vault root.

        Returns:
            Absolute path within the vault.

        Raises:
            VaultError: If the path is invalid.
            PathTraversalError: If the path escapes the vault root.
        """
        # Strip and validate path
        relative_path = relative_path.strip()
        if not relative_path:
            raise VaultError("Path cannot be empty")

        # Check for excessively long paths
        if len(relative_path) > self.MAX_PATH_LENGTH:
            raise VaultError(f"Path is too long (max {self.MAX_PATH_LENGTH} characters)")

        # Remove leading slashes
        clean_path = relative_path.lstrip("/")
        full_path = (self.root / clean_path).resolve()

        try:
            full_path.relative_to(self.root)
        except ValueError as e:
            raise PathTraversalError(f"Path '{relative_path}' escapes vault root") from e

        return full_path

    def _ensure_md_extension(self, path: str) -> str:
        """Ensure a path has a .md extension.

        Args:
            path: The file path.

        Returns:
            Path with .md extension.

        Raises:
            VaultError: If path is empty or whitespace-only.
        """
        # Validate before adding extension
        path = path.strip()
        if not path:
            raise VaultError("Path cannot be empty")
        if not path.endswith(".md"):
            return f"{path}.md"
        return path

    # -------------------------------------------------------------------------
    # Template Operations
    # -------------------------------------------------------------------------

    def load_templates(self) -> dict[str, Template]:
        """Load all templates from the templates directory.

        Returns:
            Dictionary of templates by name.
        """
        templates_dir = self._resolve_path(self.config.templates_path)
        if not templates_dir.exists():
            logger.warning(f"Templates directory not found: {templates_dir}")
            return {}

        self._templates.clear()
        for file_path in templates_dir.glob("*.md"):
            try:
                content = file_path.read_text(encoding="utf-8")
                template = Template(
                    name=file_path.stem,
                    path=str(file_path.relative_to(self.root)),
                    content=content,
                )
                self._templates[template.name] = template
                logger.debug(f"Loaded template: {template.name}")
            except Exception as e:
                logger.warning(f"Failed to load template {file_path}: {e}")

        logger.info(f"Loaded {len(self._templates)} templates")
        return self._templates

    def get_template(self, name: str) -> Template | None:
        """Get a template by name.

        Args:
            name: Template name (without .md extension).

        Returns:
            The template if found, None otherwise.
        """
        if not self._templates:
            self.load_templates()
        return self._templates.get(name)

    def list_templates(self) -> list[str]:
        """List available template names.

        Returns:
            List of template names.
        """
        if not self._templates:
            self.load_templates()
        return list(self._templates.keys())

    def render_template(
        self,
        template_name: str,
        variables: dict[str, str] | None = None,
    ) -> str:
        """Render a template with variable substitution.

        Supports Obsidian template variables:
        - {{date}} - Current date (YYYY-MM-DD)
        - {{date:FORMAT}} - Date with custom format
        - {{time}} - Current time (HH:MM)
        - {{time:FORMAT}} - Time with custom format
        - {{title}} - Note title (from variables)
        - Custom variables from the variables dict

        Args:
            template_name: Name of the template to render.
            variables: Optional dictionary of variable substitutions.

        Returns:
            Rendered template content.

        Raises:
            TemplateNotFoundError: If template doesn't exist.
        """
        template = self.get_template(template_name)
        if not template:
            raise TemplateNotFoundError(f"Template not found: {template_name}")

        content = template.content
        now = datetime.now()
        variables = variables or {}

        # Replace date variables
        content = re.sub(
            r"\{\{date(?::([^}]+))?\}\}",
            lambda m: now.strftime(m.group(1) or "%Y-%m-%d"),
            content,
        )

        # Replace time variables
        content = re.sub(
            r"\{\{time(?::([^}]+))?\}\}",
            lambda m: now.strftime(m.group(1) or "%H:%M"),
            content,
        )

        # Replace custom variables
        for key, value in variables.items():
            content = content.replace(f"{{{{{key}}}}}", value)

        return content

    def find_template_for_path(self, path: str) -> str | None:
        """Find a matching template for a given path.

        Looks for templates that match the directory structure.
        For example, "Ideas/new-idea.md" would look for:
        - "Idea Seed" template
        - "Ideas" template
        - "idea" template

        Args:
            path: The note path.

        Returns:
            Template name if found, None otherwise.
        """
        if not self._templates:
            self.load_templates()

        # Extract directory name from path
        parts = Path(path).parts
        if not parts:
            return None

        directory = parts[0] if len(parts) > 1 else ""

        # Common template name patterns to try
        candidates = [
            directory,  # e.g., "Ideas"
            directory.rstrip("s"),  # e.g., "Idea" from "Ideas"
            f"{directory.rstrip('s')} Seed",  # e.g., "Idea Seed"
            directory.lower(),
            directory.rstrip("s").lower(),
        ]

        for candidate in candidates:
            if candidate in self._templates:
                return candidate

        return None

    # -------------------------------------------------------------------------
    # Note Operations
    # -------------------------------------------------------------------------

    def read_note(self, path: str) -> str:
        """Read a note's content.

        Args:
            path: Relative path to the note.

        Returns:
            The note's content as a string.

        Raises:
            NoteNotFoundError: If the note does not exist.
            PathTraversalError: If the path escapes the vault.
        """
        full_path = self._resolve_path(self._ensure_md_extension(path))
        if not full_path.exists():
            raise NoteNotFoundError(f"Note not found: {path}")
        return full_path.read_text(encoding="utf-8")

    def write_note(
        self,
        path: str,
        content: str | None = None,
        template: str | None = None,
        template_variables: dict[str, str] | None = None,
        overwrite: bool = False,
    ) -> str:
        """Write content to a note.

        If no content is provided but a template is specified, renders the template.
        If neither is provided, looks for a matching template based on the path.

        Args:
            path: Relative path to the note.
            content: Content to write. If None, uses template.
            template: Template name to use if content is None.
            template_variables: Variables for template rendering.
            overwrite: If True, overwrite existing notes.

        Returns:
            The path of the written note.

        Raises:
            VaultError: If the note exists and overwrite is False.
            PathTraversalError: If the path escapes the vault.
            TemplateNotFoundError: If specified template doesn't exist.
        """
        full_path = self._resolve_path(self._ensure_md_extension(path))

        if full_path.exists() and not overwrite:
            raise VaultError(f"Note already exists: {path}. Set overwrite=True to replace.")

        # Determine content
        if content is None:
            # Try specified template first
            if template:
                content = self.render_template(template, template_variables)
            else:
                # Try to find matching template
                auto_template = self.find_template_for_path(path)
                if auto_template:
                    logger.debug(f"Using auto-detected template: {auto_template}")
                    content = self.render_template(auto_template, template_variables)
                else:
                    # Minimal default
                    note_name = Path(path).stem
                    content = f"# {note_name}\n\n"

        # Create parent directories if needed
        full_path.parent.mkdir(parents=True, exist_ok=True)

        full_path.write_text(content, encoding="utf-8")
        relative_path = str(full_path.relative_to(self.root))
        logger.info(f"Wrote note: {relative_path}")
        return relative_path

    def delete_note(self, path: str) -> bool:
        """Delete a note.

        Args:
            path: Relative path to the note.

        Returns:
            True if the note was deleted.

        Raises:
            NoteNotFoundError: If the note does not exist.
            PathTraversalError: If the path escapes the vault.
        """
        full_path = self._resolve_path(self._ensure_md_extension(path))
        if not full_path.exists():
            raise NoteNotFoundError(f"Note not found: {path}")
        full_path.unlink()
        logger.info(f"Deleted note: {path}")
        return True

    def note_exists(self, path: str) -> bool:
        """Check if a note exists.

        Args:
            path: Relative path to the note.

        Returns:
            True if the note exists.
        """
        try:
            full_path = self._resolve_path(self._ensure_md_extension(path))
            return full_path.exists()
        except PathTraversalError:
            return False

    def list_directories(self, directory: str = "") -> list[str]:
        """List subdirectories in a directory.

        Args:
            directory: Relative path to the directory. Empty for vault root.

        Returns:
            List of subdirectory paths relative to vault root.

        Raises:
            VaultError: If the directory does not exist.
            PathTraversalError: If the path escapes the vault.
        """
        full_path = self._resolve_path(directory) if directory else self.root

        if not full_path.exists():
            raise VaultError(f"Directory not found: {directory}")
        if not full_path.is_dir():
            raise VaultError(f"Path is not a directory: {directory}")

        directories = []
        for item in sorted(full_path.iterdir()):
            if item.is_dir() and not item.name.startswith("."):
                directories.append(str(item.relative_to(self.root)))
        return directories

    def list_notes(self, directory: str = "") -> list[NoteMetadata]:
        """List notes in a directory.

        Args:
            directory: Relative path to the directory. Empty for vault root.

        Returns:
            List of note metadata, sorted by modification time (newest first).

        Raises:
            VaultError: If the directory does not exist.
            PathTraversalError: If the path escapes the vault.
        """
        full_path = self._resolve_path(directory) if directory else self.root

        if not full_path.exists():
            raise VaultError(f"Directory not found: {directory}")
        if not full_path.is_dir():
            raise VaultError(f"Path is not a directory: {directory}")

        notes = []
        for file_path in full_path.glob("*.md"):
            stat = file_path.stat()
            notes.append(
                NoteMetadata(
                    path=str(file_path.relative_to(self.root)),
                    name=file_path.stem,
                    modified=datetime.fromtimestamp(stat.st_mtime),
                    size=stat.st_size,
                )
            )
        return sorted(notes, key=lambda n: n.modified, reverse=True)

    def search_notes(
        self,
        query: str,
        directory: str = "",
        max_results: int = 50,
    ) -> list[SearchResult]:
        """Search for text in notes.

        Args:
            query: Text to search for (case-insensitive).
            directory: Limit search to this directory. Empty for entire vault.
            max_results: Maximum number of results to return.

        Returns:
            List of search results.

        Raises:
            VaultError: If the directory does not exist or query is empty.
            PathTraversalError: If the directory path escapes the vault.
        """
        # Validate query
        query = query.strip()
        if not query:
            raise VaultError("Search query cannot be empty")

        # Validate max_results
        if max_results < 1:
            max_results = self.DEFAULT_MAX_SEARCH_RESULTS
        elif max_results > self.MAX_SEARCH_RESULTS:
            max_results = self.MAX_SEARCH_RESULTS

        search_root = self._resolve_path(directory) if directory else self.root

        if directory and not search_root.exists():
            raise VaultError(f"Directory not found: {directory}")
        if directory and not search_root.is_dir():
            raise VaultError(f"Path is not a directory: {directory}")

        pattern = re.compile(re.escape(query), re.IGNORECASE)
        results = []

        for file_path in search_root.rglob("*.md"):
            if len(results) >= max_results:
                break

            try:
                content = file_path.read_text(encoding="utf-8")
            except Exception:
                continue

            for line_num, line in enumerate(content.splitlines(), 1):
                match = pattern.search(line)
                if match:
                    results.append(
                        SearchResult(
                            path=str(file_path.relative_to(self.root)),
                            line_number=line_num,
                            line=line.strip(),
                            match=match.group(),
                        )
                    )
                    if len(results) >= max_results:
                        break

        return results

    # -------------------------------------------------------------------------
    # Daily Notes
    # -------------------------------------------------------------------------

    def get_daily_note_path(self, date: datetime | None = None) -> str:
        """Get the path for a daily note.

        Args:
            date: The date for the note. Defaults to today.

        Returns:
            Relative path to the daily note.
        """
        if date is None:
            date = datetime.now()
        filename = date.strftime(self.config.daily_note_format)
        return f"{self.config.daily_notes_path}/{filename}.md"

    def get_daily_note(self, date: datetime | None = None) -> str | None:
        """Get a daily note's content.

        Args:
            date: The date for the note. Defaults to today.

        Returns:
            The note content if it exists, None otherwise.
        """
        path = self.get_daily_note_path(date)
        if self.note_exists(path):
            return self.read_note(path)
        return None

    def create_daily_note(
        self,
        date: datetime | None = None,
        content: str | None = None,
        extra_variables: dict[str, str] | None = None,
    ) -> str:
        """Create a daily note.

        Uses the "Daily Note" template if available, otherwise creates a basic note.

        Args:
            date: The date for the note. Defaults to today.
            content: Optional content override (skips template).
            extra_variables: Additional template variables.

        Returns:
            Path to the created note.

        Raises:
            VaultError: If the note already exists.
        """
        if date is None:
            date = datetime.now()

        path = self.get_daily_note_path(date)

        # Prepare template variables
        variables = {
            "title": date.strftime("%A, %B %d, %Y"),
            "date": date.strftime("%Y-%m-%d"),
        }
        if extra_variables:
            variables.update(extra_variables)

        return self.write_note(
            path=path,
            content=content,
            template="Daily Note",
            template_variables=variables,
            overwrite=False,
        )
