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
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from apscheduler.schedulers.blocking import BlockingScheduler

import config
import publisher
import deduplicator


TIMEZONE = ZoneInfo("Asia/Kolkata")
POSTS_FILE = getattr(config, "POSTS_FILE", Path(__file__).parent / "data" / "posts.json")

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


def check_post_frequency_limits(post: dict, published_history: list = None) -> tuple[bool, str]:
    """
    Enforces Phase 7 post frequency controls using Asia/Kolkata timezone:
    1. MAX_POSTS_PER_HOUR (4)
    2. MAX_POSTS_PER_DAY (30)
    3. MIN_POST_INTERVAL_MINUTES (15)
    4. MAX_POSTS_PER_CATEGORY_PER_DAY (10)
    
    Breaking news override: Bypasses frequency limits if is_breaking or priority == 'BREAKING'.
    """
    is_breaking = post.get("is_breaking") or post.get("priority") == "BREAKING"
    if is_breaking:
        return True, "Breaking news override active"

    if published_history is None:
        published_history = deduplicator.load_published_history()

    now = datetime.now(TIMEZONE)
    hour_ago = now - timedelta(hours=1)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    min_interval = timedelta(minutes=getattr(config, "MIN_POST_INTERVAL_MINUTES", 15))

    posts_last_hour = 0
    posts_today = 0
    cat_posts_today = 0
    post_category = str(post.get("category", "")).upper()
    latest_published_dt = None

    for item in published_history:
        pub_str = item.get("published_time") or item.get("published_at")
        if not pub_str:
            continue
        try:
            from news_collector import parse_published_time
            dt = parse_published_time(str(pub_str)).astimezone(TIMEZONE)
        except Exception:
            continue

        if latest_published_dt is None or dt > latest_published_dt:
            latest_published_dt = dt

        if dt >= hour_ago:
            posts_last_hour += 1

        if dt >= day_start:
            posts_today += 1
            item_cat = str(item.get("category", "")).upper()
            if item_cat == post_category:
                cat_posts_today += 1

    max_per_hour = getattr(config, "MAX_POSTS_PER_HOUR", 4)
    if posts_last_hour >= max_per_hour:
        return False, f"Hourly limit reached ({posts_last_hour}/{max_per_hour} posts in last hour)"

    max_per_day = getattr(config, "MAX_POSTS_PER_DAY", 30)
    if posts_today >= max_per_day:
        return False, f"Daily limit reached ({posts_today}/{max_per_day} posts today)"

    if latest_published_dt and (now - latest_published_dt) < min_interval:
        elapsed = (now - latest_published_dt).total_seconds() / 60.0
        return False, f"Minimum interval not met ({elapsed:.1f} mins since last post, required {min_interval.total_seconds()/60:.0f} mins)"

    max_cat_day = getattr(config, "MAX_POSTS_PER_CATEGORY_PER_DAY", 10)
    if cat_posts_today >= max_cat_day:
        return False, f"Category daily limit reached ({cat_posts_today}/{max_cat_day} posts for {post_category} today)"

    return True, "Frequency limits passed"


def check_and_trigger_channel_rhythm(now: datetime, automation_mgr=None, admin_mgr=None):
    """
    Executes Phase 12 channel publication rhythm automatically:
    - Morning Briefing (🌅 GOOD MORNING)
    - Evening Roundup (🌙 TODAY'S TOP STORIES)
    - Trending Digest (🔥 TRENDING NOW)
    Respects admin pause controls, IST timezone dates, and records Phase 10 telemetry.
    Isolated in try...except so rhythm errors never affect core news processing.
    """
    try:
        from channel_automation import ChannelAutomationManager
        from admin_control import AdminControlManager
        from analytics_manager import AnalyticsManager, get_ist_date_str

        cam = automation_mgr or ChannelAutomationManager()
        acm = admin_mgr or AdminControlManager()
        am = AnalyticsManager()

        if acm.is_publishing_paused():
            logger.info("[AUTOMATION] Publishing is paused globally. Skipping rhythm checks.")
            return

        date_str = get_ist_date_str(now)

        # 1. Automatic Morning Briefing
        if cam.should_trigger_morning_briefing(dt=now):
            try:
                top_stories = am.get_top_stories("today")
                payload = cam.generate_morning_briefing(top_stories)
                logger.info("[AUTOMATION] Triggering automatic Morning Briefing for date %s", date_str)
                if publisher.publish_post(payload):
                    state = cam.load_state()
                    state["last_morning_briefing_date"] = date_str
                    cam.save_state(state)
                    am.record_publishing_event("success", post=payload, priority="HIGH")
            except Exception as mb_err:
                logger.warning("[AUTOMATION] Morning briefing trigger failed: %s", mb_err)

        # 2. Automatic Evening Roundup
        if cam.should_trigger_evening_roundup(dt=now):
            try:
                top_stories = am.get_top_stories("today")
                report_text = am.generate_daily_report()
                cat_stats = {}
                for line in report_text.splitlines():
                    if "• " in line and ":" in line:
                        parts = line.split("• ")[1].split(":")
                        if len(parts) == 2:
                            c_name = parts[0].strip().lower()
                            try:
                                c_cnt = int(parts[1].split()[0])
                                cat_stats[c_name] = c_cnt
                            except Exception:
                                pass
                payload = cam.generate_evening_roundup(top_stories, cat_stats=cat_stats)
                logger.info("[AUTOMATION] Triggering automatic Evening Roundup for date %s", date_str)
                if publisher.publish_post(payload):
                    state = cam.load_state()
                    state["last_evening_roundup_date"] = date_str
                    cam.save_state(state)
                    am.record_publishing_event("success", post=payload, priority="HIGH")
            except Exception as er_err:
                logger.warning("[AUTOMATION] Evening roundup trigger failed: %s", er_err)

        # 3. Automatic Trending Digest
        if cam.should_trigger_trending_digest(dt=now):
            try:
                top_stories = am.get_top_stories("today")
                if top_stories:
                    payload = cam.generate_trending_digest(top_stories)
                    logger.info("[AUTOMATION] Triggering automatic Trending Digest")
                    if publisher.publish_post(payload):
                        state = cam.load_state()
                        state["last_trending_digest_at"] = now.isoformat()
                        cam.save_state(state)
                        am.record_publishing_event("success", post=payload, priority="HIGH")
            except Exception as td_err:
                logger.warning("[AUTOMATION] Trending digest trigger failed: %s", td_err)

    except Exception as e:
        logger.warning("[AUTOMATION] Rhythm check execution failed: %s", e)


def check_and_publish():
    """
    Checks due posts in posts.json and publishes them via publisher.py.
    Enforces frequency limits, admin pause controls, and safe retry state transitions:
    scheduled -> publishing -> retrying -> published / permanently_failed
    Records to published_news.json only upon confirmed Telegram success.
    """
    try:
        from admin_control import AdminControlManager
        acm = AdminControlManager()
        acm.poll_and_process_commands()
    except Exception as e:
        logger.warning("Failed to poll admin control commands: %s", e)

    now = datetime.now(TIMEZONE)

    # Phase 16 Production Monitoring & Self-Healing check
    try:
        from health_monitor import HealthMonitor
        HealthMonitor().auto_heal()
    except Exception as h_err:
        logger.warning("[HEALTH] Health auto-heal failed: %s", h_err)

    # Automatic Phase 12 channel publication rhythm check
    check_and_trigger_channel_rhythm(now)

    posts = load_posts()
    if not posts:
        return
    published_history = deduplicator.load_published_history()
    max_retries = getattr(config, "MAX_RETRIES", 3)

    for post in posts:
        post_id = post.get("id", "?")
        status = post.get("status")

        if status not in ("scheduled", "retrying"):
            continue

        try:
            scheduled_dt = parse_scheduled_time(post)
        except ValueError as e:
            logger.error("Skipping post %s: invalid scheduled_time (%s).", post_id, e)
            continue

        if scheduled_dt > now:
            continue

        # Check admin pause control (global or category-level)
        post_category = post.get("category", "NEWS")
        try:
            from admin_control import AdminControlManager
            acm = AdminControlManager()
            if acm.is_publishing_paused(post_category):
                logger.info("[PAUSED] Delaying post %s: Publishing is currently paused for category %s", post_id, post_category)
                continue
        except Exception:
            pass

        # Check duplicate publishing prevention against published history
        post_url = post.get("original_url") or post.get("url", "")
        if post_url and deduplicator.is_duplicate_url(post_url, published_history):
            logger.warning("[SAFETY] Post %s URL already exists in published history (%s). Marking published.", post_id, post_url)
            post["status"] = "published"
            save_posts(posts)
            continue

        # Enforce post frequency limits (hourly, daily, min interval, category daily)
        freq_ok, freq_reason = check_post_frequency_limits(post, published_history=published_history)
        if not freq_ok:
            logger.info("[FREQUENCY] Delaying post %s: %s", post_id, freq_reason)
            continue

        # Attach Phase 13 engagement opinion prompt if non-sensitive and within limits
        try:
            from engagement_engine import EngagementEngine
            ee = EngagementEngine()
            post = ee.attach_opinion_prompt(post, dt=now)
        except Exception as eng_err:
            logger.warning("[ENGAGEMENT] Failed to attach opinion prompt: %s", eng_err)

        # Transition to publishing state
        post["status"] = "publishing"
        save_posts(posts)

        logger.info("[TELEGRAM] Publishing post %s (Priority: %s)", post_id, post.get("priority", "NORMAL"))
        if hasattr(publisher, "publish_post") and isinstance(post, dict):
            success = publisher.publish_post(post)
        else:
            text = format_post_message(post)
            success = publisher.publish_text(text)

        if success:
            post["status"] = "published"
            post["published_time"] = now.strftime(DATETIME_FORMAT)
            save_posts(posts)
            logger.info("Post %s published successfully", post_id)

            # Check breaking news auto-pinning if enabled
            is_breaking = post.get("is_breaking") or str(post.get("priority", "")).upper() == "BREAKING"
            msg_id = post.get("telegram_message_id")
            if is_breaking and msg_id:
                try:
                    from channel_automation import ChannelAutomationManager
                    cam = ChannelAutomationManager()
                    astate = cam.load_state()
                    if astate.get("pinning_enabled", True):
                        logger.info("[TELEGRAM] Pinning breaking news post %s (Msg ID: %s)", post_id, msg_id)
                        publisher.pin_message(msg_id)
                except Exception as pin_err:
                    logger.warning("[TELEGRAM] Failed to pin breaking post: %s", pin_err)

            # Check Phase 13 interactive prediction poll generation
            try:
                from engagement_engine import EngagementEngine
                ee = EngagementEngine()
                poll_payload = ee.generate_prediction_poll(post, dt=now)
                if poll_payload:
                    q, opts = poll_payload
                    logger.info("[ENGAGEMENT] Creating interactive prediction poll: '%s'", q)
                    if publisher.publish_poll(q, opts):
                        try:
                            from analytics_manager import AnalyticsManager
                            AnalyticsManager().record_publishing_event("success", post={"title": q}, priority="NORMAL")
                        except Exception:
                            pass
            except Exception as poll_err:
                logger.warning("[ENGAGEMENT] Failed to generate/publish poll: %s", poll_err)

            # Record to persistent published history immediately after confirmed Telegram success
            try:
                deduplicator.record_published_history([post])
                published_history.append(post)
            except Exception as e:
                logger.error("Failed to record published history for post %s: %s", post_id, e)

            # Record Phase 10 Analytics
            try:
                from analytics_manager import AnalyticsManager
                am = AnalyticsManager()
                am.record_publishing_event("success", post=post, priority=post.get("priority", "NORMAL"), is_photo=bool(post.get("image_url")))
            except Exception as e:
                logger.warning("Failed to record publishing analytics: %s", e)
        else:
            retry_count = post.get("retry_count", 0) + 1
            post["retry_count"] = retry_count
            post["failed_time"] = now.strftime(DATETIME_FORMAT)

            try:
                from analytics_manager import AnalyticsManager
                am = AnalyticsManager()
                am.record_publishing_event("failure", post=post, priority=post.get("priority", "NORMAL"))
                if retry_count < max_retries:
                    post["status"] = "retrying"
                    logger.warning("Failed to publish post %s (Attempt %d/%d). Status set to 'retrying'.", post_id, retry_count, max_retries)
                    am.record_publishing_event("retry", post=post, priority=post.get("priority", "NORMAL"))
                else:
                    post["status"] = "permanently_failed"
                    logger.error("Post %s permanently failed after %d attempts.", post_id, retry_count)
                    am.record_publishing_event("permanently_failed", post=post, priority=post.get("priority", "NORMAL"))
                    am.record_failure("TELEGRAM_ERROR", f"Post {post_id} permanently failed after {max_retries} retries", details={"post_id": post_id, "title": post.get("title")})
            except Exception as e:
                logger.warning("Failed to record failure analytics: %s", e)

            save_posts(posts)

    try:
        from storage_manager import StorageManager
        StorageManager().prune_all_storage()
    except Exception as s_err:
        logger.warning("[STORAGE] Storage pruning error: %s", s_err)


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
