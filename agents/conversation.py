"""Conversation management for Erebus.

Handles per-user conversation history and context management.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from agents.models import Message, ModelProvider, Response, Role

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Default system prompt for Erebus
DEFAULT_SYSTEM_PROMPT = """You are Erebus, a personal AI assistant that operates through Discord.

Your personality:
- You are helpful, concise, dark, and occasionally dry-witted
- You respect the user's time and get to the point
- You're knowledgeable but admit when you don't know something
- You have a subtle, mysterious aesthetic (you are named after the primordial darkness)

Guidelines:
- Keep responses concise unless detail is requested
- Use markdown formatting when helpful (Discord supports it)
- If asked about capabilities you don't have, be honest about limitations
- Never pretend to have access to tools or data you don't have

Current capabilities:
- Natural conversation and questions
- (More capabilities will be added as Erebus grows)
"""

# Maximum messages to retain in conversation history
MAX_HISTORY_MESSAGES = 50


@dataclass
class Conversation:
    """A conversation with a single user.

    Attributes:
        user_id: Discord user ID for this conversation.
        messages: List of messages in the conversation.
        system_prompt: System prompt for this conversation.
    """

    user_id: int
    messages: list[Message] = field(default_factory=list)
    system_prompt: str = DEFAULT_SYSTEM_PROMPT

    def add_user_message(self, content: str) -> None:
        """Add a user message to the conversation.

        Args:
            content: The message content.
        """
        self.messages.append(Message(role=Role.USER, content=content))
        self._trim_history()

    def add_assistant_message(self, response: Response) -> None:
        """Add an assistant message from a model response.

        Args:
            response: The model response.
        """
        self.messages.append(
            Message(
                role=Role.ASSISTANT,
                content=response.content,
                tool_uses=response.tool_uses,
            )
        )
        self._trim_history()

    def _trim_history(self) -> None:
        """Trim conversation history to stay within limits."""
        if len(self.messages) > MAX_HISTORY_MESSAGES:
            # Keep the most recent messages
            self.messages = self.messages[-MAX_HISTORY_MESSAGES:]
            logger.debug(
                f"Trimmed conversation history for user {self.user_id} "
                f"to {MAX_HISTORY_MESSAGES} messages"
            )

    def clear(self) -> None:
        """Clear the conversation history."""
        self.messages.clear()
        logger.info(f"Cleared conversation history for user {self.user_id}")


class ConversationManager:
    """Manages conversations across multiple users.

    Handles conversation state, model interaction, and history management.

    Attributes:
        model: The model provider to use for completions.
        conversations: Active conversations by user ID.
    """

    def __init__(self, model: ModelProvider) -> None:
        """Initialize the conversation manager.

        Args:
            model: The model provider to use.
        """
        self.model = model
        self.conversations: dict[int, Conversation] = {}

    def get_conversation(self, user_id: int) -> Conversation:
        """Get or create a conversation for a user.

        Args:
            user_id: Discord user ID.

        Returns:
            The conversation for this user.
        """
        if user_id not in self.conversations:
            self.conversations[user_id] = Conversation(user_id=user_id)
            logger.info(f"Created new conversation for user {user_id}")
        return self.conversations[user_id]

    async def chat(self, user_id: int, message: str) -> Response:
        """Send a message and get a response.

        Args:
            user_id: Discord user ID.
            message: The user's message.

        Returns:
            The model's response.

        Raises:
            ModelError: If the model request fails.
        """
        conversation = self.get_conversation(user_id)
        conversation.add_user_message(message)

        response = await self.model.complete(
            messages=conversation.messages,
            system=conversation.system_prompt,
        )

        conversation.add_assistant_message(response)

        logger.debug(
            f"Chat with user {user_id}: "
            f"input_tokens={response.usage.get('input_tokens', 0)}, "
            f"output_tokens={response.usage.get('output_tokens', 0)}"
        )

        return response

    def clear_conversation(self, user_id: int) -> bool:
        """Clear a user's conversation history.

        Args:
            user_id: Discord user ID.

        Returns:
            True if conversation existed and was cleared.
        """
        if user_id in self.conversations:
            self.conversations[user_id].clear()
            return True
        return False
