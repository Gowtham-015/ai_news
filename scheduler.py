"""
scheduler.py
------------
PHASE 2 & PHASE 4 of the AI News Automation Agent.

This is the scheduler module. Running this or main.py --daemon keeps the
system running in the background and automatically publishes posts from
posts.json to your Telegram channel when their scheduled_time arrives.

Updates in Phase 4:
- Rotates log files safely (RotatingFileHandler max 5MB, 3 backups)
- Records published history to data/published_news.json only AFTER Telegram confirms successful delivery.
- Preserves APScheduler BlockingScheduler functionality without replacing it.
"""

import json
import logging
from logging.handlers import RotatingFileHandler
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from apscheduler.schedulers.blocking import BlockingScheduler

import publisher
import deduplicator

TIMEZONE = ZoneInfo("Asia/Kolkata")
POSTS_FILE = Path(__file__).parent / "posts.json"
DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"
CHECK_INTERVAL_SECONDS = 30

CATEGORY_EMOJIS = {
    "NEWS": "📰",
    "TECHNOLOGY": "💻",
    "SPORTS": "🏏",
    "ENTERTAINMENT": "🎬",
}

# Rotating file handler (5MB max size per log file, 3 backups)
log_file_path = Path(__file__).parent / "scheduler.log"
rotating_handler = RotatingFileHandler(
    log_file_path, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
)
rotating_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))

stream_handler = logging.StreamHandler()
stream_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))

logger = logging.getLogger("scheduler")
logger.setLevel(logging.INFO)
if not logger.handlers:
    logger.addHandler(stream_handler)
    logger.addHandler(rotating_handler)


def load_posts():
    """Reads posts.json and returns the list of posts."""
    if not POSTS_FILE.exists():
        logger.error("posts.json not found at %s.", POSTS_FILE)
        return []

    try:
        with open(POSTS_FILE, "r", encoding="utf-8") as f:
            posts = json.load(f)
    except json.JSONDecodeError as e:
        logger.error("posts.json contains invalid JSON (%s).", e)
        return []

    if not isinstance(posts, list):
        logger.error("posts.json must contain a JSON list/array of posts.")
        return []

    return posts


def save_posts(posts):
    """Saves the posts list back to posts.json atomically."""
    tmp_fd, tmp_path = tempfile.mkstemp(
        dir=POSTS_FILE.parent, prefix="posts_", suffix=".tmp"
    )
    try:
        with open(tmp_fd, "w", encoding="utf-8") as f:
            json.dump(posts, f, indent=2, ensure_ascii=False)
        shutil.move(tmp_path, POSTS_FILE)
    except Exception:
        Path(tmp_path).unlink(missing_ok=True)
        raise


def format_post_message(post):
    """Turns a post entry from posts.json into Telegram text."""
    category = str(post.get("category", "")).upper()
    emoji = CATEGORY_EMOJIS.get(category, "📌")
    title = post.get("title", "(untitled)")
    content = post.get("content", "")
    return f"{emoji} {category}\n\n{title}\n\n{content}"


def parse_scheduled_time(post):
    """Parses scheduled_time into timezone-aware datetime in Asia/Kolkata."""
    raw = post.get("scheduled_time")
    if not raw:
        raise ValueError("missing scheduled_time")

    naive_dt = datetime.strptime(raw, DATETIME_FORMAT)
    return naive_dt.replace(tzinfo=TIMEZONE)


def check_and_publish():
    """
    Checks due posts in posts.json and publishes them via publisher.py.
    Records to published_news.json only upon confirmed Telegram success.
    """
    posts = load_posts()
    if not posts:
        return

    now = datetime.now(TIMEZONE)
    changed = False

    for post in posts:
        post_id = post.get("id", "?")

        if post.get("status") != "scheduled":
            continue

        try:
            scheduled_dt = parse_scheduled_time(post)
        except ValueError as e:
            logger.error("Skipping post %s: invalid scheduled_time (%s).", post_id, e)
            continue

        if scheduled_dt > now:
            continue

        logger.info("Publishing post %s", post_id)
        text = format_post_message(post)
        success = publisher.publish_text(text)

        if success:
            post["status"] = "published"
            post["published_time"] = now.strftime(DATETIME_FORMAT)
            changed = True
            logger.info("Post %s published successfully", post_id)

            # PART 25: Record to persistent published history only after success
            try:
                deduplicator.record_published_history([post])
            except Exception as e:
                logger.error("Failed to record published history for post %s: %s", post_id, e)
        else:
            logger.error("Failed to publish post %s. Will retry on next cycle.", post_id)

    if changed:
        try:
            save_posts(posts)
        except Exception as e:
            logger.error("Failed to save posts.json after publishing: %s", e)


def main():
    logger.info("Scheduler started")
    logger.info(
        "Checking posts.json every %s seconds (timezone: Asia/Kolkata)",
        CHECK_INTERVAL_SECONDS,
    )

    scheduler = BlockingScheduler(timezone=TIMEZONE)
    scheduler.add_job(
        check_and_publish,
        "interval",
        seconds=CHECK_INTERVAL_SECONDS,
        id="check_and_publish",
        next_run_time=datetime.now(TIMEZONE),
    )

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped by user")


if __name__ == "__main__":
    main()
