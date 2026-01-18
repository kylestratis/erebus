"""Erebus bot entry point.

Run with: python -m bot
         python -m bot --debug
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys

from pydantic import ValidationError

from bot.client import ErebusBot
from bot.logging import setup_logging
from config import get_config

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
    # Apply CLI log level overrides before loading config
    # This ensures the config picks up the correct value
    if args.debug:
        os.environ["LOG_LEVEL"] = "DEBUG"
    elif args.log_level:
        os.environ["LOG_LEVEL"] = args.log_level

    try:
        # Load configuration
        config = get_config()
    except ValidationError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        return 1

    # Set up logging (must be done before using logger)
    setup_logging(config)
    logger.info(f"Loaded configuration for {config.environment.value} environment")
    if args.debug:
        logger.debug("Debug mode enabled via --debug flag")
    logger.info("Erebus awakening...")

    # Create and run bot
    bot = ErebusBot(config)

    try:
        await bot.start(config.discord_bot_token)
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
