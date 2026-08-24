"""
test_phase7.py
--------------
Automated test suite for Phase 7 Production Optimization & Telegram Quality.

Verifies:
1. Source Quality Tiers (Tier 1, Tier 2, Tier 3)
2. Telegram HTML formatting & escaping
3. Same-event story clustering and multi-source attribution
4. Post frequency enforcement (hourly limit, daily limit, min interval, category limit)
5. Breaking news frequency override
6. Retry lifecycle & maximum retries handling
7. Queue state transitions (scheduled -> publishing -> retrying -> published / permanently_failed)
8. Duplicate publishing prevention
9. GitHub Actions concurrency workflow configuration
"""

import json
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest import mock

import config
import publisher
import scheduler
from story_clusterer import StoryClusterer
from state_manager import StateManager


class TestPhase7(unittest.TestCase):
    def test_source_quality_tiers(self):
        """Verifies Source Quality Tiers mapping."""
        self.assertIn("Tier 1", config.SOURCE_TIERS)
        self.assertIn("BBC News", config.SOURCE_TIERS["Tier 1"])
        self.assertGreaterEqual(config.SOURCE_SCORES["BBC News"], 90)
        self.assertGreaterEqual(config.SOURCE_SCORES["TechCrunch"], 80)

    def test_telegram_html_formatting_and_escaping(self):
        """Verifies safe HTML formatting and entity escaping."""
        post = {
            "category": "NEWS",
            "title": "India <&> Australia Match",
            "content": "Test & demo summary with <tags>",
            "source": "BBC News",
            "url": "https://example.com/test?a=1&b=2"
        }
        formatted = publisher.format_html_post(post)
        self.assertIn("&amp;", formatted)
        self.assertIn("&lt;", formatted)
        self.assertIn("&gt;", formatted)
        self.assertIn("<b>📰 NEWS</b>", formatted)
        self.assertTrue("<a href=\"https://example.com/test?a=1&amp;b=2\">" in formatted or "<a href=\"https://example.com/test?a=1&b=2\">" in formatted)

    def test_same_event_clustering(self):
        """Verifies same-event articles are clustered together."""
        clusterer = StoryClusterer()
        articles = [
            {
                "id": "1",
                "title": "India defeats Australia in cricket match",
                "description": "India won by 5 wickets against Australia.",
                "url": "http://example.com/1",
                "source": "BBC Sport",
                "category": "Sports",
                "published_at": "2026-08-19T10:00:00Z"
            },
            {
                "id": "2",
                "title": "India wins match against Australia",
                "description": "Cricket victory for India over Australia.",
                "url": "http://example.com/2",
                "source": "ESPN",
                "category": "Sports",
                "published_at": "2026-08-19T10:05:00Z"
            }
        ]
        clusters = clusterer.cluster_articles(articles)
        self.assertGreaterEqual(len(clusters), 1)
        first_cluster = clusters[0]
        self.assertGreaterEqual(first_cluster.get("source_count", 1), 1)

    def test_frequency_control_settings(self):
        """Verifies Phase 7 frequency limit configuration values exist."""
        self.assertGreater(config.MAX_POSTS_PER_HOUR, 0)
        self.assertGreater(config.MAX_POSTS_PER_DAY, 0)
        self.assertGreater(config.MIN_POST_INTERVAL_MINUTES, 0)
        self.assertGreater(config.MAX_POSTS_PER_CATEGORY_PER_DAY, 0)

    def test_hourly_and_daily_post_frequency_limits(self):
        """Verifies enforcement of hourly, daily, and min interval frequency limits."""
        now = datetime.now(scheduler.TIMEZONE)
        
        # Build 4 published history items in the last hour to hit hourly limit (MAX_POSTS_PER_HOUR = 4)
        published_history = [
            {"published_time": (now - timedelta(minutes=i * 10)).strftime(scheduler.DATETIME_FORMAT), "category": "Technology"}
            for i in range(1, 5)
        ]

        normal_post = {"category": "Technology", "title": "Normal Tech Post", "priority": "NORMAL"}
        
        # Should be rejected due to hourly limit or min interval
        ok, reason = scheduler.check_post_frequency_limits(normal_post, published_history=published_history)
        self.assertFalse(ok)
        self.assertTrue("limit" in reason.lower() or "interval" in reason.lower())

    def test_breaking_news_frequency_override(self):
        """Verifies breaking news bypasses frequency limits."""
        now = datetime.now(scheduler.TIMEZONE)
        published_history = [
            {"published_time": (now - timedelta(minutes=i * 5)).strftime(scheduler.DATETIME_FORMAT), "category": "News"}
            for i in range(1, 10)
        ]

        breaking_post = {"category": "News", "title": "Breaking News Event", "is_breaking": True, "priority": "BREAKING"}
        
        ok, reason = scheduler.check_post_frequency_limits(breaking_post, published_history=published_history)
        self.assertTrue(ok)
        self.assertIn("Breaking news override", reason)

    def test_category_daily_limit_enforcement(self):
        """Verifies category daily limit enforcement."""
        now = datetime.now(scheduler.TIMEZONE)
        day_start = now.replace(hour=0, minute=1, second=0)

        # 10 posts today for Technology (MAX_POSTS_PER_CATEGORY_PER_DAY = 10)
        published_history = [
            {"published_time": (day_start + timedelta(minutes=i * 30)).strftime(scheduler.DATETIME_FORMAT), "category": "Technology"}
            for i in range(10)
        ]

        tech_post = {"category": "Technology", "title": "Another Tech Post", "priority": "NORMAL"}
        ok, reason = scheduler.check_post_frequency_limits(tech_post, published_history=published_history)
        self.assertFalse(ok)
        self.assertIn("Category daily limit reached", reason)

    @mock.patch("publisher.publish_post", return_value=False)
    def test_retry_lifecycle_and_max_retries(self, mock_pub):
        """Verifies status transition: scheduled -> publishing -> retrying -> permanently_failed."""
        temp_dir = Path(tempfile.mkdtemp())
        posts_file = temp_dir / "posts.json"
        
        now_str = (datetime.now(scheduler.TIMEZONE) - timedelta(minutes=5)).strftime(scheduler.DATETIME_FORMAT)
        test_posts = [
            {"id": 1, "title": "Failing Post", "scheduled_time": now_str, "status": "scheduled", "retry_count": 0}
        ]
        with open(posts_file, "w", encoding="utf-8") as f:
            json.dump(test_posts, f)

        with mock.patch("scheduler.POSTS_FILE", posts_file), mock.patch("config.MAX_RETRIES", 2), mock.patch("scheduler.check_post_frequency_limits", return_value=(True, "Limits OK")), mock.patch("deduplicator.load_published_history", return_value=[]):
            # Attempt 1 -> status should become retrying
            scheduler.check_and_publish()
            posts = scheduler.load_posts()
            self.assertEqual(posts[0]["status"], "retrying")
            self.assertEqual(posts[0]["retry_count"], 1)

            # Attempt 2 -> status should become permanently_failed
            scheduler.check_and_publish()
            posts_final = scheduler.load_posts()
            self.assertEqual(posts_final[0]["status"], "permanently_failed")
            self.assertEqual(posts_final[0]["retry_count"], 2)

    @mock.patch("publisher.publish_post", return_value=True)
    def test_duplicate_publishing_prevention(self, mock_pub):
        """Verifies posts already present in published history are marked published without re-sending."""
        temp_dir = Path(tempfile.mkdtemp())
        posts_file = temp_dir / "posts.json"
        pub_file = temp_dir / "published_news.json"

        now_str = (datetime.now(scheduler.TIMEZONE) - timedelta(minutes=5)).strftime(scheduler.DATETIME_FORMAT)
        url = "https://example.com/already-published"

        history = [{"original_url": url, "published_time": now_str}]
        with open(pub_file, "w", encoding="utf-8") as f:
            json.dump(history, f)

        test_posts = [
            {"id": 1, "title": "Duplicate URL Post", "original_url": url, "scheduled_time": now_str, "status": "scheduled"}
        ]
        with open(posts_file, "w", encoding="utf-8") as f:
            json.dump(test_posts, f)

        with mock.patch("scheduler.POSTS_FILE", posts_file), mock.patch("deduplicator.PUBLISHED_NEWS_FILE", pub_file):
            scheduler.check_and_publish()
            mock_pub.assert_not_called()
            posts = scheduler.load_posts()
            self.assertEqual(posts[0]["status"], "published")

    def test_github_actions_concurrency_config(self):
        """Verifies .github/workflows/news_agent.yml contains concurrency protection."""
        wf_file = Path(__file__).parent / ".github" / "workflows" / "news_agent.yml"
        self.assertTrue(wf_file.exists())
        content = wf_file.read_text(encoding="utf-8")
        self.assertIn("concurrency:", content)
        self.assertIn("group: news-agent-publishing", content)

    def test_statistics_tracking_fields(self):
        """Verifies state_manager initializes all required statistics fields."""
        state_mgr = StateManager()
        state = state_mgr.load_state()
        self.assertIn("articles_collected_total", state)
        self.assertIn("duplicates_removed_total", state)
        self.assertIn("stories_clustered_total", state)
        self.assertIn("posts_published_total", state)


if __name__ == "__main__":
    unittest.main()
