"""Tests for the eidolon module.

Tests memory block definitions and EidolonMemory client (with mocked Letta).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

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

    def test_default_model_has_valid_provider_format(self) -> None:
        """Default model string follows provider/model-name format.

        Letta requires models in 'provider/model' format. This test catches
        typos that would cause 'provider not supported' errors at runtime.
        """
        from agents.eidolon.client import DEFAULT_EMBEDDING, DEFAULT_MODEL

        # Verify format is provider/model
        assert "/" in DEFAULT_MODEL, f"Model must be in 'provider/model' format: {DEFAULT_MODEL}"
        assert "/" in DEFAULT_EMBEDDING, (
            f"Embedding must be in 'provider/model' format: {DEFAULT_EMBEDDING}"
        )

        # Verify providers are known-supported
        supported_providers = {"anthropic", "openai", "letta"}
        model_provider = DEFAULT_MODEL.split("/")[0]
        embed_provider = DEFAULT_EMBEDDING.split("/")[0]

        assert model_provider in supported_providers, (
            f"Model provider '{model_provider}' not in supported providers: {supported_providers}"
        )
        assert embed_provider in supported_providers, (
            f"Embedding provider '{embed_provider}' not in supported providers: {supported_providers}"
        )


class TestEidolonMemory:
    """Tests for EidolonMemory client."""

    @pytest.fixture
    def mock_letta(self) -> MagicMock:
        """Create a mock AsyncLetta client with async methods."""
        mock = MagicMock()
        # Mock agents.list() as async - returns AsyncArrayPage-like object with .items
        mock_page = MagicMock()
        mock_page.items = []
        mock.agents.list = AsyncMock(return_value=mock_page)
        # Mock agents.create() as async - returns an agent
        mock_agent = MagicMock()
        mock_agent.id = "test-agent-id"
        mock_agent.name = "erebus-123456"
        mock.agents.create = AsyncMock(return_value=mock_agent)
        # Mock agents.delete() as async
        mock.agents.delete = AsyncMock()
        # Mock messages.create() as async - returns a response
        mock_response = MagicMock()
        mock_response.messages = [MagicMock(content="Hello from Erebus!")]
        mock.agents.messages.create = AsyncMock(return_value=mock_response)
        return mock

    @patch("agents.eidolon.client.AsyncLetta")
    def test_init_creates_client(self, mock_letta_class: MagicMock) -> None:
        """EidolonMemory creates AsyncLetta client on init."""
        config = EidolonConfig(base_url="http://test:8283")
        EidolonMemory(config)
        mock_letta_class.assert_called_once_with(
            base_url="http://test:8283",
            api_key=None,
        )

    @patch("agents.eidolon.client.AsyncLetta")
    def test_init_with_api_key(self, mock_letta_class: MagicMock) -> None:
        """EidolonMemory passes API key to AsyncLetta client."""
        config = EidolonConfig(api_key="test-key")
        EidolonMemory(config)
        mock_letta_class.assert_called_once_with(
            base_url="http://localhost:8283",
            api_key="test-key",
        )

    @patch("agents.eidolon.client.AsyncLetta")
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

    @patch("agents.eidolon.client.AsyncLetta")
    @pytest.mark.asyncio
    async def test_get_or_create_agent_returns_existing(
        self, mock_letta_class: MagicMock, mock_letta: MagicMock
    ) -> None:
        """get_or_create_agent returns existing agent if found."""
        # Set up mock to return existing agent via AsyncArrayPage-like object
        existing_agent = MagicMock()
        existing_agent.id = "existing-agent-id"
        existing_agent.name = "erebus-123456"
        mock_page = MagicMock()
        mock_page.items = [existing_agent]
        mock_letta.agents.list.return_value = mock_page
        mock_letta_class.return_value = mock_letta

        eidolon = EidolonMemory()
        agent_id = await eidolon.get_or_create_agent(user_id=123456)

        assert agent_id == "existing-agent-id"
        mock_letta.agents.create.assert_not_called()

    @patch("agents.eidolon.client.AsyncLetta")
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

    @patch("agents.eidolon.client.AsyncLetta")
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

    @patch("agents.eidolon.client.AsyncLetta")
    @pytest.mark.asyncio
    async def test_chat_uses_native_async_to_avoid_blocking(
        self, mock_letta_class: MagicMock, mock_letta: MagicMock
    ) -> None:
        """chat uses AsyncLetta for non-blocking operations.

        This prevents Discord heartbeat timeouts when Letta responses are slow.
        The AsyncLetta client provides native async support.
        """
        mock_letta_class.return_value = mock_letta

        eidolon = EidolonMemory()
        await eidolon.chat(user_id=123456, message="Hello!")

        # Verify AsyncLetta was instantiated (native async, no thread pool needed)
        mock_letta_class.assert_called_once()
        # Verify async methods were actually awaited (not just called)
        mock_letta.agents.messages.create.assert_awaited()
        mock_letta.agents.list.assert_awaited()  # from get_or_create_agent

    @patch("agents.eidolon.client.AsyncLetta")
    @pytest.mark.asyncio
    async def test_get_agent_id_returns_none_for_unknown(
        self, mock_letta_class: MagicMock, mock_letta: MagicMock
    ) -> None:
        """get_agent_id returns None for unknown user."""
        mock_letta_class.return_value = mock_letta

        eidolon = EidolonMemory()
        agent_id = await eidolon.get_agent_id(user_id=999999)

        assert agent_id is None

    @patch("agents.eidolon.client.AsyncLetta")
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

    @patch("agents.eidolon.client.AsyncLetta")
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

    @patch("agents.eidolon.client.AsyncLetta")
    @pytest.mark.asyncio
    async def test_health_check_returns_true_when_healthy(
        self, mock_letta_class: MagicMock, mock_letta: MagicMock
    ) -> None:
        """health_check returns True when server is responding."""
        mock_letta_class.return_value = mock_letta

        eidolon = EidolonMemory()
        result = await eidolon.health_check()

        assert result is True

    @patch("agents.eidolon.client.AsyncLetta")
    @pytest.mark.asyncio
    async def test_health_check_returns_false_on_error(
        self, mock_letta_class: MagicMock, mock_letta: MagicMock
    ) -> None:
        """health_check returns False when server fails."""
        mock_letta.agents.list.side_effect = Exception("Connection failed")
        mock_letta_class.return_value = mock_letta

        eidolon = EidolonMemory()
        result = await eidolon.health_check()

        assert result is False

    def test_get_agent_name_format(self) -> None:
        """Agent names follow expected format."""
        eidolon = EidolonMemory.__new__(EidolonMemory)
        name = eidolon._get_agent_name(123456789)
        assert name == "erebus-123456789"

    @patch("agents.eidolon.client.AsyncLetta")
    def test_init_with_tool_registry(self, mock_letta_class: MagicMock) -> None:
        """EidolonMemory accepts optional tool registry."""
        from agents.eidolon import ToolRegistry

        registry = ToolRegistry()
        eidolon = EidolonMemory(tool_registry=registry)
        assert eidolon.tool_registry is registry

    @patch("agents.eidolon.client.AsyncLetta")
    def test_init_creates_empty_registry_if_none(self, mock_letta_class: MagicMock) -> None:
        """EidolonMemory creates empty registry if none provided."""
        from agents.eidolon import ToolRegistry

        eidolon = EidolonMemory()
        assert isinstance(eidolon.tool_registry, ToolRegistry)
        assert len(eidolon.tool_registry.tools) == 0

    @patch("agents.eidolon.client.AsyncLetta")
    @pytest.mark.asyncio
    async def test_create_agent_registers_tools_with_letta(
        self, mock_letta_class: MagicMock, mock_letta: MagicMock
    ) -> None:
        """_create_agent registers tools and passes tool_ids to Letta."""
        from agents.eidolon import ToolRegistry
        from agents.models.base import ToolDefinition

        # Set up registry with a tool
        registry = ToolRegistry()
        tool_def = ToolDefinition(
            name="test_tool",
            description="A test tool",
            input_schema={"type": "object", "properties": {}},
        )

        class MockExecutor:
            def can_handle(self, tool_name: str) -> bool:
                return tool_name == "test_tool"

            async def execute(self, tool_name: str, arguments: dict) -> str:
                return "result"

        registry.register([tool_def], MockExecutor())

        # Mock tools.upsert to return a tool with an ID
        mock_tool = MagicMock()
        mock_tool.id = "tool-123"
        mock_letta.tools.upsert = AsyncMock(return_value=mock_tool)
        mock_letta_class.return_value = mock_letta

        eidolon = EidolonMemory(tool_registry=registry)
        await eidolon.get_or_create_agent(user_id=123456)

        # Verify tool was registered
        mock_letta.tools.upsert.assert_awaited_once()
        # Verify agent was created with tool_ids
        mock_letta.agents.create.assert_awaited_once()
        create_call = mock_letta.agents.create.call_args
        assert "tool_ids" in create_call.kwargs
        assert create_call.kwargs["tool_ids"] == ["tool-123"]


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


class TestCancelPendingApprovals:
    """Tests for _cancel_pending_approvals recovery mechanism."""

    @pytest.fixture
    def mock_letta(self) -> MagicMock:
        """Create a mock AsyncLetta client."""
        mock = MagicMock()
        # Default: empty messages list
        mock.agents.messages.list = AsyncMock(return_value=[])
        mock.agents.messages.create = AsyncMock(return_value=MagicMock())
        # Mock agents.list for initialization
        mock_page = MagicMock()
        mock_page.items = []
        mock.agents.list = AsyncMock(return_value=mock_page)
        return mock

    def _create_approval_message(
        self, tool_name: str = "test_tool", tool_call_id: str = "call-123"
    ) -> MagicMock:
        """Create a mock approval_request_message."""
        msg = MagicMock()
        msg.message_type = "approval_request_message"
        msg.tool_call = MagicMock()
        msg.tool_call.name = tool_name
        msg.tool_call.tool_call_id = tool_call_id
        return msg

    def _create_regular_message(self, msg_type: str = "user_message") -> MagicMock:
        """Create a mock non-approval message."""
        msg = MagicMock()
        msg.message_type = msg_type
        return msg

    @patch("agents.eidolon.client.AsyncLetta")
    @pytest.mark.asyncio
    async def test_no_messages_returns_zero(
        self, mock_letta_class: MagicMock, mock_letta: MagicMock
    ) -> None:
        """Returns 0 when agent has no messages."""
        mock_letta.agents.messages.list = AsyncMock(return_value=[])
        mock_letta_class.return_value = mock_letta

        eidolon = EidolonMemory()
        result = await eidolon._cancel_pending_approvals("agent-123")

        assert result == 0
        mock_letta.agents.messages.create.assert_not_called()

    @patch("agents.eidolon.client.AsyncLetta")
    @pytest.mark.asyncio
    async def test_no_pending_approvals_returns_zero(
        self, mock_letta_class: MagicMock, mock_letta: MagicMock
    ) -> None:
        """Returns 0 when no approval_request_message in messages."""
        messages = [
            self._create_regular_message("user_message"),
            self._create_regular_message("assistant_message"),
            self._create_regular_message("tool_return_message"),
        ]
        mock_letta.agents.messages.list = AsyncMock(return_value=messages)
        mock_letta_class.return_value = mock_letta

        eidolon = EidolonMemory()
        result = await eidolon._cancel_pending_approvals("agent-123")

        assert result == 0
        mock_letta.agents.messages.create.assert_not_called()

    @patch("agents.eidolon.client.AsyncLetta")
    @pytest.mark.asyncio
    async def test_cancels_single_pending_approval(
        self, mock_letta_class: MagicMock, mock_letta: MagicMock
    ) -> None:
        """Cancels a single pending approval and returns 1."""
        messages = [
            self._create_approval_message("vault_read", "call-abc"),
        ]
        mock_letta.agents.messages.list = AsyncMock(return_value=messages)
        mock_letta_class.return_value = mock_letta

        eidolon = EidolonMemory()
        result = await eidolon._cancel_pending_approvals("agent-123")

        assert result == 1
        mock_letta.agents.messages.create.assert_called_once()
        # Verify the cancellation message format
        call_args = mock_letta.agents.messages.create.call_args
        assert call_args.kwargs["agent_id"] == "agent-123"
        messages_sent = call_args.kwargs["messages"]
        assert len(messages_sent) == 1
        assert messages_sent[0]["type"] == "approval"
        assert messages_sent[0]["approvals"][0]["tool_call_id"] == "call-abc"
        assert messages_sent[0]["approvals"][0]["status"] == "error"

    @patch("agents.eidolon.client.AsyncLetta")
    @pytest.mark.asyncio
    async def test_cancels_multiple_pending_approvals(
        self, mock_letta_class: MagicMock, mock_letta: MagicMock
    ) -> None:
        """Cancels all pending approvals and returns count."""
        messages = [
            self._create_approval_message("tool_a", "call-1"),
            self._create_regular_message("user_message"),
            self._create_approval_message("tool_b", "call-2"),
            self._create_approval_message("tool_c", "call-3"),
        ]
        mock_letta.agents.messages.list = AsyncMock(return_value=messages)
        mock_letta_class.return_value = mock_letta

        eidolon = EidolonMemory()
        result = await eidolon._cancel_pending_approvals("agent-123")

        assert result == 3
        assert mock_letta.agents.messages.create.call_count == 3

    @patch("agents.eidolon.client.AsyncLetta")
    @pytest.mark.asyncio
    async def test_skips_approval_without_tool_call(
        self, mock_letta_class: MagicMock, mock_letta: MagicMock
    ) -> None:
        """Skips approval_request_message without tool_call attribute."""
        msg_no_tool_call = MagicMock()
        msg_no_tool_call.message_type = "approval_request_message"
        msg_no_tool_call.tool_call = None

        messages = [
            msg_no_tool_call,
            self._create_approval_message("valid_tool", "call-valid"),
        ]
        mock_letta.agents.messages.list = AsyncMock(return_value=messages)
        mock_letta_class.return_value = mock_letta

        eidolon = EidolonMemory()
        result = await eidolon._cancel_pending_approvals("agent-123")

        # Should only cancel the valid one
        assert result == 1
        mock_letta.agents.messages.create.assert_called_once()

    @patch("agents.eidolon.client.AsyncLetta")
    @pytest.mark.asyncio
    async def test_skips_approval_without_tool_call_id(
        self, mock_letta_class: MagicMock, mock_letta: MagicMock
    ) -> None:
        """Skips approval_request_message where tool_call has no tool_call_id."""
        msg_no_id = MagicMock()
        msg_no_id.message_type = "approval_request_message"
        msg_no_id.tool_call = MagicMock()
        msg_no_id.tool_call.name = "some_tool"
        msg_no_id.tool_call.tool_call_id = None

        messages = [
            msg_no_id,
            self._create_approval_message("valid_tool", "call-valid"),
        ]
        mock_letta.agents.messages.list = AsyncMock(return_value=messages)
        mock_letta_class.return_value = mock_letta

        eidolon = EidolonMemory()
        result = await eidolon._cancel_pending_approvals("agent-123")

        # Should only cancel the valid one
        assert result == 1

    @patch("agents.eidolon.client.AsyncLetta")
    @pytest.mark.asyncio
    async def test_continues_after_cancellation_failure(
        self, mock_letta_class: MagicMock, mock_letta: MagicMock
    ) -> None:
        """Continues cancelling other approvals if one fails."""
        messages = [
            self._create_approval_message("tool_a", "call-1"),
            self._create_approval_message("tool_b", "call-2"),
            self._create_approval_message("tool_c", "call-3"),
        ]
        mock_letta.agents.messages.list = AsyncMock(return_value=messages)
        # First call fails, second and third succeed
        mock_letta.agents.messages.create = AsyncMock(
            side_effect=[Exception("API error"), MagicMock(), MagicMock()]
        )
        mock_letta_class.return_value = mock_letta

        eidolon = EidolonMemory()
        result = await eidolon._cancel_pending_approvals("agent-123")

        # Should have attempted all 3, but only 2 succeeded
        assert result == 2
        assert mock_letta.agents.messages.create.call_count == 3

    @patch("agents.eidolon.client.AsyncLetta")
    @pytest.mark.asyncio
    async def test_returns_zero_on_list_failure(
        self, mock_letta_class: MagicMock, mock_letta: MagicMock
    ) -> None:
        """Returns 0 when listing messages fails."""
        mock_letta.agents.messages.list = AsyncMock(
            side_effect=Exception("Network error")
        )
        mock_letta_class.return_value = mock_letta

        eidolon = EidolonMemory()
        result = await eidolon._cancel_pending_approvals("agent-123")

        assert result == 0
        mock_letta.agents.messages.create.assert_not_called()

    @patch("agents.eidolon.client.AsyncLetta")
    @pytest.mark.asyncio
    async def test_uses_configured_limit(
        self, mock_letta_class: MagicMock, mock_letta: MagicMock
    ) -> None:
        """Uses PENDING_APPROVAL_CHECK_LIMIT when listing messages."""
        mock_letta.agents.messages.list = AsyncMock(return_value=[])
        mock_letta_class.return_value = mock_letta

        eidolon = EidolonMemory()
        await eidolon._cancel_pending_approvals("agent-123")

        # Verify the limit parameter was passed
        call_args = mock_letta.agents.messages.list.call_args
        assert call_args.kwargs["limit"] == eidolon.PENDING_APPROVAL_CHECK_LIMIT
