"""
publisher.py
------------
PHASE 2 of the AI News Automation Agent.

This file's ONLY job is publishing text to your Telegram channel.
It does not know or care where the text came from, and it does not
know anything about schedules or posts.json — that's scheduler.py's
job. This separation is intentional: scheduler.py decides WHEN and
WHAT to post, publisher.py only knows HOW to post it.

It reuses the exact same TELEGRAM_BOT_TOKEN / TELEGRAM_CHANNEL_ID
configuration from config.py that bot.py (Phase 1) already uses —
nothing is duplicated.

Public function:
    publish_text(text: str) -> bool
        Sends `text` to the configured Telegram channel.
        Returns True if it was sent successfully, False otherwise.
        Never raises an exception to the caller — all errors are
        caught, logged, and turned into a False return value, so
        scheduler.py can safely keep processing other posts even if
        one publish attempt fails.
"""

import asyncio
import logging

from telegram import Bot
from telegram.request import HTTPXRequest
from telegram.error import (
    InvalidToken,
    Forbidden,
    ChatMigrated,
    BadRequest,
    TimedOut,
    NetworkError,
    TelegramError,
)

import config

logger = logging.getLogger("publisher")


def _build_bot() -> Bot:
    """
    Creates a Bot instance with generous timeouts.

    We learned in Phase 1 testing that the library's default 5-second
    timeout is sometimes too short on Windows (antivirus SSL
    inspection, slower TLS handshakes, etc.), so we use the same
    longer timeout settings here.
    """
    request = HTTPXRequest(
        connect_timeout=20.0,
        read_timeout=20.0,
        write_timeout=20.0,
        pool_timeout=20.0,
    )
    return Bot(token=config.TELEGRAM_BOT_TOKEN, request=request)


async def _publish_text_async(text: str) -> bool:
    """
    The actual async logic that talks to Telegram.
    publish_text() below wraps this so callers don't need to deal
    with asyncio themselves.
    """
    bot = _build_bot()

    try:
        await bot.send_message(
            chat_id=config.TELEGRAM_CHANNEL_ID,
            text=text,
        )
        return True

    except InvalidToken:
        logger.error(
            "Publish failed: Invalid bot token. "
            "Get a fresh token from @BotFather and update .env."
        )
        return False

    except Forbidden:
        logger.error(
            "Publish failed: Forbidden. The bot is not an admin of the "
            "channel, or lacks 'Post Messages' permission."
        )
        return False

    except ChatMigrated as e:
        logger.error(
            "Publish failed: Chat migrated. Update TELEGRAM_CHANNEL_ID "
            "in .env to: %s",
            e.new_chat_id,
        )
        return False

    except BadRequest as e:
        logger.error(
            "Publish failed: Bad Request (%s). Check that "
            "TELEGRAM_CHANNEL_ID in .env is correct and the bot has "
            "been added to the channel.",
            e,
        )
        return False

    except TimedOut:
        logger.error(
            "Publish failed: Request timed out. Check your internet "
            "connection and try again."
        )
        return False

    except NetworkError as e:
        logger.error("Publish failed: Network error (%s).", e)
        return False

    except TelegramError as e:
        logger.error("Publish failed: Telegram API error (%s).", e)
        return False

    except Exception as e:  # noqa: BLE001 - last-resort safety net
        # We deliberately catch anything unexpected here too, because
        # scheduler.py must NEVER crash just because one post failed
        # to publish. We still log it so the problem is visible.
        logger.error("Publish failed: Unexpected error (%s).", e)
        return False


def publish_text(text: str) -> bool:
    """
    Synchronous entry point used by scheduler.py.

    Loads/validates config, then sends `text` to the Telegram channel.
    Returns True on success, False on any failure. Never prints or
    logs the bot token.
    """
    try:
        config.validate_config()
    except ValueError as e:
        logger.error("Publish failed: %s", e)
        return False

    return asyncio.run(_publish_text_async(text))
