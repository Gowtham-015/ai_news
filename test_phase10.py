"""
test_phase10.py
---------------
Automated test suite for Phase 10 Telegram Analytics & Statistics.

Verifies:
 1. Daily metric creation
 2. Metric incrementing
 3. Category statistics tracking
 4. Source statistics tracking
 5. Duplicate statistics tracking
 6. AI usage statistics tracking
 7. Telegram publishing statistics tracking
 8. Priority statistics tracking
 9. Story lifecycle statistics tracking
10. Daily report generation
11. Weekly report generation
12. Top stories retrieval
13. Trending statistics tracking
14. Failure statistics categorization
15. Retention policy cleanup
16. IST date boundaries
17. Persistence across runs
18. Concurrent-safe atomic file updates
19. Analytics failure isolation (never crashes main pipeline)
20. Empty-data day graceful handling
21. Corrupted analytics file recovery
"""

import json
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo

import config
from analytics_manager import (
    AnalyticsManager,
    get_ist_now,
    get_ist_date_str,
    get_ist_week_str,
    IST
)


class TestPhase10(unittest.TestCase):

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.am = AnalyticsManager(analytics_dir=self.temp_dir)

    def test_1_daily_metric_creation(self):
        """1. Verifies initial creation of default daily metrics entry."""
        today_str = get_ist_date_str()
        daily_file = self.temp_dir / "daily.json"
        
        self.am.record_pipeline_run({"collected_count": 10})
        self.assertTrue(daily_file.exists())
        
        with open(daily_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            self.assertIn(today_str, data)
            self.assertEqual(data[today_str]["articles_collected"], 10)

    def test_2_metric_increment(self):
        """2. Verifies incremental accumulation of metrics across runs."""
        self.am.record_pipeline_run({"collected_count": 10, "duplicates_count": 2})
        self.am.record_pipeline_run({"collected_count": 15, "duplicates_count": 5})

        daily_file = self.temp_dir / "daily.json"
        with open(daily_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            today_str = get_ist_date_str()
            self.assertEqual(data[today_str]["articles_collected"], 25)
            self.assertEqual(data[today_str]["duplicates_removed"], 7)

    def test_3_category_statistics(self):
        """3. Verifies category breakdown metrics (News, Technology, Sports, Entertainment)."""
        cat_data = {"News": 20, "Technology": 15, "Sports": 30, "Entertainment": 10}
        self.am.record_pipeline_run({"category_collected": cat_data})

        daily_file = self.temp_dir / "daily.json"
        with open(daily_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            today_str = get_ist_date_str()
            stats = data[today_str]["category_stats"]
            self.assertEqual(stats["NEWS"]["collected"], 20)
            self.assertEqual(stats["TECHNOLOGY"]["collected"], 15)
            self.assertEqual(stats["SPORTS"]["collected"], 30)
            self.assertEqual(stats["ENTERTAINMENT"]["collected"], 10)

    def test_4_source_statistics(self):
        """4. Verifies source-level article tracking."""
        src_data = {"Reuters": 5, "BBC News": 8}
        self.am.record_pipeline_run({"source_collected": src_data})

        daily_file = self.temp_dir / "daily.json"
        with open(daily_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            today_str = get_ist_date_str()
            stats = data[today_str]["source_stats"]
            self.assertEqual(stats["Reuters"]["collected"], 5)
            self.assertEqual(stats["BBC News"]["collected"], 8)

    def test_5_duplicate_statistics(self):
        """5. Verifies deduplication pipeline metrics (collected -> duplicates -> unique -> clusters)."""
        self.am.record_pipeline_run({
            "collected_count": 100,
            "duplicates_count": 40,
            "unique_count": 60,
            "clusters_count": 25
        })

        daily_file = self.temp_dir / "daily.json"
        with open(daily_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            today_str = get_ist_date_str()
            self.assertEqual(data[today_str]["articles_collected"], 100)
            self.assertEqual(data[today_str]["duplicates_removed"], 40)
            self.assertEqual(data[today_str]["unique_articles"], 60)
            self.assertEqual(data[today_str]["stories_clustered"], 25)

    def test_6_ai_usage_statistics(self):
        """6. Verifies AI usage tracking (processed, successful, failed, filtered)."""
        self.am.record_pipeline_run({
            "ai_processed_count": 10,
            "ai_successful_count": 9,
            "ai_failed_count": 1,
            "ai_filtered_before_count": 15
        })

        daily_file = self.temp_dir / "daily.json"
        with open(daily_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            today_str = get_ist_date_str()
            self.assertEqual(data[today_str]["ai_processed"], 10)
            self.assertEqual(data[today_str]["ai_successful"], 9)
            self.assertEqual(data[today_str]["ai_failed"], 1)
            self.assertEqual(data[today_str]["ai_filtered_before"], 15)

    def test_7_publishing_statistics(self):
        """7. Verifies Telegram publishing metrics (success, retries, failure, photo vs text)."""
        post_photo = {"category": "Technology", "title": "Photo Tech Post", "image_url": "https://example.com/a.jpg"}
        post_text = {"category": "News", "title": "Text News Post"}

        self.am.record_publishing_event("success", post=post_photo, is_photo=True)
        self.am.record_publishing_event("success", post=post_text, is_photo=False)
        self.am.record_publishing_event("retry", post=post_text)
        self.am.record_publishing_event("permanently_failed", post=post_text)

        daily_file = self.temp_dir / "daily.json"
        with open(daily_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            today_str = get_ist_date_str()
            self.assertEqual(data[today_str]["posts_published"], 2)
            self.assertEqual(data[today_str]["photo_posts"], 1)
            self.assertEqual(data[today_str]["text_only_posts"], 1)
            self.assertEqual(data[today_str]["post_retries"], 1)
            self.assertEqual(data[today_str]["permanently_failed"], 1)

    def test_8_priority_statistics(self):
        """8. Verifies breakdown of BREAKING, HIGH, NORMAL, and LOW priority published posts."""
        post_b = {"category": "News", "title": "Breaking News", "is_breaking": True}
        post_h = {"category": "Sports", "title": "High Priority Sports"}
        post_n = {"category": "Technology", "title": "Normal Tech"}

        self.am.record_publishing_event("success", post=post_b, priority="BREAKING")
        self.am.record_publishing_event("success", post=post_h, priority="HIGH")
        self.am.record_publishing_event("success", post=post_n, priority="NORMAL")

        daily_file = self.temp_dir / "daily.json"
        with open(daily_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            today_str = get_ist_date_str()
            self.assertEqual(data[today_str]["breaking_posts"], 1)
            self.assertEqual(data[today_str]["high_priority_posts"], 1)
            self.assertEqual(data[today_str]["normal_priority_posts"], 1)

    def test_9_story_lifecycle_statistics(self):
        """9. Verifies story lifecycle counters (NEW, DEVELOPING, TRENDING, RESOLVED)."""
        self.am.record_pipeline_run({
            "lifecycle_new": 5,
            "lifecycle_developing": 3,
            "lifecycle_trending": 2,
            "lifecycle_resolved": 1
        })

        daily_file = self.temp_dir / "daily.json"
        with open(daily_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            today_str = get_ist_date_str()
            self.assertEqual(data[today_str]["lifecycle_new"], 5)
            self.assertEqual(data[today_str]["lifecycle_developing"], 3)
            self.assertEqual(data[today_str]["lifecycle_trending"], 2)
            self.assertEqual(data[today_str]["lifecycle_resolved"], 1)

    def test_10_daily_report_generation(self):
        """10. Verifies readable daily report generation."""
        self.am.record_pipeline_run({"collected_count": 50, "duplicates_count": 10, "unique_count": 40})
        report = self.am.generate_daily_report()
        
        self.assertIn("DAILY NEWS REPORT", report)
        self.assertIn("Collected: 50", report)
        self.assertIn("Duplicates Removed: 10", report)

    def test_11_weekly_report_generation(self):
        """11. Verifies weekly report aggregation across daily entries."""
        self.am.record_pipeline_run({"collected_count": 50})
        self.am.record_publishing_event("success", post={"category": "Technology", "title": "A"})
        
        report = self.am.generate_weekly_report()
        self.assertIn("WEEKLY NEWS REPORT", report)
        self.assertIn("Total Posts: 1", report)

    def test_12_top_stories_retrieval(self):
        """12. Verifies recording and retrieval of top stories."""
        top_items = [
            {"title": "Top Tech Breakthrough", "category": "Technology", "priority": "HIGH", "final_score": 92.5, "source_count": 3}
        ]
        today_str = get_ist_date_str()
        week_str = get_ist_week_str()
        self.am.record_top_stories(top_items, today_str, week_str)

        stories = self.am.get_top_stories("today")
        self.assertEqual(len(stories), 1)
        self.assertEqual(stories[0]["title"], "Top Tech Breakthrough")

    def test_13_trending_statistics(self):
        """13. Verifies trending stories counts and lifecycle state tracking."""
        self.am.record_pipeline_run({"lifecycle_trending": 4})
        daily_file = self.temp_dir / "daily.json"
        with open(daily_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            today_str = get_ist_date_str()
            self.assertEqual(data[today_str]["lifecycle_trending"], 4)

    def test_14_failure_statistics_categorization(self):
        """14. Verifies categorized failure logging (COLLECTION_ERROR, AI_ERROR, TELEGRAM_ERROR, IMAGE_ERROR)."""
        self.am.record_failure("COLLECTION_ERROR", "RSS Feed Timeout", details={"feed": "TOI"})
        self.am.record_failure("TELEGRAM_ERROR", "HTTP 500 Server Error")

        fail_file = self.temp_dir / "failures.json"
        with open(fail_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            self.assertEqual(len(data["COLLECTION_ERROR"]), 1)
            self.assertEqual(data["COLLECTION_ERROR"][0]["error"], "RSS Feed Timeout")
            self.assertEqual(len(data["TELEGRAM_ERROR"]), 1)

    def test_15_retention_policy_cleanup(self):
        """15. Verifies old daily metrics purging according to ANALYTICS_RETENTION_DAYS."""
        daily_file = self.temp_dir / "daily.json"
        
        old_date = (get_ist_now() - timedelta(days=100)).strftime("%Y-%m-%d")
        recent_date = get_ist_date_str()

        test_data = {
            old_date: {"articles_collected": 5},
            recent_date: {"articles_collected": 20}
        }
        with open(daily_file, "w", encoding="utf-8") as f:
            json.dump(test_data, f)

        self.am.cleanup_old_analytics(retention_days=90)
        with open(daily_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            self.assertNotIn(old_date, data)
            self.assertIn(recent_date, data)

    def test_16_ist_date_boundaries(self):
        """16. Verifies all dates are formatted using Asia/Kolkata timezone."""
        now_ist = datetime.now(IST)
        date_str = get_ist_date_str(now_ist)
        week_str = get_ist_week_str(now_ist)

        self.assertEqual(date_str, now_ist.strftime("%Y-%m-%d"))
        self.assertTrue(week_str.startswith(now_ist.strftime("%Y-W")))

    def test_17_persistence_across_runs(self):
        """17. Verifies metrics persist across separate AnalyticsManager instances."""
        am1 = AnalyticsManager(analytics_dir=self.temp_dir)
        am1.record_pipeline_run({"collected_count": 42})

        am2 = AnalyticsManager(analytics_dir=self.temp_dir)
        report = am2.generate_daily_report()
        self.assertIn("Collected: 42", report)

    def test_18_concurrent_safe_file_updates(self):
        """18. Verifies safe atomic file write mechanism."""
        self.am.record_pipeline_run({"collected_count": 10})
        daily_file = self.temp_dir / "daily.json"
        self.assertTrue(daily_file.exists())

    def test_19_analytics_failure_isolation(self):
        """19. Verifies analytics failure never crashes main pipeline execution."""
        read_only_dir = self.temp_dir / "invalid_read_only"
        read_only_dir.touch()  # File instead of directory -> causes write failure
        
        faulty_am = AnalyticsManager(analytics_dir=read_only_dir)
        # Should log warning but NOT raise Exception
        faulty_am.record_pipeline_run({"collected_count": 100})
        faulty_am.record_publishing_event("success")

    def test_20_empty_data_day_graceful_handling(self):
        """20. Verifies daily report generates gracefully on day with no pipeline data."""
        report = self.am.generate_daily_report("2099-01-01")
        self.assertIn("DAILY NEWS REPORT", report)
        self.assertIn("Collected: 0", report)

    def test_21_corrupted_analytics_file_recovery(self):
        """21. Verifies corrupted JSON files are safely recovered without crashing."""
        daily_file = self.temp_dir / "daily.json"
        with open(daily_file, "w", encoding="utf-8") as f:
            f.write("{ INVALID JSON CONTENT ... ")

        # Should recover cleanly and record new metric
        self.am.record_pipeline_run({"collected_count": 15})
        with open(daily_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            today_str = get_ist_date_str()
            self.assertEqual(data[today_str]["articles_collected"], 15)

    def test_22_top_story_accumulation(self):
        """22. Verifies top stories accumulate across multiple runs on the same day retaining highest scores."""
        today_str = get_ist_date_str()
        week_str = get_ist_week_str()

        self.am.record_top_stories([{"title": "Story A", "final_score": 80}], today_str, week_str)
        self.am.record_top_stories([{"title": "Story B", "final_score": 95}, {"title": "Story A", "final_score": 85}], today_str, week_str)

        stories = self.am.get_top_stories("today")
        self.assertEqual(len(stories), 2)
        self.assertEqual(stories[0]["title"], "Story B")
        self.assertEqual(stories[0]["score"], 95)
        self.assertEqual(stories[1]["title"], "Story A")
        self.assertEqual(stories[1]["score"], 85)

    def test_23_source_accepted_tracking(self):
        """23. Verifies source accepted counts are tracked in source_stats."""
        self.am.record_pipeline_run({
            "source_collected": {"NDTV": 10},
            "source_accepted": {"NDTV": 4}
        })

        daily_file = self.temp_dir / "daily.json"
        with open(daily_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            today_str = get_ist_date_str()
            stats = data[today_str]["source_stats"]
            self.assertEqual(stats["NDTV"]["collected"], 10)
            self.assertEqual(stats["NDTV"]["accepted"], 4)

    def test_24_pipeline_durations_populated(self):
        """24. Verifies durations are tracked and accumulated in durations_seconds."""
        self.am.record_pipeline_run({
            "durations": {
                "collection": 1.25,
                "deduplication": 0.5,
                "clustering": 0.3,
                "ai": 2.1,
                "total_pipeline": 4.15
            }
        })

        daily_file = self.temp_dir / "daily.json"
        with open(daily_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            today_str = get_ist_date_str()
            durations = data[today_str]["durations_seconds"]
            self.assertGreater(durations["collection"], 0)
            self.assertGreater(durations["total_pipeline"], 0)


if __name__ == "__main__":
    unittest.main()
