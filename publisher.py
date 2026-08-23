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
import re
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse

def is_valid_url(url: str) -> bool:
    """Checks if a URL is non-empty, well-formed, and uses http/https scheme."""
    if not url or not isinstance(url, str):
        return False
    url = url.strip()
    if not (url.startswith("http://") or url.startswith("https://")):
        return False
    try:
        res = urlparse(url)
        return bool(res.scheme and res.netloc)
    except Exception:
        return False


def validate_image_url(url: str, timeout: float = 3.0, max_bytes: int = 10 * 1024 * 1024) -> bool:
    """
    Fast HTTP HEAD/stream check to pre-validate image URL availability, Content-Type, and size.
    Prevents huge downloads or hanging servers from blocking Telegram publishing.
    """
    if not is_valid_url(url):
        return False
    try:
        import requests
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        resp = requests.head(url, headers=headers, timeout=timeout, allow_redirects=True)
        if resp.status_code != 200:
            resp = requests.get(url, headers=headers, stream=True, timeout=timeout, allow_redirects=True)
            if resp.status_code != 200:
                return False
        
        content_type = resp.headers.get("Content-Type", "").lower()
        if content_type and not content_type.startswith("image/") and "octet-stream" not in content_type and "binary" not in content_type:
            return False
            
        content_length = resp.headers.get("Content-Length")
        if content_length and content_length.isdigit():
            if int(content_length) > max_bytes:
                logger.warning("Image URL rejected (size %s bytes exceeds limit %s bytes): %s", content_length, max_bytes, url[:60])
                return False
        return True
    except Exception as e:
        logger.warning("Image pre-validation failed for %s: %s", url[:60], e)
        return False


def format_html_post(post: dict, max_length: int = 4096) -> str:
    """
    Safely formats a post dictionary into clean, professional Telegram HTML.
    Supports breaking news header, category branding, summary, '📌 Why it matters:',
    timestamp in IST, source attribution, and validated clickable source link.
    Budget-aware so total HTML string does not exceed max_length (e.g., 1024 for photo captions).
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
    
    title_raw = post.get("title", "").replace("🔥 ", "").strip()
    raw_summary = post.get("summary") or post.get("content") or post.get("description", "")
    if "📰 Source:" in raw_summary:
        raw_summary = raw_summary.split("📰 Source:")[0].strip()
    if "🔗 Read More:" in raw_summary:
        raw_summary = raw_summary.split("🔗 Read More:")[0].strip()
        
    summary_raw = raw_summary.strip()
    why_it_matters_raw = post.get("why_it_matters", "").strip()

    sources_list = post.get("sources_list") or []
    if sources_list:
        sources_str = ", ".join(sources_list)
    else:
        sources_str = post.get("source", "Unknown Source").strip()
        
    url = post.get("original_url") or post.get("url", "")
    if not is_valid_url(url):
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

    title = html.escape(title_raw)
    sources = html.escape(sources_str)
    category_cap = html.escape(category_raw.capitalize())

    priority_raw = post.get("priority")
    is_followup = post.get("is_followup", False)
    sources_count = len(post.get("sources_list", [])) if post.get("sources_list") else (1 if post.get("source") else 0)

    footer_parts = [
        f"🏷️ <b>Category:</b> {category_cap}",
        f"🕒 <b>Published:</b> {time_str}",
        f"📰 <b>Source:</b> {sources}"
    ]

    intel_badge = []
    if priority_raw == "BREAKING" or is_breaking:
        intel_badge.append("⚡ <b>Priority:</b> 🚨 BREAKING (Fast-Tracked)")
    elif priority_raw == "HIGH":
        intel_badge.append("⚡ <b>Priority:</b> 🔥 HIGH")
        
    if is_followup:
        intel_badge.append("🔄 <b>Story State:</b> 📢 DEVELOPING UPDATE")
    elif sources_count >= 2:
        intel_badge.append(f"👥 <b>Confirmation:</b> {sources_count} Independent Sources")

    if intel_badge:
        footer_parts.append("\n" + "\n".join(intel_badge))

    if url:
        safe_url = html.escape(url, quote=True)
        footer_parts.append(f"\n🔗 <a href=\"{safe_url}\">Read full story</a>")
        
    footer_text = "\n".join(footer_parts)

    overhead = len(header) + len(title) + len(footer_text) + 150
    available_for_body = max(100, max_length - overhead)

    if len(summary_raw) > available_for_body:
        summary_raw = summary_raw[:available_for_body - 3].rstrip() + "..."

    summary = html.escape(summary_raw)
    
    parts = [header, ""]
    if title:
        parts.append(f"<b>{title}</b>\n")
    if summary:
        parts.append(f"{summary}\n")
    if why_it_matters_raw:
        why_it_matters = html.escape(why_it_matters_raw)
        parts.append(f"📌 <b>Why it matters:</b>\n{why_it_matters}\n")
        
    parts.append(footer_text)
    full_html = "\n".join(parts)

    if len(full_html) > max_length and why_it_matters_raw:
        # Fallback to omitting why_it_matters if caption budget is still exceeded
        parts = [header, "", f"<b>{title}</b>\n", f"{summary}\n", footer_text]
        full_html = "\n".join(parts)
        
    return full_html


async def _publish_post_async(post: dict) -> bool:
    """
    Publishes a post dictionary, attempting photo publishing first if real article image exists,
    with automatic fallback to text-only Telegram post if no image exists or photo publish fails.
    """
    bot = _build_bot()
    image_url = post.get("image_url") or post.get("image", "")

    is_image_valid = False
    if image_url and is_valid_url(image_url):
        is_image_valid = validate_image_url(image_url, timeout=3.0)

    # 1. Attempt Photo Post if real article image is present and valid
    if is_image_valid and image_url:
        caption_html = format_html_post(post, max_length=1024)
        try:
            logger.info("[TELEGRAM] Attempting photo publish (Image: %s)", image_url[:60])
            await bot.send_photo(
                chat_id=config.TELEGRAM_CHANNEL_ID,
                photo=image_url,
                caption=caption_html,
                parse_mode="HTML"
            )
            return True
        except Exception as img_err:
            logger.warning("[TELEGRAM] Photo publish failed (%s). Falling back to text-only.", img_err)

    # 2. Text-only Post HTML
    formatted_html = format_html_post(post, max_length=4096)
    try:
        await bot.send_message(
            chat_id=config.TELEGRAM_CHANNEL_ID,
            text=formatted_html,
            parse_mode="HTML",
            disable_web_page_preview=False
        )
        return True
    except BadRequest as e:
        logger.warning("[TELEGRAM] HTML parse failed (%s). Retrying plain text.", e)
        try:
            plain_text = re.sub(r"<[^>]+>", "", formatted_html)
            await bot.send_message(
                chat_id=config.TELEGRAM_CHANNEL_ID,
                text=plain_text[:4096]
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
    Automatically records post to persistent published history on success to prevent duplicate posts.
    """
    try:
        config.validate_config()
    except ValueError as e:
        logger.error("Publish failed: %s", e)
        return False

    success = asyncio.run(_publish_post_async(post))
    if success and isinstance(post, dict):
        try:
            import deduplicator
            deduplicator.record_published_history([post])
        except Exception as err:
            logger.error("Failed to record published history: %s", err)
    return success



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

