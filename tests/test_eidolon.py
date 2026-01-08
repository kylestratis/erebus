"""Tests for the eidolon module.

Tests memory block definitions and EidolonMemory client (with mocked Letta).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from agents.eidolon import (
    CONTEXT_BLOCK,
    CONTEXT_LABEL,
    HUMAN_LABEL,
    PERSONA_BLOCK,
    PERSONA_LABEL,
    EidolonConfig,
    EidolonMemory,
    create_human_block,
)


class TestMemoryBlocks:
    """Tests for memory block definitions."""

    def test_persona_block_contains_identity(self) -> None:
        """Persona block contains Erebus identity."""
        assert "Erebus" in PERSONA_BLOCK
        assert "Discord" in PERSONA_BLOCK
        assert "primordial darkness" in PERSONA_BLOCK

    def test_persona_block_contains_personality(self) -> None:
        """Persona block defines personality traits."""
        assert "concise" in PERSONA_BLOCK
        assert "dry-witted" in PERSONA_BLOCK
        assert "mysterious" in PERSONA_BLOCK

    def test_persona_block_contains_safety_guidelines(self) -> None:
        """Persona block includes safety guidelines."""
        assert "confirm" in PERSONA_BLOCK
        assert "completing/deleting" in PERSONA_BLOCK or "completing" in PERSONA_BLOCK

    def test_persona_block_contains_capabilities(self) -> None:
        """Persona block lists capabilities."""
        assert "Todoist" in PERSONA_BLOCK
        assert "Obsidian" in PERSONA_BLOCK or "vault" in PERSONA_BLOCK

    def test_context_block_has_structure(self) -> None:
        """Context block has expected structure."""
        assert "Last interaction" in CONTEXT_BLOCK
        assert "Active projects" in CONTEXT_BLOCK
        assert "Pending items" in CONTEXT_BLOCK

    def test_create_human_block_fills_template(self) -> None:
        """create_human_block fills in template values."""
        block = create_human_block(
            name="TestUser",
            timezone="America/Chicago",
            discord_id=123456789,
        )
        assert "TestUser" in block
        assert "America/Chicago" in block
        assert "123456789" in block

    def test_memory_labels_are_strings(self) -> None:
        """Memory labels are valid strings."""
        assert isinstance(PERSONA_LABEL, str)
        assert isinstance(HUMAN_LABEL, str)
        assert isinstance(CONTEXT_LABEL, str)
        assert len(PERSONA_LABEL) > 0
        assert len(HUMAN_LABEL) > 0
        assert len(CONTEXT_LABEL) > 0


class TestEidolonConfig:
    """Tests for EidolonConfig."""

    def test_default_config(self) -> None:
        """Default config has expected values."""
        config = EidolonConfig()
        assert config.base_url == "http://localhost:8283"
        assert config.api_key is None
        assert "anthropic" in config.model.lower() or "claude" in config.model.lower()
        assert config.default_timezone == "America/New_York"

    def test_custom_config(self) -> None:
        """Custom config values are preserved."""
        config = EidolonConfig(
            base_url="http://custom:9999",
            api_key="test-key",
            model="custom-model",
            default_timezone="Europe/London",
        )
        assert config.base_url == "http://custom:9999"
        assert config.api_key == "test-key"
        assert config.model == "custom-model"
        assert config.default_timezone == "Europe/London"


class TestEidolonMemory:
    """Tests for EidolonMemory client."""

    @pytest.fixture
    def mock_letta(self) -> MagicMock:
        """Create a mock Letta client."""
        mock = MagicMock()
        # Mock agents.list() to return empty list
        mock.agents.list.return_value = []
        # Mock agents.create() to return an agent
        mock_agent = MagicMock()
        mock_agent.id = "test-agent-id"
        mock_agent.name = "erebus-123456"
        mock.agents.create.return_value = mock_agent
        # Mock messages.create() to return a response
        mock_response = MagicMock()
        mock_response.messages = [MagicMock(content="Hello from Erebus!")]
        mock.agents.messages.create.return_value = mock_response
        return mock

    @patch("agents.eidolon.client.Letta")
    def test_init_creates_client(self, mock_letta_class: MagicMock) -> None:
        """EidolonMemory creates Letta client on init."""
        config = EidolonConfig(base_url="http://test:8283")
        EidolonMemory(config)
        mock_letta_class.assert_called_once_with(
            base_url="http://test:8283",
            token=None,
        )

    @patch("agents.eidolon.client.Letta")
    def test_init_with_api_key(self, mock_letta_class: MagicMock) -> None:
        """EidolonMemory passes API key to client."""
        config = EidolonConfig(api_key="test-key")
        EidolonMemory(config)
        mock_letta_class.assert_called_once_with(
            base_url="http://localhost:8283",
            token="test-key",
        )

    @patch("agents.eidolon.client.Letta")
    @pytest.mark.asyncio
    async def test_get_or_create_agent_creates_new(
        self, mock_letta_class: MagicMock, mock_letta: MagicMock
    ) -> None:
        """get_or_create_agent creates new agent when none exists."""
        mock_letta_class.return_value = mock_letta

        eidolon = EidolonMemory()
        agent_id = await eidolon.get_or_create_agent(
            user_id=123456,
            user_name="TestUser",
            timezone="America/Chicago",
        )

        assert agent_id == "test-agent-id"
        mock_letta.agents.create.assert_called_once()

    @patch("agents.eidolon.client.Letta")
    @pytest.mark.asyncio
    async def test_get_or_create_agent_returns_existing(
        self, mock_letta_class: MagicMock, mock_letta: MagicMock
    ) -> None:
        """get_or_create_agent returns existing agent if found."""
        # Set up mock to return existing agent
        existing_agent = MagicMock()
        existing_agent.id = "existing-agent-id"
        existing_agent.name = "erebus-123456"
        mock_letta.agents.list.return_value = [existing_agent]
        mock_letta_class.return_value = mock_letta

        eidolon = EidolonMemory()
        agent_id = await eidolon.get_or_create_agent(user_id=123456)

        assert agent_id == "existing-agent-id"
        mock_letta.agents.create.assert_not_called()

    @patch("agents.eidolon.client.Letta")
    @pytest.mark.asyncio
    async def test_get_or_create_agent_uses_cache(
        self, mock_letta_class: MagicMock, mock_letta: MagicMock
    ) -> None:
        """get_or_create_agent uses cache on second call."""
        mock_letta_class.return_value = mock_letta

        eidolon = EidolonMemory()
        # First call creates agent
        await eidolon.get_or_create_agent(user_id=123456)
        # Second call should use cache
        await eidolon.get_or_create_agent(user_id=123456)

        # Should only create once
        assert mock_letta.agents.create.call_count == 1

    @patch("agents.eidolon.client.Letta")
    @pytest.mark.asyncio
    async def test_chat_returns_response(
        self, mock_letta_class: MagicMock, mock_letta: MagicMock
    ) -> None:
        """chat returns agent response text."""
        mock_letta_class.return_value = mock_letta

        eidolon = EidolonMemory()
        response = await eidolon.chat(
            user_id=123456,
            message="Hello!",
        )

        assert response == "Hello from Erebus!"
        mock_letta.agents.messages.create.assert_called_once()

    @patch("agents.eidolon.client.Letta")
    @pytest.mark.asyncio
    async def test_get_agent_id_returns_none_for_unknown(
        self, mock_letta_class: MagicMock, mock_letta: MagicMock
    ) -> None:
        """get_agent_id returns None for unknown user."""
        mock_letta_class.return_value = mock_letta

        eidolon = EidolonMemory()
        agent_id = await eidolon.get_agent_id(user_id=999999)

        assert agent_id is None

    @patch("agents.eidolon.client.Letta")
    @pytest.mark.asyncio
    async def test_clear_agent_deletes_and_returns_true(
        self, mock_letta_class: MagicMock, mock_letta: MagicMock
    ) -> None:
        """clear_agent deletes agent and returns True."""
        mock_letta_class.return_value = mock_letta

        eidolon = EidolonMemory()
        # Create agent first
        await eidolon.get_or_create_agent(user_id=123456)
        # Now clear it
        result = await eidolon.clear_agent(user_id=123456)

        assert result is True
        mock_letta.agents.delete.assert_called_once()

    @patch("agents.eidolon.client.Letta")
    @pytest.mark.asyncio
    async def test_clear_agent_returns_false_for_unknown(
        self, mock_letta_class: MagicMock, mock_letta: MagicMock
    ) -> None:
        """clear_agent returns False for unknown user."""
        mock_letta_class.return_value = mock_letta

        eidolon = EidolonMemory()
        result = await eidolon.clear_agent(user_id=999999)

        assert result is False
        mock_letta.agents.delete.assert_not_called()

    @patch("agents.eidolon.client.Letta")
    def test_health_check_returns_true_when_healthy(
        self, mock_letta_class: MagicMock, mock_letta: MagicMock
    ) -> None:
        """health_check returns True when server is responding."""
        mock_letta_class.return_value = mock_letta

        eidolon = EidolonMemory()
        result = eidolon.health_check()

        assert result is True

    @patch("agents.eidolon.client.Letta")
    def test_health_check_returns_false_on_error(
        self, mock_letta_class: MagicMock, mock_letta: MagicMock
    ) -> None:
        """health_check returns False when server fails."""
        mock_letta.agents.list.side_effect = Exception("Connection failed")
        mock_letta_class.return_value = mock_letta

        eidolon = EidolonMemory()
        result = eidolon.health_check()

        assert result is False

    def test_get_agent_name_format(self) -> None:
        """Agent names follow expected format."""
        eidolon = EidolonMemory.__new__(EidolonMemory)
        name = eidolon._get_agent_name(123456789)
        assert name == "erebus-123456789"

    @patch("agents.eidolon.client.Letta")
    def test_init_with_tool_registry(self, mock_letta_class: MagicMock) -> None:
        """EidolonMemory accepts optional tool registry."""
        from agents.eidolon import ToolRegistry

        registry = ToolRegistry()
        eidolon = EidolonMemory(tool_registry=registry)
        assert eidolon.tool_registry is registry

    @patch("agents.eidolon.client.Letta")
    def test_init_creates_empty_registry_if_none(
        self, mock_letta_class: MagicMock
    ) -> None:
        """EidolonMemory creates empty registry if none provided."""
        from agents.eidolon import ToolRegistry

        eidolon = EidolonMemory()
        assert isinstance(eidolon.tool_registry, ToolRegistry)
        assert len(eidolon.tool_registry.tools) == 0


class TestToolRegistry:
    """Tests for ToolRegistry."""

    def test_register_adds_tools(self) -> None:
        """register adds tools to the registry."""
        from agents.eidolon import ToolRegistry
        from agents.models.base import ToolDefinition

        registry = ToolRegistry()
        tools = [
            ToolDefinition(
                name="test_tool",
                description="A test tool",
                input_schema={"type": "object", "properties": {}},
            )
        ]

        class MockExecutor:
            def can_handle(self, tool_name: str) -> bool:
                return tool_name == "test_tool"

            async def execute(self, tool_name: str, arguments: dict) -> str:
                return "result"

        registry.register(tools, MockExecutor())
        assert len(registry.tools) == 1
        assert registry.tools[0].name == "test_tool"

    def test_tool_names_returns_names(self) -> None:
        """tool_names returns list of tool names."""
        from agents.eidolon import ToolRegistry
        from agents.models.base import ToolDefinition

        registry = ToolRegistry()
        tools = [
            ToolDefinition(
                name="tool_a",
                description="Tool A",
                input_schema={"type": "object"},
            ),
            ToolDefinition(
                name="tool_b",
                description="Tool B",
                input_schema={"type": "object"},
            ),
        ]

        class MockExecutor:
            def can_handle(self, tool_name: str) -> bool:
                return True

            async def execute(self, tool_name: str, arguments: dict) -> str:
                return "result"

        registry.register(tools, MockExecutor())
        assert registry.tool_names == ["tool_a", "tool_b"]

    def test_can_handle_returns_true_for_registered_tool(self) -> None:
        """can_handle returns True for registered tools."""
        from agents.eidolon import ToolRegistry
        from agents.models.base import ToolDefinition

        registry = ToolRegistry()
        tools = [
            ToolDefinition(
                name="my_tool",
                description="My tool",
                input_schema={"type": "object"},
            ),
        ]

        class MockExecutor:
            def can_handle(self, tool_name: str) -> bool:
                return tool_name == "my_tool"

            async def execute(self, tool_name: str, arguments: dict) -> str:
                return "result"

        registry.register(tools, MockExecutor())
        assert registry.can_handle("my_tool") is True
        assert registry.can_handle("unknown_tool") is False

    @pytest.mark.asyncio
    async def test_execute_calls_executor(self) -> None:
        """execute calls the correct executor."""
        from agents.eidolon import ToolRegistry
        from agents.models.base import ToolDefinition

        registry = ToolRegistry()
        tools = [
            ToolDefinition(
                name="my_tool",
                description="My tool",
                input_schema={"type": "object"},
            ),
        ]

        class MockExecutor:
            def can_handle(self, tool_name: str) -> bool:
                return tool_name == "my_tool"

            async def execute(self, tool_name: str, arguments: dict) -> str:
                return f"executed {tool_name} with {arguments}"

        registry.register(tools, MockExecutor())
        result = await registry.execute("my_tool", {"arg": "value"})
        assert result == "executed my_tool with {'arg': 'value'}"

    @pytest.mark.asyncio
    async def test_execute_raises_for_unknown_tool(self) -> None:
        """execute raises ValueError for unknown tools."""
        from agents.eidolon import ToolRegistry

        registry = ToolRegistry()
        with pytest.raises(ValueError, match="No executor found"):
            await registry.execute("unknown_tool", {})


class TestToolConversion:
    """Tests for tool format conversion functions."""

    def test_convert_to_letta_tool_format(self) -> None:
        """convert_to_letta_tool_format creates correct dict."""
        from agents.eidolon import convert_to_letta_tool_format
        from agents.models.base import ToolDefinition

        tool = ToolDefinition(
            name="my_tool",
            description="Does something useful",
            input_schema={
                "type": "object",
                "properties": {"arg1": {"type": "string"}},
            },
        )

        result = convert_to_letta_tool_format(tool)
        assert result == {
            "name": "my_tool",
            "description": "Does something useful",
            "parameters": {
                "type": "object",
                "properties": {"arg1": {"type": "string"}},
            },
        }

    def test_convert_tools_to_letta_format(self) -> None:
        """convert_tools_to_letta_format converts list of tools."""
        from agents.eidolon import convert_tools_to_letta_format
        from agents.models.base import ToolDefinition

        tools = [
            ToolDefinition(name="a", description="A", input_schema={"type": "object"}),
            ToolDefinition(name="b", description="B", input_schema={"type": "object"}),
        ]

        result = convert_tools_to_letta_format(tools)
        assert len(result) == 2
        assert result[0]["name"] == "a"
        assert result[1]["name"] == "b"

    def test_get_tool_names(self) -> None:
        """get_tool_names extracts names from tool list."""
        from agents.eidolon import get_tool_names
        from agents.models.base import ToolDefinition

        tools = [
            ToolDefinition(name="x", description="X", input_schema={}),
            ToolDefinition(name="y", description="Y", input_schema={}),
            ToolDefinition(name="z", description="Z", input_schema={}),
        ]

        result = get_tool_names(tools)
        assert result == ["x", "y", "z"]
