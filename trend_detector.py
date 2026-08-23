"""
trend_detector.py
-----------------
PHASE 5 of the AI News Automation Agent.

Responsible for evaluating story momentum and trend velocity across RSS sources
and tracking trends over time using data/trend_cache.json.
"""

import json
import logging
import shutil
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Dict

import config

logger = logging.getLogger("trend_detector")
if not logger.handlers:
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    logger.addHandler(handler)

DATA_DIR = getattr(config, "DATA_DIR_PATH", Path(__file__).parent / "data")
DATA_DIR.mkdir(parents=True, exist_ok=True)
CACHE_FILE = getattr(config, "TREND_CACHE_FILE", DATA_DIR / "trend_cache.json")



class TrendDetector:
    def __init__(self, cache_filepath: Path = CACHE_FILE):
        self.cache_filepath = cache_filepath

    def load_cache(self) -> dict:
        """Loads persistent trend cache from data/trend_cache.json."""
        if not self.cache_filepath.exists():
            return {}
        try:
            with open(self.cache_filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
        except Exception as e:
            logger.error("Failed to load trend cache: %s", e)
        return {}

    def save_cache(self, cache: dict):
        """Saves trend cache atomically."""
        tmp_fd, tmp_path = tempfile.mkstemp(dir=self.cache_filepath.parent, prefix="trend_", suffix=".tmp")
        try:
            with open(tmp_fd, "w", encoding="utf-8") as f:
                json.dump(cache, f, indent=2, ensure_ascii=False)
            shutil.move(tmp_path, self.cache_filepath)
        except Exception as e:
            Path(tmp_path).unlink(missing_ok=True)
            logger.error("Failed to save trend cache: %s", e)

    def cleanup_old_cache(self, max_age_hours: int = 48):
        """Removes cache entries older than max_age_hours."""
        cache = self.load_cache()
        if not cache:
            return

        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(hours=max_age_hours)
        cleaned = {}

        for topic_key, item in cache.items():
            first_seen_str = item.get("first_seen_at")
            if first_seen_str:
                try:
                    dt = datetime.fromisoformat(first_seen_str.replace("Z", "+00:00"))
                    if dt > cutoff:
                        cleaned[topic_key] = item
                        continue
                except Exception:
                    pass
            cleaned[topic_key] = item

        if len(cleaned) != len(cache):
            self.save_cache(cleaned)

    def calculate_trend_score(self, cluster: Dict, history_items: List[Dict] = None) -> tuple[int, float]:
        """
        Calculates normalized trend momentum score (0 to 100) and velocity based on:
        - Multi-source coverage
        - Velocity of mentions over time buckets (mentions_now - mentions_previous) / delta_hours
        - Frequency of articles within cluster
        """
        source_count = cluster.get("source_count", 1)
        article_count = len(cluster.get("articles", []))

        # Base momentum from multi-source coverage
        if source_count >= 4:
            base_score = 95
        elif source_count == 3:
            base_score = 88
        elif source_count == 2:
            base_score = 75
        else:
            base_score = 50

        # Frequency boost for multiple articles reporting on topic
        article_boost = min(10, (article_count - 1) * 3)

        # Velocity calculation based on history
        velocity = 0.0
        velocity_boost = 0.0

        if history_items and len(history_items) >= 2:
            try:
                latest = history_items[-1]
                prev = history_items[-2]

                dt_latest = datetime.fromisoformat(latest["timestamp"].replace("Z", "+00:00"))
                dt_prev = datetime.fromisoformat(prev["timestamp"].replace("Z", "+00:00"))
                delta_hours = max(0.25, (dt_latest - dt_prev).total_seconds() / 3600.0)

                mentions_diff = latest.get("mentions", article_count) - prev.get("mentions", 0)
                if mentions_diff > 0:
                    velocity = round(mentions_diff / delta_hours, 2)
                    velocity_boost = min(25.0, velocity * 4.0)
            except Exception:
                pass

        trend_score = min(100, base_score + article_boost + velocity_boost)
        return int(trend_score), velocity

    def analyze_trends(self, clusters: List[Dict]) -> List[Dict]:
        """
        Applies trend analysis, populates trend_score and trend_velocity for all clusters.
        Updates persistent trend cache with time-stamped mention history.
        """
        cache = self.load_cache()
        now_dt = datetime.now(timezone.utc)
        now_str = now_dt.isoformat()

        for cluster in clusters:
            cid = cluster.get("cluster_id")
            topic_key = cluster.get("topic", "")

            cache_entry = cache.get(cid) if cid else None
            history = cache_entry.get("mention_history", []) if cache_entry else []

            # Append current observation to history
            article_count = max(len(cluster.get("articles", [])), cluster.get("source_count", 1))
            current_obs = {"timestamp": now_str, "mentions": article_count}

            temp_history = list(history) + [current_obs]

            score, velocity = self.calculate_trend_score(cluster, temp_history)
            cluster["trend_score"] = score
            cluster["trend_velocity"] = velocity

            if cid:
                if cid not in cache:
                    cache[cid] = {
                        "topic": topic_key,
                        "first_seen_at": now_str,
                        "last_seen_at": now_str,
                        "source_count": cluster.get("source_count", 1),
                        "highest_trend_score": score,
                        "velocity": velocity,
                        "mention_history": [current_obs]
                    }
                else:
                    cache[cid]["last_seen_at"] = now_str
                    cache[cid]["source_count"] = max(cache[cid]["source_count"], cluster.get("source_count", 1))
                    cache[cid]["highest_trend_score"] = max(cache[cid]["highest_trend_score"], score)
                    cache[cid]["velocity"] = velocity
                    hist = cache[cid].get("mention_history", [])
                    hist.append(current_obs)
                    # Keep history capped to last 20 snapshots
                    cache[cid]["mention_history"] = hist[-20:]

        self.save_cache(cache)
        return clusters
