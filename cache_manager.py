"""
cache_manager.py
-----------------
PHASE 15 of the AI News Automation Agent.

Responsible for:
1. Safe TTL-backed caching of AI generated summaries, processed URLs, and RSS metadata.
2. Preventing duplicate AI API requests for identical or recurring story texts.
3. Automatic pruning of expired cache entries to keep cache file compact.
"""

import json
import logging
import shutil
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, Optional, Any
from zoneinfo import ZoneInfo

import config
from analytics_manager import get_ist_now

logger = logging.getLogger("cache_manager")
if not logger.handlers:
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    logger.addHandler(handler)

IST = ZoneInfo("Asia/Kolkata")
DATA_DIR = getattr(config, "DATA_DIR_PATH", Path(__file__).parent / "data")
CACHE_FILE = DATA_DIR / "cache.json"


def _create_default_cache() -> dict:
    return {
        "ai_summaries": {},
        "seen_urls": {},
        "source_metadata": {}
    }


class CacheManager:
    def __init__(self, filepath: Path = CACHE_FILE):
        self.filepath = filepath

    def load_cache(self) -> dict:
        """Loads cache data atomically."""
        if not self.filepath.exists():
            return _create_default_cache()
        try:
            with open(self.filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
        except Exception as e:
            logger.error("Failed to load cache (%s): %s", self.filepath, e)
        return _create_default_cache()

    def save_cache(self, data: dict):
        """Saves cache data atomically."""
        self.filepath.parent.mkdir(parents=True, exist_ok=True)
        tmp_fd, tmp_path = tempfile.mkstemp(dir=self.filepath.parent, prefix="cache_", suffix=".tmp")
        try:
            with open(tmp_fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            shutil.move(tmp_path, self.filepath)
        except Exception as e:
            Path(tmp_path).unlink(missing_ok=True)
            logger.error("Failed to save cache: %s", e)

    def _is_expired(self, expires_at_str: str) -> bool:
        try:
            exp_dt = datetime.fromisoformat(expires_at_str)
            return get_ist_now() > exp_dt
        except Exception:
            return True

    def get_ai_summary(self, key: str) -> Optional[dict]:
        """Retrieves cached AI summary if not expired."""
        cache = self.load_cache()
        entry = cache.get("ai_summaries", {}).get(key)
        if entry:
            if not self._is_expired(entry.get("expires_at", "")):
                logger.info("[CACHE] AI summary cache hit for key '%s'", key[:30])
                return entry.get("value")
            else:
                # Expired -> remove
                del cache["ai_summaries"][key]
                self.save_cache(cache)
        return None

    def set_ai_summary(self, key: str, summary: dict, ttl_hours: float = 48.0):
        """Caches AI summary with TTL."""
        cache = self.load_cache()
        exp_dt = get_ist_now() + timedelta(hours=ttl_hours)
        cache.setdefault("ai_summaries", {})[key] = {
            "value": summary,
            "expires_at": exp_dt.isoformat()
        }
        self.save_cache(cache)

    def is_url_cached(self, url: str) -> bool:
        """Checks if URL is cached and non-expired."""
        if not url:
            return False
        cache = self.load_cache()
        entry = cache.get("seen_urls", {}).get(url)
        if entry:
            if not self._is_expired(entry.get("expires_at", "")):
                return True
            else:
                del cache["seen_urls"][url]
                self.save_cache(cache)
        return False

    def mark_url_cached(self, url: str, ttl_hours: float = 168.0):
        """Caches processed URL for deduplication."""
        if not url:
            return
        cache = self.load_cache()
        exp_dt = get_ist_now() + timedelta(hours=ttl_hours)
        cache.setdefault("seen_urls", {})[url] = {
            "expires_at": exp_dt.isoformat()
        }
        self.save_cache(cache)

    def prune_expired_entries(self) -> int:
        """Prunes all expired entries across cache categories."""
        cache = self.load_cache()
        pruned_count = 0
        now = get_ist_now()

        for category in ["ai_summaries", "seen_urls", "source_metadata"]:
            cat_dict = cache.get(category, {})
            to_delete = []
            for k, entry in cat_dict.items():
                exp_str = entry.get("expires_at", "")
                if self._is_expired(exp_str):
                    to_delete.append(k)

            for k in to_delete:
                del cat_dict[k]
                pruned_count += 1

        if pruned_count > 0:
            self.save_cache(cache)
            logger.info("[CACHE] Pruned %d expired cache entries", pruned_count)

        return pruned_count
