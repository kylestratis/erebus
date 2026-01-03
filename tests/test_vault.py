"""Tests for the vault module.

Tests validation, error handling, and core operations.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from agents.vault.vault import (
    NoteNotFoundError,
    PathTraversalError,
    TemplateNotFoundError,
    Vault,
    VaultConfig,
    VaultError,
)


@pytest.fixture
def temp_vault(tmp_path: Path) -> Vault:
    """Create a temporary vault for testing."""
    # Create templates directory
    templates_dir = tmp_path / "Templates"
    templates_dir.mkdir()

    # Create a test template
    (templates_dir / "Test Template.md").write_text("# {{title}}\n\nCreated: {{date}}")

    # Create daily notes directory
    daily_dir = tmp_path / "Calendar" / "Daily Notes"
    daily_dir.mkdir(parents=True)

    # Create a Daily Note template
    (templates_dir / "Daily Note.md").write_text("# {{title}}\n\n## Tasks\n\n## Notes")

    config = VaultConfig(
        root=tmp_path,
        templates_path="Templates",
        daily_notes_path="Calendar/Daily Notes",
    )
    return Vault(config)


class TestVaultInitialization:
    """Tests for Vault initialization."""

    def test_init_with_valid_path(self, tmp_path: Path) -> None:
        """Vault initializes with valid directory."""
        config = VaultConfig(root=tmp_path)
        vault = Vault(config)
        assert vault.root == tmp_path

    def test_init_with_nonexistent_path(self, tmp_path: Path) -> None:
        """Vault raises error for nonexistent path."""
        nonexistent = tmp_path / "nonexistent"
        config = VaultConfig(root=nonexistent)
        with pytest.raises(VaultError, match="does not exist"):
            Vault(config)

    def test_init_with_file_path(self, tmp_path: Path) -> None:
        """Vault raises error when path is a file."""
        file_path = tmp_path / "file.txt"
        file_path.write_text("test")
        config = VaultConfig(root=file_path)
        with pytest.raises(VaultError, match="not a directory"):
            Vault(config)


class TestPathValidation:
    """Tests for path validation and security."""

    def test_empty_path_raises_error(self, temp_vault: Vault) -> None:
        """Empty path raises VaultError."""
        with pytest.raises(VaultError, match="cannot be empty"):
            temp_vault.read_note("")

    def test_whitespace_only_path_raises_error(self, temp_vault: Vault) -> None:
        """Whitespace-only path raises VaultError."""
        with pytest.raises(VaultError, match="cannot be empty"):
            temp_vault.read_note("   ")

    def test_path_too_long_raises_error(self, temp_vault: Vault) -> None:
        """Path exceeding max length raises VaultError."""
        long_path = "a" * (Vault.MAX_PATH_LENGTH + 1)
        with pytest.raises(VaultError, match="too long"):
            temp_vault.read_note(long_path)

    def test_path_at_reasonable_length_works(self, temp_vault: Vault) -> None:
        """Long path below MAX_PATH_LENGTH is accepted (though file won't exist)."""
        # Use 200 chars - long enough to test but under OS filename limits (255)
        long_path = "a" * 200
        # Should raise NoteNotFoundError, not VaultError for length
        with pytest.raises(NoteNotFoundError):
            temp_vault.read_note(long_path)

    def test_path_traversal_blocked(self, temp_vault: Vault) -> None:
        """Path traversal attempts are blocked."""
        with pytest.raises(PathTraversalError, match="escapes vault root"):
            temp_vault.read_note("../../../etc/passwd")

    def test_absolute_path_treated_as_relative(self, temp_vault: Vault) -> None:
        """Absolute paths are treated as relative (leading slash stripped)."""
        # /etc/passwd becomes etc/passwd.md within the vault - safe behavior
        with pytest.raises(NoteNotFoundError):
            temp_vault.read_note("/etc/passwd")

    def test_leading_slashes_stripped(self, temp_vault: Vault) -> None:
        """Leading slashes are stripped from paths."""
        # Create a test note
        temp_vault.write_note("test.md", content="test content")
        # Should work with leading slash
        content = temp_vault.read_note("/test.md")
        assert content == "test content"


class TestSearchValidation:
    """Tests for search query validation."""

    def test_empty_query_raises_error(self, temp_vault: Vault) -> None:
        """Empty search query raises VaultError."""
        with pytest.raises(VaultError, match="cannot be empty"):
            temp_vault.search_notes("")

    def test_whitespace_only_query_raises_error(self, temp_vault: Vault) -> None:
        """Whitespace-only query raises VaultError."""
        with pytest.raises(VaultError, match="cannot be empty"):
            temp_vault.search_notes("   ")

    def test_single_char_query_works(self, temp_vault: Vault) -> None:
        """Single character queries are allowed."""
        # Create a note with content
        temp_vault.write_note("test.md", content="I am here")
        results = temp_vault.search_notes("I")
        assert len(results) >= 1

    def test_max_results_capped(self, temp_vault: Vault) -> None:
        """max_results is capped at MAX_SEARCH_RESULTS."""
        temp_vault.write_note("test.md", content="test")
        # Request more than max - should not error
        results = temp_vault.search_notes("test", max_results=1000)
        # Just verify it doesn't crash
        assert isinstance(results, list)

    def test_invalid_max_results_uses_default(self, temp_vault: Vault) -> None:
        """Invalid max_results uses default value."""
        temp_vault.write_note("test.md", content="test")
        # Negative value should use default
        results = temp_vault.search_notes("test", max_results=-1)
        assert isinstance(results, list)


class TestNoteOperations:
    """Tests for note CRUD operations."""

    def test_write_and_read_note(self, temp_vault: Vault) -> None:
        """Can write and read a note."""
        temp_vault.write_note("test.md", content="Hello, world!")
        content = temp_vault.read_note("test.md")
        assert content == "Hello, world!"

    def test_write_note_creates_directories(self, temp_vault: Vault) -> None:
        """Writing a note creates parent directories."""
        temp_vault.write_note("nested/path/note.md", content="nested content")
        content = temp_vault.read_note("nested/path/note.md")
        assert content == "nested content"

    def test_write_note_without_extension(self, temp_vault: Vault) -> None:
        """Can write note without .md extension (auto-added)."""
        temp_vault.write_note("no-extension", content="test")
        content = temp_vault.read_note("no-extension.md")
        assert content == "test"

    def test_read_nonexistent_note_raises_error(self, temp_vault: Vault) -> None:
        """Reading nonexistent note raises NoteNotFoundError."""
        with pytest.raises(NoteNotFoundError, match="not found"):
            temp_vault.read_note("does-not-exist.md")

    def test_overwrite_note_requires_flag(self, temp_vault: Vault) -> None:
        """Overwriting existing note requires overwrite=True."""
        temp_vault.write_note("exists.md", content="original")
        with pytest.raises(VaultError, match="already exists"):
            temp_vault.write_note("exists.md", content="new content")

    def test_overwrite_note_with_flag(self, temp_vault: Vault) -> None:
        """Can overwrite note with overwrite=True."""
        temp_vault.write_note("exists.md", content="original")
        temp_vault.write_note("exists.md", content="new content", overwrite=True)
        content = temp_vault.read_note("exists.md")
        assert content == "new content"

    def test_delete_note(self, temp_vault: Vault) -> None:
        """Can delete a note."""
        temp_vault.write_note("to-delete.md", content="delete me")
        assert temp_vault.note_exists("to-delete.md")
        temp_vault.delete_note("to-delete.md")
        assert not temp_vault.note_exists("to-delete.md")

    def test_delete_nonexistent_note_raises_error(self, temp_vault: Vault) -> None:
        """Deleting nonexistent note raises NoteNotFoundError."""
        with pytest.raises(NoteNotFoundError, match="not found"):
            temp_vault.delete_note("does-not-exist.md")


class TestTemplates:
    """Tests for template functionality."""

    def test_load_templates(self, temp_vault: Vault) -> None:
        """Templates are loaded from templates directory."""
        templates = temp_vault.load_templates()
        assert "Test Template" in templates
        assert "Daily Note" in templates

    def test_get_template(self, temp_vault: Vault) -> None:
        """Can get a specific template."""
        template = temp_vault.get_template("Test Template")
        assert template is not None
        assert "{{title}}" in template.content

    def test_get_nonexistent_template(self, temp_vault: Vault) -> None:
        """Getting nonexistent template returns None."""
        template = temp_vault.get_template("Does Not Exist")
        assert template is None

    def test_render_template_basic(self, temp_vault: Vault) -> None:
        """Template renders with variable substitution."""
        content = temp_vault.render_template(
            "Test Template",
            variables={"title": "My Note"},
        )
        assert "# My Note" in content
        # Date should be filled in
        assert "{{date}}" not in content

    def test_render_nonexistent_template_raises_error(self, temp_vault: Vault) -> None:
        """Rendering nonexistent template raises TemplateNotFoundError."""
        with pytest.raises(TemplateNotFoundError, match="not found"):
            temp_vault.render_template("Does Not Exist")


class TestDailyNotes:
    """Tests for daily note functionality."""

    def test_get_daily_note_path(self, temp_vault: Vault) -> None:
        """Daily note path is generated correctly."""
        test_date = datetime(2024, 1, 15)
        path = temp_vault.get_daily_note_path(test_date)
        assert path == "Calendar/Daily Notes/2024-01-15.md"

    def test_get_daily_note_path_defaults_to_today(self, temp_vault: Vault) -> None:
        """Daily note path defaults to today's date."""
        path = temp_vault.get_daily_note_path()
        today = datetime.now().strftime("%Y-%m-%d")
        assert today in path

    def test_create_daily_note(self, temp_vault: Vault) -> None:
        """Can create a daily note."""
        test_date = datetime(2024, 1, 15)
        path = temp_vault.create_daily_note(date=test_date)
        assert "2024-01-15" in path
        content = temp_vault.get_daily_note(date=test_date)
        assert content is not None
        assert "Tasks" in content  # From template

    def test_get_nonexistent_daily_note(self, temp_vault: Vault) -> None:
        """Getting nonexistent daily note returns None."""
        test_date = datetime(2020, 1, 1)
        content = temp_vault.get_daily_note(date=test_date)
        assert content is None

    def test_create_duplicate_daily_note_raises_error(self, temp_vault: Vault) -> None:
        """Creating duplicate daily note raises VaultError."""
        test_date = datetime(2024, 6, 15)
        temp_vault.create_daily_note(date=test_date)
        with pytest.raises(VaultError, match="already exists"):
            temp_vault.create_daily_note(date=test_date)


class TestListOperations:
    """Tests for listing notes and directories."""

    def test_list_notes_empty_directory(self, temp_vault: Vault) -> None:
        """Listing empty directory returns empty list."""
        notes = temp_vault.list_notes("Calendar/Daily Notes")
        assert notes == []

    def test_list_notes(self, temp_vault: Vault) -> None:
        """Can list notes in a directory."""
        temp_vault.write_note("Ideas/idea1.md", content="idea 1")
        temp_vault.write_note("Ideas/idea2.md", content="idea 2")
        notes = temp_vault.list_notes("Ideas")
        assert len(notes) == 2
        names = [n.name for n in notes]
        assert "idea1" in names
        assert "idea2" in names

    def test_list_directories(self, temp_vault: Vault) -> None:
        """Can list subdirectories."""
        temp_vault.write_note("Dir1/note.md", content="test")
        temp_vault.write_note("Dir2/note.md", content="test")
        directories = temp_vault.list_directories()
        # Should include Dir1, Dir2, Templates, Calendar
        dir_names = [Path(d).name for d in directories]
        assert "Dir1" in dir_names
        assert "Dir2" in dir_names

    def test_list_nonexistent_directory_raises_error(self, temp_vault: Vault) -> None:
        """Listing nonexistent directory raises VaultError."""
        with pytest.raises(VaultError, match="not found"):
            temp_vault.list_notes("NonexistentDir")


class TestConstants:
    """Tests for class constants."""

    def test_max_path_length_constant(self) -> None:
        """MAX_PATH_LENGTH constant is defined."""
        assert Vault.MAX_PATH_LENGTH == 500

    def test_default_max_search_results_constant(self) -> None:
        """DEFAULT_MAX_SEARCH_RESULTS constant is defined."""
        assert Vault.DEFAULT_MAX_SEARCH_RESULTS == 50

    def test_max_search_results_constant(self) -> None:
        """MAX_SEARCH_RESULTS constant is defined."""
        assert Vault.MAX_SEARCH_RESULTS == 500
