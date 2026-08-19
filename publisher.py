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


import html
from datetime import datetime, timezone, timedelta

def format_html_post(post: dict) -> str:
    """
    Safely formats a post dictionary into clean, professional Telegram HTML.
    Supports breaking news header, category branding, summary, '📌 Why it matters:',
    timestamp in IST, source attribution, and validated clickable source link.
    """
    is_breaking = post.get("is_breaking") or post.get("score", 0) >= getattr(config, "BREAKING_NEWS_SCORE_THRESHOLD", 90)
    category_raw = str(post.get("category", "NEWS")).upper()
    
    emoji_map = {
        "NEWS": "📰",
        "TECHNOLOGY": "💻",
        "SPORTS": "🏏",
        "ENTERTAINMENT": "🎬"
    }
    cat_emoji = emoji_map.get(category_raw, "📰")
    
    header = "🚨 <b>BREAKING NEWS</b>" if is_breaking else f"<b>{cat_emoji} {category_raw}</b>"
    
    title = html.escape(post.get("title", "").replace("🔥 ", "").strip())
    raw_summary = post.get("summary") or post.get("content") or post.get("description", "")
    if "📰 Source:" in raw_summary:
        raw_summary = raw_summary.split("📰 Source:")[0].strip()
    if "🔗 Read More:" in raw_summary:
        raw_summary = raw_summary.split("🔗 Read More:")[0].strip()
    summary = html.escape(raw_summary.strip())
    why_it_matters = html.escape(post.get("why_it_matters", "").strip())

    
    sources_list = post.get("sources_list") or []
    if sources_list:
        sources_str = html.escape(", ".join(sources_list))
    else:
        sources_str = html.escape(post.get("source", "Unknown Source").strip())
        
    url = post.get("original_url") or post.get("url", "")
    if url and not (url.startswith("http://") or url.startswith("https://")):
        url = ""
        
    pub_time = post.get("published_at") or post.get("scheduled_time")
    dt = None
    if pub_time:
        try:
            from news_collector import parse_published_time
            dt = parse_published_time(str(pub_time))
        except Exception:
            pass
    if not dt:
        dt = datetime.now(timezone.utc)
        
    ist_dt = dt.astimezone(timezone(timedelta(hours=5, minutes=30)))
    time_str = ist_dt.strftime("%I:%M %p IST")


    parts = [header, ""]
    if title:
        parts.append(f"<b>{title}</b>\n")
    if summary:
        parts.append(f"{summary}\n")
    if why_it_matters:
        parts.append(f"📌 <b>Why it matters:</b>\n{why_it_matters}\n")
        
    parts.append(f"🏷️ <b>Category:</b> {category_raw.capitalize()}")
    parts.append(f"🕒 <b>Published:</b> {time_str}")
    parts.append(f"📰 <b>Source:</b> {sources_str}")
    
    if url:
        parts.append(f"\n🔗 <a href=\"{url}\">Read full story</a>")
        
    return "\n".join(parts)


async def _publish_post_async(post: dict) -> bool:
    """
    Publishes a post dictionary, attempting video or photo publishing first if available,
    with automatic fallback to text message if media publishing fails.
    """
    bot = _build_bot()
    video_url = post.get("video_url") or post.get("video", "")
    image_url = post.get("image_url") or post.get("image", "")
    
    formatted_html = format_html_post(post)
    parse_mode = "HTML"

    if video_url and (video_url.startswith("http://") or video_url.startswith("https://")):
        try:
            logger.info("[TELEGRAM] Attempting video publish (Video: %s)", video_url[:60])
            await bot.send_video(
                chat_id=config.TELEGRAM_CHANNEL_ID,
                video=video_url,
                caption=formatted_html[:1024],
                parse_mode=parse_mode
            )
            return True
        except Exception as vid_err:
            logger.warning("[TELEGRAM] Video publish failed (%s). Falling back to photo/text.", vid_err)
    
    if image_url and (image_url.startswith("http://") or image_url.startswith("https://")):
        try:
            logger.info("[TELEGRAM] Attempting photo publish (Image: %s)", image_url[:60])
            await bot.send_photo(
                chat_id=config.TELEGRAM_CHANNEL_ID,
                photo=image_url,
                caption=formatted_html[:1024],
                parse_mode=parse_mode
            )
            return True
        except Exception as img_err:
            logger.warning("[TELEGRAM] Photo publish failed (%s). Falling back to text-only.", img_err)


    try:
        await bot.send_message(
            chat_id=config.TELEGRAM_CHANNEL_ID,
            text=formatted_html[:4096],
            parse_mode=parse_mode,
            disable_web_page_preview=False
        )
        return True
    except BadRequest as e:
        logger.warning("[TELEGRAM] HTML parse failed (%s). Retrying plain text.", e)
        try:
            # Strip HTML tags as ultimate safety fallback
            clean_text = post.get("title", "") + "\n\n" + (post.get("content") or post.get("description", ""))
            await bot.send_message(
                chat_id=config.TELEGRAM_CHANNEL_ID,
                text=clean_text[:4096]
            )
            return True
        except Exception as fallback_err:
            logger.error("[TELEGRAM] Plain text fallback failed: %s", fallback_err)
            return False
    except Exception as e:
        logger.error("[TELEGRAM] Message publish failed: %s", e)
        return False



def publish_post(post: dict) -> bool:
    """
    Synchronous entry point to publish a post dictionary safely.
    """
    try:
        config.validate_config()
    except ValueError as e:
        logger.error("Publish failed: %s", e)
        return False

    return asyncio.run(_publish_post_async(post))


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

