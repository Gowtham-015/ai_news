"""
queue_manager.py
----------------
PHASE 4 & PHASE 5 of the AI News Automation Agent.

Responsible for:
1. Managing posts.json with atomic file writes.
2. Enforcing MAX_QUEUE_SIZE limits to prevent queue explosion.
3. Calculating category balancing needs to prioritize underrepresented categories.
4. Calculating spaced FUTURE schedule times (e.g. 30 minutes apart) continuing after existing scheduled posts.
5. Preventing duplicate queuing of already scheduled or published articles.
"""

import json
import logging
import shutil
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import config
from deduplicator import normalize_url, normalize_title, load_published_history
import scheduler

logger = logging.getLogger("queue_manager")
if not logger.handlers:
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    logger.addHandler(handler)

POSTS_FILE = getattr(config, "POSTS_FILE", Path(__file__).parent / "data" / "posts.json")



class QueueManager:
    def __init__(self, posts_filepath: Path = POSTS_FILE):
        self.posts_filepath = posts_filepath

    def load_queue(self) -> list[dict]:
        """Reads posts.json safely from configured posts_filepath."""
        if not self.posts_filepath.exists():
            return []
        try:
            with open(self.posts_filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
        except Exception as e:
            logger.error("Failed to load queue from %s: %s", self.posts_filepath, e)
        return []

    def save_queue(self, posts: list[dict]):
        """Saves posts list back to posts_filepath atomically."""
        tmp_fd, tmp_path = tempfile.mkstemp(dir=self.posts_filepath.parent, prefix="posts_", suffix=".tmp")
        try:
            with open(tmp_fd, "w", encoding="utf-8") as f:
                json.dump(posts, f, indent=2, ensure_ascii=False)
            shutil.move(tmp_path, self.posts_filepath)
        except Exception as e:
            Path(tmp_path).unlink(missing_ok=True)
            logger.error("Failed to save posts queue: %s", e)

    def get_queued_counts(self, posts: list[dict] = None) -> dict:
        """
        Returns count of currently 'scheduled' posts per category.
        """
        if posts is None:
            posts = self.load_queue()

        counts = {"NEWS": 0, "TECHNOLOGY": 0, "SPORTS": 0, "ENTERTAINMENT": 0}

        for p in posts:
            if p.get("status") == "scheduled":
                cat = str(p.get("category", "")).upper()
                if cat in counts:
                    counts[cat] += 1
                else:
                    counts[cat] = 1
        return counts

    def calculate_category_needs(self, target_per_cat: int = None, instant_schedule: bool = False) -> dict:
        """
        Calculates how many additional articles are needed per category
        to achieve balanced category representation.
        In instant_schedule/cron mode, requests target_per_cat articles per category.
        """
        if target_per_cat is None:
            target_per_cat = getattr(config, "POSTS_PER_CATEGORY", 2)

        if instant_schedule:
            return {"NEWS": target_per_cat, "TECHNOLOGY": target_per_cat, "SPORTS": target_per_cat, "ENTERTAINMENT": target_per_cat}

        queued_counts = self.get_queued_counts()
        needed = {}

        for cat, count in queued_counts.items():
            diff = target_per_cat - count
            needed[cat] = max(0, diff)

        return needed

    def add_posts_to_queue(
        self,
        new_posts: list[dict],
        max_queue_size: int = None,
        history_filepath: Path = None,
        instant_schedule: bool = False
    ) -> int:
        """
        Adds new AI-generated posts to posts.json safely.
        - Enforces MAX_QUEUE_SIZE limit.
        - Calculates spaced FUTURE schedule times (e.g. 30 mins apart) continuing after existing scheduled posts.
        - If instant_schedule is True, starts schedule times immediately at current time for cron/on-demand publishing.
        - Prevents queuing duplicate URLs/titles.
        - Returns number of new posts added.
        """
        if max_queue_size is None:
            max_queue_size = getattr(config, "MAX_QUEUE_SIZE", 20)

        existing_posts = self.load_queue()
        
        # Build set of already queued/published URLs & titles
        seen_urls = set()
        seen_titles = set()

        for p in existing_posts:
            url = p.get("original_url") or p.get("url", "")
            if url:
                seen_urls.add(normalize_url(url))
            title = p.get("title", "")
            if title:
                seen_titles.add(normalize_title(title))

        # Include published history in seen sets
        history = load_published_history(filepath=history_filepath) if history_filepath else load_published_history()
        for item in history:
            raw_u = item.get("original_url") or item.get("url") or ""
            if raw_u:
                seen_urls.add(normalize_url(raw_u))
            raw_t = item.get("title") or ""
            if raw_t:
                seen_titles.add(normalize_title(raw_t))


        # Check existing scheduled count
        if instant_schedule:
            scheduled_posts = []
            scheduled_count = 0
            available_slots = max_queue_size
        else:
            scheduled_posts = [p for p in existing_posts if p.get("status") == "scheduled"]
            scheduled_count = len(scheduled_posts)
            available_slots = max(0, max_queue_size - scheduled_count)

        logger.info("[QUEUE] Selected %d candidate articles", len(new_posts))
        logger.info("[QUEUE] Existing queue size: %d scheduled posts (Max limit: %d)", scheduled_count, max_queue_size)

        if available_slots <= 0:
            logger.warning(
                "[QUEUE] Queue size limit reached (%d/%d scheduled posts). Skipping adding new posts.",
                scheduled_count,
                max_queue_size
            )
            return 0

        # Calculate future scheduled times
        interval_minutes = getattr(config, "NEWS_COLLECTION_INTERVAL_MINUTES", 30)
        now_tz = datetime.now(scheduler.TIMEZONE)

        latest_scheduled_dt = None
        for p in scheduled_posts:
            try:
                dt = scheduler.parse_scheduled_time(p)
                if latest_scheduled_dt is None or dt > latest_scheduled_dt:
                    latest_scheduled_dt = dt
            except Exception:
                pass

        if instant_schedule:
            start_dt = now_tz
        elif latest_scheduled_dt and latest_scheduled_dt > now_tz:
            start_dt = latest_scheduled_dt + timedelta(minutes=interval_minutes)
        else:
            start_dt = now_tz + timedelta(minutes=interval_minutes)



        # Priority sorting: BREAKING (1) > HIGH (2) > NORMAL (3) > LOW (4)
        prio_order = {"BREAKING": 1, "HIGH": 2, "NORMAL": 3, "LOW": 4}
        sorted_new_posts = sorted(
            new_posts,
            key=lambda p: prio_order.get(p.get("priority", "NORMAL"), 3)
        )

        existing_ids = [p.get("id") for p in existing_posts if isinstance(p.get("id"), int)]
        next_id = (max(existing_ids) + 1) if existing_ids else 1

        added_count = 0
        posts_to_append = []

        for post in sorted_new_posts:
            if added_count >= available_slots:
                logger.info("[QUEUE] Reached queue capacity limit (%d posts added).", added_count)
                break

            priority = post.get("priority", "NORMAL")
            final_score = post.get("final_score", 60)

            # Filter out LOW priority low-value posts if score < 55
            if priority == "LOW" and final_score < 55:
                logger.info("Discarding low-value post below quality threshold: '%s' (Score: %s)", post.get("title"), final_score)
                continue

            raw_url = post.get("original_url") or post.get("url", "")
            norm_url = normalize_url(raw_url)
            norm_title = normalize_title(post.get("title", ""))

            if norm_url and norm_url in seen_urls:
                logger.debug("Skipping adding to queue: URL already present (%s)", raw_url)
                continue

            if norm_title and norm_title in seen_titles:
                logger.debug("Skipping adding to queue: Title already present (%s)", post.get("title"))
                continue

            # Fast-path for BREAKING news: schedule immediately at current time
            if priority == "BREAKING" or post.get("is_breaking"):
                sched_time_dt = now_tz
            elif instant_schedule:
                sched_time_dt = now_tz
            else:
                sched_time_dt = start_dt + timedelta(minutes=added_count * interval_minutes)

            sched_time_str = sched_time_dt.strftime(scheduler.DATETIME_FORMAT)

            post_entry = {
                "id": next_id,
                "category": str(post.get("category", "")).upper(),
                "title": post.get("title", ""),
                "content": post.get("content", ""),
                "summary": post.get("summary", ""),
                "why_it_matters": post.get("why_it_matters", ""),
                "scheduled_time": sched_time_str,
                "status": "scheduled",
                "published_time": None,
                "original_url": raw_url,
                "source": post.get("source", ""),
                "priority": priority,
                "is_breaking": post.get("is_breaking", False),
                "is_followup": post.get("is_followup", False),
                "image_url": post.get("image_url", ""),
                "source_article_id": post.get("source_article_id", "")
            }

            posts_to_append.append(post_entry)
            if norm_url:
                seen_urls.add(norm_url)
            if norm_title:
                seen_titles.add(norm_title)

            logger.info("[QUEUE] Post %d (ID %d) scheduled for future time: %s (%s)",
                        added_count + 1, next_id, sched_time_str, post_entry["title"])

            next_id += 1
            added_count += 1

        if added_count > 0:
            existing_posts.extend(posts_to_append)
            self.save_queue(existing_posts)
            logger.info("Successfully added %d new posts to posts.json (Queue size now: %d)",
                        added_count, scheduled_count + added_count)

        return added_count
