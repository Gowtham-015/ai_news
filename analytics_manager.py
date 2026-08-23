"""
analytics_manager.py
--------------------
PHASE 10 of the AI News Automation Agent.

Responsible for:
1. Persisting daily and weekly performance, category, source, duplicate, AI usage,
   Telegram publishing, priority distribution, story lifecycle, failure, and duration metrics.
2. Enforcing IST (Asia/Kolkata) date boundaries for all daily (YYYY-MM-DD) and weekly (YYYY-W%V) reports.
3. Providing human-readable daily & weekly report generators.
4. Tracking top stories by score and priority.
5. Atomic, crash-safe file persistence under data/analytics/.
6. Automatic retention cleanup for metrics older than ANALYTICS_RETENTION_DAYS (default 90 days).
"""

import json
import logging
import shutil
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from typing import Dict, List, Optional, Tuple, Any

import config

logger = logging.getLogger("analytics_manager")
if not logger.handlers:
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    logger.addHandler(handler)

IST = ZoneInfo("Asia/Kolkata")
DATA_DIR = getattr(config, "DATA_DIR_PATH", Path(__file__).parent / "data")
ANALYTICS_DIR = getattr(config, "ANALYTICS_DIR", DATA_DIR / "analytics")

DAILY_FILE = ANALYTICS_DIR / "daily.json"
WEEKLY_FILE = ANALYTICS_DIR / "weekly.json"
TOP_STORIES_FILE = ANALYTICS_DIR / "top_stories.json"
FAILURES_FILE = ANALYTICS_DIR / "failures.json"


def get_ist_now() -> datetime:
    """Returns current datetime in Asia/Kolkata timezone."""
    return datetime.now(IST)


def get_ist_date_str(dt: Optional[datetime] = None) -> str:
    """Returns YYYY-MM-DD date string in Asia/Kolkata timezone."""
    if dt is None:
        dt = get_ist_now()
    elif dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc).astimezone(IST)
    else:
        dt = dt.astimezone(IST)
    return dt.strftime("%Y-%m-%d")


def get_ist_week_str(dt: Optional[datetime] = None) -> str:
    """Returns YYYY-W%V ISO week string in Asia/Kolkata timezone."""
    if dt is None:
        dt = get_ist_now()
    elif dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc).astimezone(IST)
    else:
        dt = dt.astimezone(IST)
    return dt.strftime("%Y-W%V")


def _ensure_dir(dir_path: Path):
    """Ensures analytics directory exists safely."""
    try:
        dir_path.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        logger.error("Failed to create analytics directory %s: %s", dir_path, e)


def _load_json_file(file_path: Path, default_factory=dict) -> Any:
    """Loads JSON file safely, returning default_factory() on missing or corrupt files."""
    if not file_path.exists():
        return default_factory()
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, type(default_factory())):
                return data
    except Exception as e:
        logger.warning("Corrupted or unreadable analytics file (%s). Resetting: %s", file_path, e)
    return default_factory()


def _save_json_file(file_path: Path, data: Any):
    """Saves data to JSON file atomically."""
    _ensure_dir(file_path.parent)
    tmp_fd, tmp_path = tempfile.mkstemp(dir=file_path.parent, prefix="analytics_", suffix=".tmp")
    try:
        with open(tmp_fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        shutil.move(tmp_path, file_path)
    except Exception as e:
        Path(tmp_path).unlink(missing_ok=True)
        logger.error("Failed to save analytics file %s: %s", file_path, e)


def _create_default_daily_entry(date_str: str) -> dict:
    """Returns default metrics structure for a single IST day."""
    return {
        "date": date_str,
        "articles_collected": 0,
        "articles_rejected": 0,
        "duplicates_removed": 0,
        "unique_articles": 0,
        "stories_clustered": 0,
        "stories_ranked": 0,
        "ai_processed": 0,
        "ai_successful": 0,
        "ai_failed": 0,
        "ai_retries": 0,
        "ai_filtered_before": 0,
        "posts_generated": 0,
        "posts_scheduled": 0,
        "posts_published": 0,
        "posts_failed": 0,
        "post_retries": 0,
        "permanently_failed": 0,
        "photo_posts": 0,
        "text_only_posts": 0,
        "markup_fallbacks": 0,
        "breaking_posts": 0,
        "high_priority_posts": 0,
        "normal_priority_posts": 0,
        "low_priority_posts": 0,
        "lifecycle_new": 0,
        "lifecycle_developing": 0,
        "lifecycle_trending": 0,
        "lifecycle_resolved": 0,
        "meaningful_followups": 0,
        "rejected_followups": 0,
        "queue_size_end": 0,
        "peak_queue_size": 0,
        "last_successful_collection": None,
        "last_successful_publication": None,
        "durations_seconds": {
            "collection": 0.0,
            "deduplication": 0.0,
            "clustering": 0.0,
            "ai": 0.0,
            "ranking": 0.0,
            "queue": 0.0,
            "publishing": 0.0,
            "total_pipeline": 0.0
        },
        "category_stats": {
            "NEWS": {"collected": 0, "rejected": 0, "published": 0, "failed": 0, "breaking": 0, "high": 0, "normal": 0, "low": 0},
            "TECHNOLOGY": {"collected": 0, "rejected": 0, "published": 0, "failed": 0, "breaking": 0, "high": 0, "normal": 0, "low": 0},
            "SPORTS": {"collected": 0, "rejected": 0, "published": 0, "failed": 0, "breaking": 0, "high": 0, "normal": 0, "low": 0},
            "ENTERTAINMENT": {"collected": 0, "rejected": 0, "published": 0, "failed": 0, "breaking": 0, "high": 0, "normal": 0, "low": 0}
        },
        "source_stats": {}
    }


class AnalyticsManager:
    def __init__(self, analytics_dir: Path = ANALYTICS_DIR):
        self.analytics_dir = analytics_dir
        self.daily_file = analytics_dir / "daily.json"
        self.weekly_file = analytics_dir / "weekly.json"
        self.top_stories_file = analytics_dir / "top_stories.json"
        self.failures_file = analytics_dir / "failures.json"
        _ensure_dir(self.analytics_dir)

    def record_pipeline_run(self, metrics: dict):
        """
        Records pipeline metrics (collection, deduplication, clustering, ranking, AI, queueing).
        Wrapped in crash-safe try...except so analytics errors never disrupt main execution.
        """
        if not getattr(config, "ANALYTICS_ENABLED", True):
            return

        try:
            now_ist = get_ist_now()
            date_str = get_ist_date_str(now_ist)
            week_str = get_ist_week_str(now_ist)

            daily_data = _load_json_file(self.daily_file, dict)
            day_entry = daily_data.get(date_str, _create_default_daily_entry(date_str))

            # Update scalar metrics
            day_entry["articles_collected"] += metrics.get("collected_count", 0)
            day_entry["articles_rejected"] += metrics.get("rejected_count", 0)
            day_entry["duplicates_removed"] += metrics.get("duplicates_count", 0)
            day_entry["unique_articles"] += metrics.get("unique_count", 0)
            day_entry["stories_clustered"] += metrics.get("clusters_count", 0)
            day_entry["stories_ranked"] += metrics.get("ranked_count", 0)
            day_entry["ai_processed"] += metrics.get("ai_processed_count", 0)
            day_entry["ai_successful"] += metrics.get("ai_successful_count", 0)
            day_entry["ai_failed"] += metrics.get("ai_failed_count", 0)
            day_entry["ai_filtered_before"] += metrics.get("ai_filtered_before_count", 0)
            day_entry["posts_generated"] += metrics.get("posts_generated_count", 0)
            day_entry["posts_scheduled"] += metrics.get("posts_scheduled_count", 0)
            
            queue_size = metrics.get("queue_size", 0)
            day_entry["queue_size_end"] = queue_size
            day_entry["peak_queue_size"] = max(day_entry.get("peak_queue_size", 0), queue_size)

            if metrics.get("collected_count", 0) > 0:
                day_entry["last_successful_collection"] = now_ist.strftime("%Y-%m-%d %H:%M:%S")

            # Update lifecycle stats
            day_entry["lifecycle_new"] += metrics.get("lifecycle_new", 0)
            day_entry["lifecycle_developing"] += metrics.get("lifecycle_developing", 0)
            day_entry["lifecycle_trending"] += metrics.get("lifecycle_trending", 0)
            day_entry["lifecycle_resolved"] += metrics.get("lifecycle_resolved", 0)
            day_entry["meaningful_followups"] += metrics.get("meaningful_followups", 0)
            day_entry["rejected_followups"] += metrics.get("rejected_followups", 0)

            # Update durations
            durations = metrics.get("durations", {})
            for k in day_entry["durations_seconds"]:
                if k in durations:
                    day_entry["durations_seconds"][k] += round(durations[k], 2)

            # Update category stats
            cat_metrics = metrics.get("category_collected", {})
            for cat, count in cat_metrics.items():
                cat_key = cat.upper()
                if cat_key in day_entry["category_stats"]:
                    day_entry["category_stats"][cat_key]["collected"] += count

            # Update source stats
            src_metrics = metrics.get("source_collected", {})
            for src, count in src_metrics.items():
                if src not in day_entry["source_stats"]:
                    day_entry["source_stats"][src] = {"collected": 0, "accepted": 0, "published": 0}
                day_entry["source_stats"][src]["collected"] += count

            src_accepted = metrics.get("source_accepted", {})
            for src, count in src_accepted.items():
                if src not in day_entry["source_stats"]:
                    day_entry["source_stats"][src] = {"collected": 0, "accepted": 0, "published": 0}
                day_entry["source_stats"][src]["accepted"] += count

            daily_data[date_str] = day_entry
            _save_json_file(self.daily_file, daily_data)

            # Record top stories if provided
            top_candidates = metrics.get("top_candidates", [])
            if top_candidates:
                self.record_top_stories(top_candidates, date_str, week_str)

            self._aggregate_weekly(date_str, week_str)
            self.cleanup_old_analytics()
        except Exception as e:
            logger.warning("Analytics failure in record_pipeline_run: %s", e)

    def record_publishing_event(
        self,
        event_type: str,
        post: dict = None,
        priority: str = "NORMAL",
        is_photo: bool = False,
        is_fallback: bool = False
    ):
        """
        Records Telegram publishing events (attempt, success, failure, retry, permanently_failed).
        Crash-safe try...except wrapper.
        """
        if not getattr(config, "ANALYTICS_ENABLED", True):
            return

        try:
            now_ist = get_ist_now()
            date_str = get_ist_date_str(now_ist)
            week_str = get_ist_week_str(now_ist)

            daily_data = _load_json_file(self.daily_file, dict)
            day_entry = daily_data.get(date_str, _create_default_daily_entry(date_str))

            prio = (priority or "NORMAL").upper()
            cat = (post.get("category") or "NEWS").upper() if post else "NEWS"

            if event_type == "success":
                day_entry["posts_published"] += 1
                day_entry["last_successful_publication"] = now_ist.strftime("%Y-%m-%d %H:%M:%S")

                if is_photo:
                    day_entry["photo_posts"] += 1
                else:
                    day_entry["text_only_posts"] += 1

                if is_fallback:
                    day_entry["markup_fallbacks"] += 1

                if prio == "BREAKING" or (post and post.get("is_breaking")):
                    day_entry["breaking_posts"] += 1
                elif prio == "HIGH":
                    day_entry["high_priority_posts"] += 1
                elif prio == "LOW":
                    day_entry["low_priority_posts"] += 1
                else:
                    day_entry["normal_priority_posts"] += 1

                if cat in day_entry["category_stats"]:
                    day_entry["category_stats"][cat]["published"] += 1
                    if prio == "BREAKING" or (post and post.get("is_breaking")):
                        day_entry["category_stats"][cat]["breaking"] += 1
                    elif prio == "HIGH":
                        day_entry["category_stats"][cat]["high"] += 1
                    elif prio == "LOW":
                        day_entry["category_stats"][cat]["low"] += 1
                    else:
                        day_entry["category_stats"][cat]["normal"] += 1

                source = post.get("source") if post else None
                if source and source in day_entry["source_stats"]:
                    day_entry["source_stats"][source]["published"] += 1

            elif event_type == "retry":
                day_entry["post_retries"] += 1
            elif event_type == "failure":
                day_entry["posts_failed"] += 1
                if cat in day_entry["category_stats"]:
                    day_entry["category_stats"][cat]["failed"] += 1
            elif event_type == "permanently_failed":
                day_entry["permanently_failed"] += 1

            daily_data[date_str] = day_entry
            _save_json_file(self.daily_file, daily_data)
            self._aggregate_weekly(date_str, week_str)
        except Exception as e:
            logger.warning("Analytics failure in record_publishing_event: %s", e)

    def record_failure(self, category: str, error_msg: str, details: dict = None):
        """Records categorized failure events (COLLECTION_ERROR, AI_ERROR, TELEGRAM_ERROR, IMAGE_ERROR, QUEUE_ERROR, FORMAT_ERROR, OTHER)."""
        if not getattr(config, "ANALYTICS_ENABLED", True):
            return

        try:
            valid_cats = {"COLLECTION_ERROR", "AI_ERROR", "TELEGRAM_ERROR", "IMAGE_ERROR", "QUEUE_ERROR", "FORMAT_ERROR", "OTHER"}
            cat_key = category.upper() if category.upper() in valid_cats else "OTHER"

            failures_data = _load_json_file(self.failures_file, dict)
            if cat_key not in failures_data:
                failures_data[cat_key] = []

            failures_data[cat_key].append({
                "timestamp": get_ist_now().strftime("%Y-%m-%d %H:%M:%S IST"),
                "error": error_msg[:300],
                "details": details or {}
            })

            # Keep last 50 failure logs per category
            failures_data[cat_key] = failures_data[cat_key][-50:]
            _save_json_file(self.failures_file, failures_data)
        except Exception as e:
            logger.warning("Analytics failure in record_failure: %s", e)

    def record_top_stories(self, stories: list[dict], date_str: str, week_str: str):
        """Stores top stories metadata by date and week, accumulating top scoring stories across runs."""
        try:
            data = _load_json_file(self.top_stories_file, dict)
            existing_list = data.get(date_str, [])
            
            new_items = []
            for s in stories[:10]:
                title = s.get("title") or s.get("topic", "")
                if not title:
                    continue
                new_items.append({
                    "title": title,
                    "category": s.get("category", "NEWS"),
                    "priority": s.get("priority", "NORMAL"),
                    "score": s.get("final_score", 0),
                    "source_count": s.get("source_count", 1),
                    "published_at": s.get("published_at", "")
                })

            # Merge existing and new items, avoiding duplicate titles and retaining top scores
            combined = {item["title"]: item for item in existing_list}
            for item in new_items:
                if item["title"] not in combined or item["score"] > combined[item["title"]]["score"]:
                    combined[item["title"]] = item

            sorted_top = sorted(list(combined.values()), key=lambda x: x.get("score", 0), reverse=True)[:10]
            data[date_str] = sorted_top
            _save_json_file(self.top_stories_file, data)
        except Exception as e:
            logger.warning("Analytics failure in record_top_stories: %s", e)

    def _aggregate_weekly(self, date_str: str, week_str: str):
        """Aggregates daily entries into weekly metrics."""
        try:
            daily_data = _load_json_file(self.daily_file, dict)
            weekly_data = _load_json_file(self.weekly_file, dict)

            # Find all dates in the same ISO week
            week_days = [
                d for d, v in daily_data.items()
                if get_ist_week_str(datetime.strptime(d, "%Y-%m-%d").replace(tzinfo=IST)) == week_str
            ]

            if not week_days:
                return

            week_entry = {
                "week": week_str,
                "days_count": len(week_days),
                "total_posts_published": sum(daily_data[d].get("posts_published", 0) for d in week_days),
                "total_articles_collected": sum(daily_data[d].get("articles_collected", 0) for d in week_days),
                "total_duplicates_removed": sum(daily_data[d].get("duplicates_removed", 0) for d in week_days),
                "total_ai_processed": sum(daily_data[d].get("ai_processed", 0) for d in week_days),
                "total_breaking_posts": sum(daily_data[d].get("breaking_posts", 0) for d in week_days),
                "total_failed_posts": sum(daily_data[d].get("posts_failed", 0) for d in week_days),
                "total_retries": sum(daily_data[d].get("post_retries", 0) for d in week_days),
                "avg_posts_per_day": round(sum(daily_data[d].get("posts_published", 0) for d in week_days) / max(1, len(week_days)), 1),
                "category_totals": {"NEWS": 0, "TECHNOLOGY": 0, "SPORTS": 0, "ENTERTAINMENT": 0}
            }

            for d in week_days:
                cat_stats = daily_data[d].get("category_stats", {})
                for cat in week_entry["category_totals"]:
                    week_entry["category_totals"][cat] += cat_stats.get(cat, {}).get("published", 0)

            weekly_data[week_str] = week_entry
            _save_json_file(self.weekly_file, weekly_data)
        except Exception as e:
            logger.warning("Analytics failure in _aggregate_weekly: %s", e)

    def generate_daily_report(self, date_str: str = None) -> str:
        """Generates a human-readable daily analytics report string for the given IST date."""
        try:
            if not date_str:
                date_str = get_ist_date_str()

            daily_data = _load_json_file(self.daily_file, dict)
            day = daily_data.get(date_str, _create_default_daily_entry(date_str))

            cat_stats = day.get("category_stats", {})
            durations = day.get("durations_seconds", {})

            report_lines = [
                "📊 DAILY NEWS REPORT",
                f"Date: {date_str} (IST)\n",
                "📰 NEWS",
                f"Collected: {cat_stats.get('NEWS', {}).get('collected', 0)} | Published: {cat_stats.get('NEWS', {}).get('published', 0)}\n",
                "💻 TECHNOLOGY",
                f"Collected: {cat_stats.get('TECHNOLOGY', {}).get('collected', 0)} | Published: {cat_stats.get('TECHNOLOGY', {}).get('published', 0)}\n",
                "🏏 SPORTS",
                f"Collected: {cat_stats.get('SPORTS', {}).get('collected', 0)} | Published: {cat_stats.get('SPORTS', {}).get('published', 0)}\n",
                "🎬 ENTERTAINMENT",
                f"Collected: {cat_stats.get('ENTERTAINMENT', {}).get('collected', 0)} | Published: {cat_stats.get('ENTERTAINMENT', {}).get('published', 0)}\n",
                "────────────────",
                "📝 ARTICLES",
                f"Collected: {day.get('articles_collected', 0)}",
                f"Duplicates Removed: {day.get('duplicates_removed', 0)}",
                f"Unique Articles: {day.get('unique_articles', 0)}",
                f"Clusters Created: {day.get('stories_clustered', 0)}\n",
                "🤖 AI PROCESSING",
                f"Processed: {day.get('ai_processed', 0)}",
                f"Successful: {day.get('ai_successful', 0)}",
                f"Failed: {day.get('ai_failed', 0)}\n",
                "📱 TELEGRAM PUBLISHING",
                f"Published: {day.get('posts_published', 0)}",
                f"Failed: {day.get('posts_failed', 0)}",
                f"Retries: {day.get('post_retries', 0)}\n",
                f"🚨 BREAKING: {day.get('breaking_posts', 0)}",
                f"🔥 HIGH PRIORITY: {day.get('high_priority_posts', 0)}",
                f"📌 NORMAL: {day.get('normal_priority_posts', 0)}"
            ]
            return "\n".join(report_lines)
        except Exception as e:
            logger.error("Failed to generate daily report: %s", e)
            return f"Error generating daily report: {e}"

    def generate_weekly_report(self, week_str: str = None) -> str:
        """Generates a human-readable weekly analytics report string for the given IST week."""
        try:
            if not week_str:
                week_str = get_ist_week_str()

            weekly_data = _load_json_file(self.weekly_file, dict)
            week = weekly_data.get(week_str, {})

            if not week:
                return f"📊 WEEKLY NEWS REPORT\nPeriod: {week_str}\nNo data recorded for this week."

            cats = week.get("category_totals", {})
            report_lines = [
                "📊 WEEKLY NEWS REPORT",
                f"Period: {week_str}\n",
                f"Total Posts: {week.get('total_posts_published', 0)}\n",
                f"📰 News: {cats.get('NEWS', 0)}",
                f"💻 Technology: {cats.get('TECHNOLOGY', 0)}",
                f"🏏 Sports: {cats.get('SPORTS', 0)}",
                f"🎬 Entertainment: {cats.get('ENTERTAINMENT', 0)}\n",
                f"Breaking News: {week.get('total_breaking_posts', 0)}",
                f"Articles Collected: {week.get('total_articles_collected', 0)}",
                f"Duplicates Removed: {week.get('total_duplicates_removed', 0)}",
                f"AI Processed: {week.get('total_ai_processed', 0)}",
                f"Failed Posts: {week.get('total_failed_posts', 0)}",
                f"Retry Count: {week.get('total_retries', 0)}",
                f"Average Posts/Day: {week.get('avg_posts_per_day', 0.0)}"
            ]
            return "\n".join(report_lines)
        except Exception as e:
            logger.error("Failed to generate weekly report: %s", e)
            return f"Error generating weekly report: {e}"

    def get_top_stories(self, period: str = "today") -> list[dict]:
        """Returns top stories recorded for 'today' or 'this_week'."""
        try:
            data = _load_json_file(self.top_stories_file, dict)
            if period == "today":
                date_str = get_ist_date_str()
                return data.get(date_str, [])
            elif period == "this_week":
                current_week = get_ist_week_str()
                result = []
                for d, stories in data.items():
                    try:
                        w = get_ist_week_str(datetime.strptime(d, "%Y-%m-%d").replace(tzinfo=IST))
                        if w == current_week:
                            result.extend(stories)
                    except Exception:
                        pass
                result.sort(key=lambda s: s.get("score", 0), reverse=True)
                return result[:10]
        except Exception as e:
            logger.error("Failed to get top stories: %s", e)
        return []

    def cleanup_old_analytics(self, retention_days: int = None):
        """Purges analytics records older than retention_days (default ANALYTICS_RETENTION_DAYS)."""
        if retention_days is None:
            retention_days = getattr(config, "ANALYTICS_RETENTION_DAYS", 90)

        try:
            cutoff = get_ist_now() - timedelta(days=retention_days)
            cutoff_date_str = cutoff.strftime("%Y-%m-%d")

            daily_data = _load_json_file(self.daily_file, dict)
            cleaned_daily = {d: v for d, v in daily_data.items() if d >= cutoff_date_str}
            if len(cleaned_daily) != len(daily_data):
                _save_json_file(self.daily_file, cleaned_daily)

            top_data = _load_json_file(self.top_stories_file, dict)
            cleaned_top = {d: v for d, v in top_data.items() if d >= cutoff_date_str}
            if len(cleaned_top) != len(top_data):
                _save_json_file(self.top_stories_file, cleaned_top)
        except Exception as e:
            logger.warning("Failed during analytics retention cleanup: %s", e)
