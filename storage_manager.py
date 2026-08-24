"""
storage_manager.py
-------------------
PHASE 15 of the AI News Automation Agent.

Responsible for:
1. Safe retention policy enforcement to prevent indefinite file growth.
2. Pruning posts.json (max 100 posts).
3. Pruning published_news.json (max 500 records).
4. Pruning analytics history files older than retention policy (90 days).
5. Safe atomic file writes to prevent data corruption during pruning.
"""

import json
import logging
import shutil
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional
from zoneinfo import ZoneInfo

import config
from analytics_manager import get_ist_now

logger = logging.getLogger("storage_manager")
if not logger.handlers:
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    logger.addHandler(handler)

IST = ZoneInfo("Asia/Kolkata")
DATA_DIR = getattr(config, "DATA_DIR_PATH", Path(__file__).parent / "data")
POSTS_FILE = DATA_DIR / "posts.json"
PUBLISHED_NEWS_FILE = DATA_DIR / "published_news.json"
ANALYTICS_DIR = DATA_DIR / "analytics"


class StorageManager:
    def __init__(self, data_dir: Path = DATA_DIR):
        self.data_dir = data_dir
        self.posts_file = data_dir / "posts.json"
        self.published_file = data_dir / "published_news.json"
        self.analytics_dir = data_dir / "analytics"

    def prune_posts_file(self, max_posts: int = 100) -> int:
        """Keeps only the most recent max_posts in posts.json."""
        if not self.posts_file.exists():
            return 0
        try:
            with open(self.posts_file, "r", encoding="utf-8") as f:
                posts = json.load(f)
            if isinstance(posts, list) and len(posts) > max_posts:
                pruned_posts = posts[-max_posts:]
                removed_count = len(posts) - len(pruned_posts)

                tmp_fd, tmp_path = tempfile.mkstemp(dir=self.posts_file.parent, prefix="posts_", suffix=".tmp")
                with open(tmp_fd, "w", encoding="utf-8") as f:
                    json.dump(pruned_posts, f, indent=2, ensure_ascii=False)
                shutil.move(tmp_path, self.posts_file)
                logger.info("[STORAGE] Pruned %d old posts from posts.json", removed_count)
                return removed_count
        except Exception as e:
            logger.error("Failed to prune posts.json: %s", e)
        return 0

    def prune_published_news(self, max_history: int = 500) -> int:
        """Keeps only the most recent max_history records in published_news.json."""
        if not self.published_file.exists():
            return 0
        try:
            with open(self.published_file, "r", encoding="utf-8") as f:
                history = json.load(f)
            if isinstance(history, list) and len(history) > max_history:
                pruned_history = history[-max_history:]
                removed_count = len(history) - len(pruned_history)

                tmp_fd, tmp_path = tempfile.mkstemp(dir=self.published_file.parent, prefix="published_", suffix=".tmp")
                with open(tmp_fd, "w", encoding="utf-8") as f:
                    json.dump(pruned_history, f, indent=2, ensure_ascii=False)
                shutil.move(tmp_path, self.published_file)
                logger.info("[STORAGE] Pruned %d old records from published_news.json", removed_count)
                return removed_count
        except Exception as e:
            logger.error("Failed to prune published_news.json: %s", e)
        return 0

    def prune_analytics_dir(self, max_days: int = 90) -> int:
        """Deletes analytics snapshot files older than max_days."""
        if not self.analytics_dir.exists():
            return 0
        removed_count = 0
        cutoff_dt = get_ist_now() - timedelta(days=max_days)

        try:
            for p in self.analytics_dir.glob("*.json"):
                if p.name in ("daily.json", "weekly.json", "top_stories.json", "failures.json"):
                    continue  # Keep main active state files
                try:
                    mtime = datetime.fromtimestamp(p.stat().st_mtime, tz=IST)
                    if mtime < cutoff_dt:
                        p.unlink()
                        removed_count += 1
                except Exception:
                    pass
            if removed_count > 0:
                logger.info("[STORAGE] Deleted %d expired analytics snapshot files", removed_count)
        except Exception as e:
            logger.error("Failed to prune analytics dir: %s", e)
        return removed_count

    def prune_all_storage(self) -> dict:
        """Executes all storage retention pruning tasks."""
        return {
            "posts_pruned": self.prune_posts_file(),
            "published_pruned": self.prune_published_news(),
            "analytics_pruned": self.prune_analytics_dir()
        }
