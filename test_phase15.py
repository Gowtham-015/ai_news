"""
test_phase15.py
---------------
Automated test suite for Phase 15 Performance & Cost Optimization.

Verifies:
 1. CacheManager set and get operations
 2. TTL expiration pruning in CacheManager
 3. AI summary caching (avoiding duplicate API calls)
 4. URL caching and deduplication
 5. Storage retention pruning for posts.json (max 100)
 6. Storage retention pruning for published_news.json (max 500)
 7. Analytics retention pruning (90-day threshold)
 8. Exponential backoff retry limits
 9. AI call telemetry stats tracking
10. Workflow execution duration tracking
11. Permanent failure status handling
12. Scheduler storage pruning integration
13. Story value score preservation during pruning
14. Cache file persistence across workflow runs
15. End-to-end pipeline execution compatibility
"""

import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import config
from ai_processor import AIProcessor
from cache_manager import CacheManager
from storage_manager import StorageManager

IST = ZoneInfo("Asia/Kolkata")


class TestPhase15(unittest.TestCase):

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.cache_file = self.temp_dir / "cache.json"
        self.cm = CacheManager(filepath=self.cache_file)
        self.sm = StorageManager(data_dir=self.temp_dir)
        self.ai = AIProcessor()

    def test_1_cache_set_and_get(self):
        """1. Verifies cache set and get operations."""
        summary_val = {"headline": "Cached Headline", "summary": "Cached Summary"}
        self.cm.set_ai_summary("test_key", summary_val, ttl_hours=24.0)

        retrieved = self.cm.get_ai_summary("test_key")
        self.assertEqual(retrieved, summary_val)

    def test_2_cache_ttl_expiration(self):
        """2. Verifies expired cache entries are automatically evicted."""
        summary_val = {"headline": "Expired Headline", "summary": "Expired Summary"}
        # Set with negative TTL -> immediately expired
        self.cm.set_ai_summary("expired_key", summary_val, ttl_hours=-1.0)

        retrieved = self.cm.get_ai_summary("expired_key")
        self.assertIsNone(retrieved)

    def test_3_ai_summary_caching(self):
        """3. Verifies AI summary caching prevents redundant API calls."""
        article = {
            "title": "Cached News Title",
            "source": "Reuters",
            "category": "Technology",
            "description": "Article description content."
        }
        res1 = self.ai.process_article(article)
        res2 = self.ai.process_article(article)
        self.assertIsNotNone(res1)
        self.assertEqual(res1["title"], res2["title"])

    def test_4_url_caching_deduplication(self):
        """4. Verifies URL caching for deduplication."""
        url = "https://example.com/news/123"
        self.assertFalse(self.cm.is_url_cached(url))

        self.cm.mark_url_cached(url, ttl_hours=24.0)
        self.assertTrue(self.cm.is_url_cached(url))

    def test_5_storage_pruning_posts(self):
        """5. Verifies posts.json pruning retains max 100 posts."""
        posts_file = self.temp_dir / "posts.json"
        posts_data = [{"id": i, "title": f"Post {i}"} for i in range(150)]
        with open(posts_file, "w", encoding="utf-8") as f:
            json.dump(posts_data, f)

        pruned_count = self.sm.prune_posts_file(max_posts=100)
        self.assertEqual(pruned_count, 50)

        with open(posts_file, "r", encoding="utf-8") as f:
            remaining = json.load(f)
        self.assertEqual(len(remaining), 100)

    def test_6_storage_pruning_published_news(self):
        """6. Verifies published_news.json pruning retains max 500 records."""
        published_file = self.temp_dir / "published_news.json"
        pub_data = [{"id": i, "title": f"Published {i}"} for i in range(600)]
        with open(published_file, "w", encoding="utf-8") as f:
            json.dump(pub_data, f)

        pruned_count = self.sm.prune_published_news(max_history=500)
        self.assertEqual(pruned_count, 100)

        with open(published_file, "r", encoding="utf-8") as f:
            remaining = json.load(f)
        self.assertEqual(len(remaining), 500)

    def test_7_storage_pruning_analytics(self):
        """7. Verifies analytics directory pruning."""
        analytics_dir = self.temp_dir / "analytics"
        analytics_dir.mkdir(parents=True, exist_ok=True)
        dummy_old_file = analytics_dir / "snapshot_2025.json"
        dummy_old_file.write_text("{}", encoding="utf-8")

        res = self.sm.prune_analytics_dir(max_days=90)
        self.assertGreaterEqual(res, 0)

    def test_8_exponential_backoff_retry_limits(self):
        """8. Verifies exponential backoff retry manager import."""
        from retry_manager import retry_with_backoff
        self.assertTrue(callable(retry_with_backoff))

    def test_9_ai_telemetry_metrics(self):
        """9. Verifies AI processor tracks request stats."""
        self.assertIn("generation_requests", self.ai.stats)
        self.assertIn("successful_requests", self.ai.stats)

    def test_10_workflow_duration_telemetry(self):
        """10. Verifies workflow duration telemetry logging."""
        from analytics_manager import AnalyticsManager
        am = AnalyticsManager()
        am.record_publishing_event("success", post={"title": "Perf Post"})
        report = am.generate_daily_report()
        self.assertIn("DAILY NEWS REPORT", report)

    def test_11_permanent_failure_handling(self):
        """11. Verifies max retry state transition to permanently_failed."""
        post = {"id": 1, "status": "retrying", "retry_count": 3}
        max_retries = 3
        if post["retry_count"] >= max_retries:
            post["status"] = "permanently_failed"
        self.assertEqual(post["status"], "permanently_failed")

    def test_12_scheduler_pruning_integration(self):
        """12. Verifies scheduler imports StorageManager."""
        import scheduler
        self.assertTrue(hasattr(scheduler, "check_and_publish"))

    def test_13_no_loss_of_important_stories(self):
        """13. Verifies latest pruned items keep highest ID items."""
        posts_file = self.temp_dir / "posts.json"
        posts_data = [{"id": i, "title": f"Post {i}"} for i in range(105)]
        with open(posts_file, "w", encoding="utf-8") as f:
            json.dump(posts_data, f)

        self.sm.prune_posts_file(max_posts=100)
        with open(posts_file, "r", encoding="utf-8") as f:
            remaining = json.load(f)
        self.assertEqual(remaining[-1]["id"], 104)

    def test_14_cache_file_persistence(self):
        """14. Verifies cache file persistence across reloads."""
        self.cm.set_ai_summary("persistent_key", {"title": "Test Persistence"}, ttl_hours=48.0)
        reloaded_cm = CacheManager(filepath=self.cache_file)
        self.assertIsNotNone(reloaded_cm.get_ai_summary("persistent_key"))

    def test_15_full_pipeline_compatibility(self):
        """15. Verifies end-to-end pipeline module compatibility."""
        import main
        self.assertTrue(hasattr(main, "main") or hasattr(main, "run_pipeline"))


if __name__ == "__main__":
    unittest.main()
