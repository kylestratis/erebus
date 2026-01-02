"""Erebus bot entry point.

Run with: python -m bot
"""

from __future__ import annotations

import asyncio
import logging
import sys

from pydantic import ValidationError

from bot.client import ErebusBot
from bot.config import get_settings
from bot.logging import setup_logging

logger = logging.getLogger(__name__)


async def main() -> int:
    """Run the Erebus bot.

    Returns:
        Exit code (0 for success, 1 for error).
    """
    try:
        # Load configuration
        settings = get_settings()
    except ValidationError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        return 1

    # Set up logging (must be done before using logger)
    setup_logging(settings)
    logger.info(f"Loaded configuration for {settings.environment.value} environment")
    logger.info("Erebus awakening...")

    # Create and run bot
    bot = ErebusBot(settings)

    try:
        await bot.start(settings.discord_bot_token)
    except KeyboardInterrupt:
        logger.info("Received interrupt, shutting down...")
    except Exception as e:
        logger.exception(f"Fatal error: {e}")
        return 1
    finally:
        if not bot.is_closed():
            await bot.close()
        logger.info("Erebus returns to the void.")

    return 0


def run() -> None:
    """Entry point for the bot."""
    exit_code = asyncio.run(main())
    sys.exit(exit_code)


if __name__ == "__main__":
    run()
