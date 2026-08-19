"""
bot.py
------
PHASE 1 of the AI News Automation Agent.

What this script does (and ONLY this):
1. Loads and validates configuration (bot token + channel ID) from .env
2. Connects to the Telegram Bot API using that token
3. Sends ONE test message to your Telegram channel
4. Prints a clear success or failure message in the terminal
5. Exits cleanly

This script does NOT scrape news, use AI, schedule anything, use a
database, or touch Instagram. Those are for later phases.
"""

import asyncio
import sys

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


# This is the exact test message required for Phase 1.
TEST_MESSAGE = (
    "🤖 AI News Agent is connected!\n"
    "This is my first automated Telegram post.\n\n"
    "📰 News\n"
    "💻 Technology\n"
    "🏏 Sports\n"
    "🎬 Entertainment\n\n"
    "Automation system: ONLINE ✅"
)


async def send_test_message():
    """
    Connects to Telegram using the bot token and sends TEST_MESSAGE
    to the configured channel. Handles the most common errors a
    beginner is likely to run into, with plain-English explanations.
    """

    # By default, python-telegram-bot only waits ~5 seconds for a
    # connection before giving up. On some Windows setups (antivirus
    # SSL inspection, slower TLS handshakes, VPNs, etc.) that's too
    # short even though the network itself is fine. We give it more
    # breathing room here.
    request = HTTPXRequest(
        connect_timeout=20.0,
        read_timeout=20.0,
        write_timeout=20.0,
        pool_timeout=20.0,
    )

    # Bot(...) creates a connection object using our secret token.
    # This does NOT print or expose the token anywhere.
    bot = Bot(token=config.TELEGRAM_BOT_TOKEN, request=request)

    try:
        # Ask Telegram "who am I?" - a lightweight way to confirm the
        # token itself is valid before we try to post anything.
        me = await bot.get_me()
        print(f"[bot] Connected to Telegram as: @{me.username}")

        # Actually send the message to the channel.
        await bot.send_message(
            chat_id=config.TELEGRAM_CHANNEL_ID,
            text=TEST_MESSAGE,
        )

        print("\n========================================")
        print(" SUCCESS: Test message sent to your channel!")
        print("========================================")
        print("Go check your Telegram channel now — the message")
        print("should already be visible there.")

    except InvalidToken:
        print("\n[ERROR] Invalid Token (Unauthorized / 401)")
        print("This means your BOT TOKEN is invalid, malformed, or has been revoked.")
        print("How to fix:")
        print(" 1. Open Telegram and message @BotFather")
        print(" 2. Send /mybots -> select your bot -> API Token")
        print(" 3. Copy the token exactly into your .env file")
        print(" 4. Make sure there are no extra spaces or quotes around it")
        sys.exit(1)

    except Forbidden:
        print("\n[ERROR] Forbidden (403)")
        print("This means your bot does not have permission to post in")
        print("that channel. This is the most common Phase 1 mistake.")
        print("How to fix:")
        print(" 1. Open your Telegram channel")
        print(" 2. Go to Administrators")
        print(" 3. Add your bot as an Administrator")
        print(" 4. Make sure 'Post Messages' permission is enabled")
        sys.exit(1)

    except ChatMigrated as e:
        print("\n[ERROR] Chat Migrated")
        print("The channel/group has migrated to a new ID.")
        print(f"Update TELEGRAM_CHANNEL_ID in your .env to: {e.new_chat_id}")
        sys.exit(1)

    except BadRequest as e:
        print("\n[ERROR] Bad Request")
        print(f"Telegram said: {e}")
        print("This usually means 'Chat not found' or the channel ID")
        print("is formatted incorrectly.")
        print("How to fix:")
        print(" 1. Double-check TELEGRAM_CHANNEL_ID in your .env")
        print(" 2. It should look like: -1001234567890 (a negative number)")
        print(" 3. Make sure the bot has been added to the channel as admin")
        print(" 4. See README.md 'How to find your Channel ID' section")
        sys.exit(1)

    except TimedOut:
        print("\n[ERROR] Request timed out")
        print("Telegram did not respond in time.")
        print("How to fix:")
        print(" 1. Check your internet connection")
        print(" 2. Try running the script again")
        sys.exit(1)

    except NetworkError as e:
        print("\n[ERROR] Network error")
        print(f"Details: {e}")
        print("How to fix:")
        print(" 1. Check that you are connected to the internet")
        print(" 2. Check if a firewall/VPN is blocking Telegram")
        print(" 3. Try again in a moment")
        sys.exit(1)

    except TelegramError as e:
        # Catch-all for any other Telegram-related error we didn't
        # specifically anticipate above.
        print("\n[ERROR] Telegram API error")
        print(f"Details: {e}")
        print("Please read the message above for clues, or check the")
        print("Troubleshooting section in README.md")
        sys.exit(1)


def main():
    print("========================================")
    print(" AI News Automation Agent - PHASE 1")
    print(" Testing Telegram connection...")
    print("========================================\n")

    # Step 1: make sure our .env values exist before doing anything else.
    config.validate_config()

    # Step 2: run the async Telegram logic.
    asyncio.run(send_test_message())

    print("\n[bot] Done. Exiting cleanly.")


if __name__ == "__main__":
    try:
        main()
    except ValueError as ve:
        # Raised by config.validate_config() when .env is incomplete.
        print(ve)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n[bot] Cancelled by user.")
        sys.exit(0)
