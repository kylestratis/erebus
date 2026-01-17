"""Erebus bot entry point.

Run with: python -m bot
         python -m bot --debug
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from pydantic import ValidationError

from bot.client import ErebusBot
from bot.config import get_settings
from bot.logging import setup_logging

logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments.

    Returns:
        Parsed arguments namespace.
    """
    parser = argparse.ArgumentParser(
        prog="erebus",
        description="Erebus - AI assistant with persistent memory",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging (overrides LOG_LEVEL env var)",
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Set log level (overrides LOG_LEVEL env var)",
    )
    return parser.parse_args()


async def main(args: argparse.Namespace) -> int:
    """Run the Erebus bot.

    Args:
        args: Parsed command-line arguments.

    Returns:
        Exit code (0 for success, 1 for error).
    """
    try:
        # Load configuration
        settings = get_settings()
    except ValidationError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        return 1

    # Override log level from CLI args
    if args.debug:
        settings.log_level = "DEBUG"
    elif args.log_level:
        settings.log_level = args.log_level

    # Set up logging (must be done before using logger)
    setup_logging(settings)
    logger.info(f"Loaded configuration for {settings.environment.value} environment")
    if args.debug:
        logger.debug("Debug mode enabled via --debug flag")
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
    args = parse_args()
    exit_code = asyncio.run(main(args))
    sys.exit(exit_code)


if __name__ == "__main__":
    run()
