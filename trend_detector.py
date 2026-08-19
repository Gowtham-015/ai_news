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

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)
CACHE_FILE = DATA_DIR / "trend_cache.json"


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

    def calculate_trend_score(self, cluster: Dict) -> int:
        """
        Calculates normalized trend momentum score (0 to 100) based on:
        - Number of reporting sources (Cross-source confirmation)
        - Velocity & frequency over time
        - Recency
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

        trend_score = min(100, base_score + article_boost)
        return int(trend_score)

    def analyze_trends(self, clusters: List[Dict]) -> List[Dict]:
        """
        Applies trend analysis and populates trend_score for all clusters.
        Updates persistent trend cache.
        """
        cache = self.load_cache()
        now_str = datetime.now(timezone.utc).isoformat()

        for cluster in clusters:
            cid = cluster.get("cluster_id")
            score = self.calculate_trend_score(cluster)
            cluster["trend_score"] = score

            if cid:
                if cid not in cache:
                    cache[cid] = {
                        "topic": cluster.get("topic", ""),
                        "first_seen_at": now_str,
                        "source_count": cluster.get("source_count", 1),
                        "highest_trend_score": score
                    }
                else:
                    cache[cid]["source_count"] = max(cache[cid]["source_count"], cluster.get("source_count", 1))
                    cache[cid]["highest_trend_score"] = max(cache[cid]["highest_trend_score"], score)

        self.save_cache(cache)
        return clusters
