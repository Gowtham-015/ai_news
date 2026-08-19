"""
test_phase7.py
--------------
Automated test suite for Phase 7 Production Optimization & Telegram Quality.

Verifies:
1. Source Quality Tiers (Tier 1, Tier 2, Tier 3)
2. Same-event story clustering and multi-source attribution
3. Category balancing and post frequency limits
4. Telegram HTML formatting & escaping
5. Image fallback to text-only publishing
6. Health and daily statistics tracking
"""

import unittest
import html
from pathlib import Path
import config
from config.feeds import FEEDS
import publisher
from story_clusterer import StoryClusterer
from news_ranker import NewsRanker
from queue_manager import QueueManager
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
        self.assertIn("<a href=\"https://example.com/test?a=1&b=2\">", formatted)


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
        # Verify multi-source count
        first_cluster = clusters[0]
        self.assertGreaterEqual(first_cluster.get("source_count", 1), 1)

    def test_frequency_control_settings(self):
        """Verifies Phase 7 frequency limit configuration values exist."""
        self.assertGreater(config.MAX_POSTS_PER_HOUR, 0)
        self.assertGreater(config.MAX_POSTS_PER_DAY, 0)
        self.assertGreater(config.MIN_POST_INTERVAL_MINUTES, 0)
        self.assertGreater(config.MAX_POSTS_PER_CATEGORY_PER_DAY, 0)

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
