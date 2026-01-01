"""Anthropic/Claude model provider.

Implements the ModelProvider interface for Claude models.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import anthropic
from anthropic import APIError, APIStatusError, AsyncAnthropic
from anthropic import RateLimitError as AnthropicRateLimitError

from agents.models.base import (
    AuthenticationError,
    Message,
    ModelError,
    ModelProvider,
    RateLimitError,
    Response,
    Role,
    ToolDefinition,
    ToolUse,
)

logger = logging.getLogger(__name__)

# Retry configuration
MAX_RETRIES = 3
BASE_RETRY_DELAY = 1.0  # seconds
MAX_RETRY_DELAY = 60.0  # seconds


class AnthropicProvider(ModelProvider):
    """Anthropic/Claude model provider.

    Provides access to Claude models via the Anthropic API.
    Includes automatic retry logic for transient errors.

    Attributes:
        client: The Anthropic async client.
    """

    def __init__(self, api_key: str) -> None:
        """Initialize the Anthropic provider.

        Args:
            api_key: Anthropic API key.
        """
        self.client = AsyncAnthropic(api_key=api_key)
        self._default_model = "claude-haiku-4-5-20251001"

    @property
    def name(self) -> str:
        """Return the provider name."""
        return "anthropic"

    @property
    def default_model(self) -> str:
        """Return the default model identifier."""
        return self._default_model

    async def complete(
        self,
        messages: list[Message],
        *,
        system: str | None = None,
        tools: list[ToolDefinition] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> Response:
        """Generate a completion using Claude.

        Args:
            messages: The conversation history. Messages can contain tool_uses
                (for assistant messages) or tool_results (for user messages).
            system: System prompt to use.
            tools: Tools available for the model to call.
            model: Model to use (defaults to claude-sonnet-4-20250514).
            max_tokens: Maximum tokens to generate.
            temperature: Sampling temperature (0-1).

        Returns:
            The model's response.

        Raises:
            ModelError: If the request fails after retries.
            RateLimitError: If rate limited and retries exhausted.
            AuthenticationError: If API key is invalid.
        """
        # Input validation
        if not messages:
            raise ValueError("messages cannot be empty")
        if not 0 <= temperature <= 1:
            raise ValueError(f"temperature must be between 0 and 1, got {temperature}")
        if max_tokens <= 0:
            raise ValueError(f"max_tokens must be positive, got {max_tokens}")

        model = model or self.default_model

        # Convert messages to Anthropic format
        api_messages = self._convert_messages(messages)

        # Convert tools to Anthropic format
        api_tools = self._convert_tools(tools) if tools else None

        # Make request with retry logic
        return await self._request_with_retry(
            api_messages,
            system=system,
            tools=api_tools,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
        )

    async def _request_with_retry(
        self,
        messages: list[dict[str, Any]],
        *,
        system: str | None,
        tools: list[dict[str, Any]] | None,
        model: str,
        max_tokens: int,
        temperature: float,
    ) -> Response:
        """Make API request with exponential backoff retry.

        Args:
            messages: Anthropic-format messages.
            system: System prompt.
            tools: Anthropic-format tools.
            model: Model identifier.
            max_tokens: Maximum tokens.
            temperature: Sampling temperature.

        Returns:
            Parsed response.

        Raises:
            ModelError: If all retries fail.
        """
        last_error: Exception | None = None
        delay = BASE_RETRY_DELAY

        for attempt in range(MAX_RETRIES + 1):
            try:
                kwargs: dict[str, Any] = {
                    "model": model,
                    "messages": messages,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                }

                if system:
                    kwargs["system"] = system

                if tools:
                    kwargs["tools"] = tools

                response = await self.client.messages.create(**kwargs)
                return self._parse_response(response)

            except AnthropicRateLimitError as e:
                last_error = e
                retry_after = getattr(e, "retry_after", None)

                if attempt < MAX_RETRIES:
                    wait_time = retry_after if retry_after else min(delay, MAX_RETRY_DELAY)
                    logger.warning(
                        f"Rate limited, retrying in {wait_time}s (attempt {attempt + 1}/{MAX_RETRIES})"
                    )
                    await asyncio.sleep(wait_time)
                    delay *= 2  # Exponential backoff
                else:
                    raise RateLimitError(str(e), retry_after=retry_after) from e

            except APIStatusError as e:
                if e.status_code == 401:
                    raise AuthenticationError("Invalid API key") from e
                if e.status_code == 429:
                    # Rate limit (shouldn't reach here, but handle it)
                    last_error = e
                    if attempt < MAX_RETRIES:
                        wait_time = min(delay, MAX_RETRY_DELAY)
                        logger.warning(
                            f"Rate limited (429), retrying in {wait_time}s "
                            f"(attempt {attempt + 1}/{MAX_RETRIES})"
                        )
                        await asyncio.sleep(wait_time)
                        delay *= 2
                    else:
                        raise RateLimitError(str(e)) from e
                elif e.status_code >= 500:
                    # Server error, retry
                    last_error = e
                    if attempt < MAX_RETRIES:
                        wait_time = min(delay, MAX_RETRY_DELAY)
                        logger.warning(
                            f"Server error ({e.status_code}), retrying in {wait_time}s "
                            f"(attempt {attempt + 1}/{MAX_RETRIES})"
                        )
                        await asyncio.sleep(wait_time)
                        delay *= 2
                    else:
                        raise ModelError(f"Server error: {e}") from e
                else:
                    # Client error, don't retry
                    raise ModelError(f"API error: {e}") from e

            except APIError as e:
                # Generic API error
                last_error = e
                if attempt < MAX_RETRIES:
                    wait_time = min(delay, MAX_RETRY_DELAY)
                    logger.warning(
                        f"API error, retrying in {wait_time}s (attempt {attempt + 1}/{MAX_RETRIES})"
                    )
                    await asyncio.sleep(wait_time)
                    delay *= 2
                else:
                    raise ModelError(f"API error: {e}") from e

        # Should not reach here, but handle it
        raise ModelError(f"Request failed after {MAX_RETRIES} retries: {last_error}")

    def _convert_messages(self, messages: list[Message]) -> list[dict[str, Any]]:
        """Convert messages to Anthropic API format.

        Handles:
        - Simple text messages
        - Assistant messages with tool_uses
        - User messages with tool_results

        Args:
            messages: Our message format.

        Returns:
            Anthropic-format messages.
        """
        api_messages: list[dict[str, Any]] = []

        for msg in messages:
            if msg.role == Role.ASSISTANT and msg.tool_uses:
                # Assistant message with tool uses - build content blocks
                content_blocks: list[dict[str, Any]] = []
                if msg.content:
                    content_blocks.append({"type": "text", "text": msg.content})
                for tool_use in msg.tool_uses:
                    content_blocks.append(
                        {
                            "type": "tool_use",
                            "id": tool_use.id,
                            "name": tool_use.name,
                            "input": tool_use.input,
                        }
                    )
                api_messages.append(
                    {
                        "role": "assistant",
                        "content": content_blocks,
                    }
                )
            elif msg.role == Role.USER and msg.tool_results:
                # User message with tool results (may also have text content)
                content_blocks: list[dict[str, Any]] = []
                if msg.content:
                    content_blocks.append({"type": "text", "text": msg.content})
                content_blocks.extend(
                    {
                        "type": "tool_result",
                        "tool_use_id": result.tool_use_id,
                        "content": result.content,
                        "is_error": result.is_error,
                    }
                    for result in msg.tool_results
                )
                api_messages.append(
                    {
                        "role": "user",
                        "content": content_blocks,
                    }
                )
            else:
                # Simple text message
                api_messages.append(
                    {
                        "role": msg.role.value,
                        "content": msg.content or "",
                    }
                )

        return api_messages

    def _convert_tools(self, tools: list[ToolDefinition]) -> list[dict[str, Any]]:
        """Convert tools to Anthropic API format.

        Args:
            tools: Our tool definition format.

        Returns:
            Anthropic-format tools.
        """
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.input_schema,
            }
            for tool in tools
        ]

    def _parse_response(self, response: anthropic.types.Message) -> Response:
        """Parse Anthropic API response to our format.

        Args:
            response: Raw Anthropic response.

        Returns:
            Parsed response.
        """
        text_blocks: list[str] = []
        tool_uses: list[ToolUse] = []

        for block in response.content:
            if block.type == "text":
                text_blocks.append(block.text)
            elif block.type == "tool_use":
                tool_uses.append(
                    ToolUse(
                        id=block.id,
                        name=block.name,
                        input=block.input,
                    )
                )

        content = "\n".join(text_blocks) if text_blocks else None

        return Response(
            content=content,
            tool_uses=tool_uses,
            stop_reason=response.stop_reason,
            usage={
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            },
            model=response.model,
        )
