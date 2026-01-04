"""Tests for core cog workflow prompts and utilities."""

from __future__ import annotations

import pytest

from bot.cogs.core import (
    CAPTURE_WORKFLOW_PROMPT,
    DAILY_WORKFLOW_PROMPT,
    IDEA_WORKFLOW_PROMPT,
)


class TestWorkflowPrompts:
    """Tests for workflow prompt templates."""

    def test_daily_prompt_contains_required_instructions(self) -> None:
        """Daily prompt should contain key workflow steps."""
        assert "vault_get_daily_note" in DAILY_WORKFLOW_PROMPT
        assert "vault_create_daily_note" in DAILY_WORKFLOW_PROMPT
        assert "todoist_find-tasks" in DAILY_WORKFLOW_PROMPT
        assert "## Tasks" in DAILY_WORKFLOW_PROMPT
        assert "YYYY-MM-DD" in DAILY_WORKFLOW_PROMPT

    def test_daily_prompt_mentions_preservation(self) -> None:
        """Daily prompt should emphasize preserving existing content."""
        assert "Preserve" in DAILY_WORKFLOW_PROMPT or "preserve" in DAILY_WORKFLOW_PROMPT
        assert "FULL" in DAILY_WORKFLOW_PROMPT or "full" in DAILY_WORKFLOW_PROMPT

    def test_idea_prompt_contains_title_placeholder(self) -> None:
        """Idea prompt should have a placeholder for the title."""
        assert "{title}" in IDEA_WORKFLOW_PROMPT

    def test_idea_prompt_format_with_title(self) -> None:
        """Idea prompt should format correctly with a title."""
        formatted = IDEA_WORKFLOW_PROMPT.format(title="Test Idea")
        assert "Test Idea" in formatted
        # The title placeholder is replaced, but template example placeholders remain
        assert 'title: "Test Idea"' in formatted
        assert "Bins/Ideas/Test Idea.md" in formatted

    def test_idea_prompt_contains_required_sections(self) -> None:
        """Idea prompt should reference all idea template sections."""
        assert "## The Idea" in IDEA_WORKFLOW_PROMPT
        assert "## Why It's Interesting" in IDEA_WORKFLOW_PROMPT
        assert "## Next Steps" in IDEA_WORKFLOW_PROMPT
        assert "## Related" in IDEA_WORKFLOW_PROMPT

    def test_idea_prompt_contains_frontmatter_fields(self) -> None:
        """Idea prompt should include required frontmatter fields."""
        assert "confidence" in IDEA_WORKFLOW_PROMPT
        assert "could-become" in IDEA_WORKFLOW_PROMPT
        assert "status: seed" in IDEA_WORKFLOW_PROMPT

    def test_idea_prompt_mentions_vault_write(self) -> None:
        """Idea prompt should instruct to use vault_write_note."""
        assert "vault_write_note" in IDEA_WORKFLOW_PROMPT
        assert "Bins/Ideas" in IDEA_WORKFLOW_PROMPT

    def test_capture_prompt_contains_task_placeholder(self) -> None:
        """Capture prompt should have a placeholder for the task."""
        assert "{task_description}" in CAPTURE_WORKFLOW_PROMPT

    def test_capture_prompt_format_with_task(self) -> None:
        """Capture prompt should format correctly with a task."""
        formatted = CAPTURE_WORKFLOW_PROMPT.format(
            task_description="Buy groceries P1 tomorrow"
        )
        assert "Buy groceries P1 tomorrow" in formatted
        assert "{task_description}" not in formatted

    def test_capture_prompt_mentions_todoist(self) -> None:
        """Capture prompt should reference Todoist tools."""
        assert "todoist_add-tasks" in CAPTURE_WORKFLOW_PROMPT
        assert "Todoist" in CAPTURE_WORKFLOW_PROMPT

    def test_capture_prompt_mentions_priority_parsing(self) -> None:
        """Capture prompt should mention priority parsing."""
        assert "P1" in CAPTURE_WORKFLOW_PROMPT
        assert "P2" in CAPTURE_WORKFLOW_PROMPT
        assert "priority" in CAPTURE_WORKFLOW_PROMPT.lower()

    def test_capture_prompt_mentions_daily_note_integration(self) -> None:
        """Capture prompt should mention daily note integration."""
        assert "daily note" in CAPTURE_WORKFLOW_PROMPT.lower()
        assert "@todoist-" in CAPTURE_WORKFLOW_PROMPT


class TestPromptSecurity:
    """Tests for prompt injection safety."""

    def test_idea_title_escaping(self) -> None:
        """Title with special characters should be safely inserted."""
        # This tests that the format string doesn't break with special chars
        malicious_title = "Test {title} {{injection}}"
        # Should not raise an exception
        formatted = IDEA_WORKFLOW_PROMPT.format(title=malicious_title)
        assert malicious_title in formatted

    def test_capture_task_escaping(self) -> None:
        """Task with special characters should be safely inserted."""
        malicious_task = "Test {task_description} {{injection}}"
        formatted = CAPTURE_WORKFLOW_PROMPT.format(task_description=malicious_task)
        assert malicious_task in formatted
