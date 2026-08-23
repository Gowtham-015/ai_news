"""
story_lifecycle.py
------------------
PHASE 9 of the AI News Automation Agent.

Responsible for tracking story lifecycles across pipeline runs:
- States: NEW -> DEVELOPING -> TRENDING -> RESOLVED
- Prevents repetitive posting of unchanged stories.
- Evaluates follow-up eligibility for developing stories (at least 2 hours apart with significant updates).
- Persists story history in data/story_lifecycle.json.
"""

import json
import logging
import re
import shutil
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Tuple

import config
from story_clusterer import extract_keywords

logger = logging.getLogger("story_lifecycle")
if not logger.handlers:
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    logger.addHandler(handler)

DATA_DIR = getattr(config, "DATA_DIR_PATH", Path(__file__).parent / "data")
DATA_DIR.mkdir(parents=True, exist_ok=True)
LIFECYCLE_FILE = DATA_DIR / "story_lifecycle.json"


class StoryLifecycleManager:
    def __init__(self, filepath: Path = LIFECYCLE_FILE):
        self.filepath = filepath

    def load_lifecycle(self) -> dict:
        """Loads story lifecycle tracking dict from data/story_lifecycle.json."""
        if not self.filepath.exists():
            return {}
        try:
            with open(self.filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
        except Exception as e:
            logger.error("Failed to load story lifecycle file (%s): %s", self.filepath, e)
        return {}

    def save_lifecycle(self, data: dict):
        """Saves story lifecycle dict atomically."""
        tmp_fd, tmp_path = tempfile.mkstemp(dir=self.filepath.parent, prefix="lifecycle_", suffix=".tmp")
        try:
            with open(tmp_fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            shutil.move(tmp_path, self.filepath)
        except Exception as e:
            Path(tmp_path).unlink(missing_ok=True)
            logger.error("Failed to save story lifecycle data: %s", e)

    def _get_story_key(self, cluster: dict) -> str:
        """Generates a normalized key for a story cluster based on its topic keywords."""
        topic = cluster.get("topic", "")
        best_title = cluster.get("best_article", {}).get("title", "")
        text = f"{topic} {best_title}".strip()
        keywords = sorted(list(extract_keywords(text)))
        if not keywords:
            return cluster.get("cluster_id", "unknown_cluster")
        return "_".join(keywords[:5])

    def get_story_state(self, cluster: dict, lifecycle_data: dict = None) -> str:
        """
        Determines current state of a story cluster:
        - NEW: First time detected
        - DEVELOPING: Multi-source interest, <= 12 hours old
        - TRENDING: High momentum / multi-source coverage (>=3 sources)
        - RESOLVED: Older than 24 hours with no recent update
        """
        if lifecycle_data is None:
            lifecycle_data = self.load_lifecycle()

        story_key = self._get_story_key(cluster)
        entry = lifecycle_data.get(story_key)

        source_count = cluster.get("source_count", 1)
        score = cluster.get("final_score", 50)

        if not entry:
            if source_count >= 3 or score >= 85:
                return "TRENDING"
            return "NEW"

        first_seen_str = entry.get("first_seen_at")
        if first_seen_str:
            try:
                dt = datetime.fromisoformat(first_seen_str.replace("Z", "+00:00"))
                age = datetime.now(timezone.utc) - dt
                if age > timedelta(hours=24):
                    return "RESOLVED"
            except Exception:
                pass

        if source_count >= 3 or score >= 85:
            return "TRENDING"
        elif entry.get("post_count", 0) > 0:
            return "DEVELOPING"
        else:
            return "NEW"

    def is_eligible_for_followup(self, cluster: dict, min_interval_hours: float = 2.0) -> Tuple[bool, str]:
        """
        Evaluates whether a story cluster that was previously posted qualifies for a follow-up post.
        
        Criteria:
        - Must have been posted before.
        - ALLOW_MAJOR_STORY_UPDATES setting must be True.
        - Must have elapsed at least min_interval_hours since the last post.
        - Must show meaningful new development (higher source count, breaking status, or significant new headline terms).
        """
        lifecycle_data = self.load_lifecycle()
        story_key = self._get_story_key(cluster)
        entry = lifecycle_data.get(story_key)

        if not entry or entry.get("post_count", 0) == 0:
            return True, "Initial post for new story"

        # Enforce ALLOW_MAJOR_STORY_UPDATES config setting
        allow_updates = getattr(config, "ALLOW_MAJOR_STORY_UPDATES", True)
        if not allow_updates:
            return False, "Follow-ups disabled: ALLOW_MAJOR_STORY_UPDATES is False"

        last_posted_str = entry.get("last_posted_at")
        if not last_posted_str:
            return True, "No previous post timestamp recorded"

        try:
            last_posted_dt = datetime.fromisoformat(last_posted_str.replace("Z", "+00:00"))
            elapsed = datetime.now(timezone.utc) - last_posted_dt
            if elapsed < timedelta(hours=min_interval_hours):
                hrs = elapsed.total_seconds() / 3600.0
                return False, f"Follow-up requested too soon ({hrs:.1f}h elapsed, minimum {min_interval_hours}h required)"
        except Exception:
            pass

        prev_source_count = entry.get("source_count", 1)
        curr_source_count = cluster.get("source_count", 1)
        is_breaking = cluster.get("is_breaking") or cluster.get("final_score", 0) >= 90

        if curr_source_count > prev_source_count:
            return True, f"Multi-source expansion ({prev_source_count} -> {curr_source_count} sources)"
        if is_breaking:
            return True, "Breaking news follow-up"

        # Check if new article title differs significantly
        prev_title = entry.get("last_posted_title", "")
        curr_title = cluster.get("best_article", {}).get("title", "")
        kw_prev = extract_keywords(prev_title)
        kw_curr = extract_keywords(curr_title)

        diff = kw_curr.difference(kw_prev)
        if len(diff) >= 2:
            return True, f"Significant headline progression: new terms ({', '.join(list(diff)[:3])})"

        return False, "No meaningful new development detected since last post"

    def record_posted_story(self, cluster: dict):
        """Records a post event for a story cluster in data/story_lifecycle.json."""
        lifecycle_data = self.load_lifecycle()
        story_key = self._get_story_key(cluster)
        now_str = datetime.now(timezone.utc).isoformat()

        entry = lifecycle_data.get(story_key, {
            "story_key": story_key,
            "topic": cluster.get("topic", ""),
            "first_seen_at": now_str,
            "post_count": 0,
            "sources": []
        })

        entry["post_count"] += 1
        entry["last_posted_at"] = now_str
        entry["last_posted_title"] = cluster.get("best_article", {}).get("title", cluster.get("topic", ""))
        entry["source_count"] = max(entry.get("source_count", 1), cluster.get("source_count", 1))

        current_sources = set(entry.get("sources", []))
        current_sources.update(cluster.get("sources", []))
        entry["sources"] = list(current_sources)

        entry["state"] = self.get_story_state(cluster, lifecycle_data)
        lifecycle_data[story_key] = entry
        self.save_lifecycle(lifecycle_data)
        logger.info("Updated story lifecycle for key '%s' (State: %s, Posts: %d)", story_key, entry["state"], entry["post_count"])

    def cleanup_old_stories(self, max_age_hours: int = 72):
        """Purges story lifecycle records older than max_age_hours."""
        lifecycle_data = self.load_lifecycle()
        if not lifecycle_data:
            return

        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(hours=max_age_hours)
        cleaned = {}

        for k, v in lifecycle_data.items():
            last_seen = v.get("last_posted_at") or v.get("first_seen_at")
            if last_seen:
                try:
                    dt = datetime.fromisoformat(last_seen.replace("Z", "+00:00"))
                    if dt > cutoff:
                        cleaned[k] = v
                        continue
                except Exception:
                    pass
            cleaned[k] = v

        if len(cleaned) != len(lifecycle_data):
            self.save_lifecycle(cleaned)
