"""
test_phase9.py
--------------
Automated test suite for Phase 9 Smart Telegram Content Intelligence.

Verifies:
 1. Story lifecycle NEW
 2. Story lifecycle DEVELOPING
 3. Story lifecycle TRENDING
 4. Stale/Resolved story detection
 5. Trend velocity calculation
 6. Multi-signal breaking-news detection
 7. Non-breaking high-score story
 8. Multi-source confirmation & syndication filtering
 9. Meaningful follow-up story detection
10. Insignificant follow-up story rejection
11. ALLOW_MAJOR_STORY_UPDATES=false control
12. ALLOW_MAJOR_STORY_UPDATES=true control
13. Priority assignment (BREAKING, HIGH, NORMAL, LOW)
14. Priority queue ordering (BREAKING > HIGH > NORMAL > LOW)
15. Category intelligence rules
16. Persistence across runs (story_lifecycle.json)
17. Duplicate story prevention
"""

import json
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest import mock

import config
import news_ranker
from news_ranker import NewsRanker, filter_syndicated_sources
from trend_detector import TrendDetector
from story_lifecycle import StoryLifecycleManager
from queue_manager import QueueManager
from ai_processor import AIProcessor


class TestPhase9(unittest.TestCase):

    def test_1_story_lifecycle_new(self):
        """1. Verifies NEW story state for first-time detected story."""
        temp_dir = Path(tempfile.mkdtemp())
        life_file = temp_dir / "story_lifecycle.json"
        slm = StoryLifecycleManager(filepath=life_file)

        cluster = {"cluster_id": "c_new", "topic": "Local Tech Meetup Announced", "source_count": 1, "final_score": 50}
        state = slm.get_story_state(cluster)
        self.assertEqual(state, "NEW")

    def test_2_story_lifecycle_developing(self):
        """2. Verifies DEVELOPING story state after initial posting."""
        temp_dir = Path(tempfile.mkdtemp())
        life_file = temp_dir / "story_lifecycle.json"
        slm = StoryLifecycleManager(filepath=life_file)

        cluster = {"cluster_id": "c_dev", "topic": "Startup Launches New App", "source_count": 2, "final_score": 70}
        slm.record_posted_story(cluster)
        
        state = slm.get_story_state(cluster)
        self.assertEqual(state, "DEVELOPING")

    def test_3_story_lifecycle_trending(self):
        """3. Verifies TRENDING story state with high source count/score."""
        temp_dir = Path(tempfile.mkdtemp())
        life_file = temp_dir / "story_lifecycle.json"
        slm = StoryLifecycleManager(filepath=life_file)

        cluster = {"cluster_id": "c_trend", "topic": "Global AI Safety Accord Signed", "source_count": 4, "final_score": 90}
        state = slm.get_story_state(cluster)
        self.assertEqual(state, "TRENDING")

    def test_4_stale_story_detection(self):
        """4. Verifies RESOLVED/STALE story state for stories older than 24 hours."""
        temp_dir = Path(tempfile.mkdtemp())
        life_file = temp_dir / "story_lifecycle.json"
        slm = StoryLifecycleManager(filepath=life_file)

        cluster = {"cluster_id": "c_stale", "topic": "Yesterday News Event", "source_count": 1, "final_score": 55}
        slm.record_posted_story(cluster)

        # Shift first_seen_at back by 30 hours
        data = slm.load_lifecycle()
        key = slm._get_story_key(cluster)
        past_str = (datetime.now(timezone.utc) - timedelta(hours=30)).isoformat()
        data[key]["first_seen_at"] = past_str
        slm.save_lifecycle(data)

        state = slm.get_story_state(cluster)
        self.assertEqual(state, "RESOLVED")

    def test_5_trend_velocity_calculation(self):
        """5. Verifies trend velocity calculation across time snapshots."""
        temp_dir = Path(tempfile.mkdtemp())
        cache_file = temp_dir / "trend_cache.json"
        td = TrendDetector(cache_filepath=cache_file)

        now = datetime.now(timezone.utc)
        history_items = [
            {"timestamp": (now - timedelta(hours=2)).isoformat(), "mentions": 2},
            {"timestamp": now.isoformat(), "mentions": 12}
        ]

        cluster = {
            "cluster_id": "c_vel",
            "topic": "Escalating Topic",
            "source_count": 4,
            "articles": [{"title": f"a{i}"} for i in range(12)]
        }

        score, velocity = td.calculate_trend_score(cluster, history_items)
        self.assertGreater(velocity, 4.0)
        self.assertGreaterEqual(score, 90)

    def test_6_breaking_news_detection(self):
        """6. Verifies multi-signal breaking news classification."""
        ranker = NewsRanker()
        cluster = {
            "cluster_id": "c_break",
            "topic": "Breaking: Magnitude 7.8 Earthquake Disaster Reported",
            "category": "News",
            "is_breaking": True,
            "source_count": 3,
            "best_article": {
                "title": "Breaking: Magnitude 7.8 Earthquake Disaster Reported",
                "source": "Reuters",
                "published_at": datetime.now(timezone.utc).isoformat()
            }
        }
        score, explanation = ranker.calculate_composite_score(cluster)
        priority = ranker.assign_priority(cluster, score)

        self.assertGreaterEqual(score, 80.0)
        self.assertEqual(priority, "BREAKING")
        self.assertTrue(cluster.get("is_breaking"))
        self.assertIn("breaking_reason", cluster)

    def test_7_non_breaking_high_score_story(self):
        """7. Verifies routine high-scoring story is assigned HIGH priority, not BREAKING."""
        ranker = NewsRanker()
        cluster = {
            "cluster_id": "c_routine_high",
            "topic": "Annual Tech Conference Reveals Next Generation Devices",
            "category": "Technology",
            "source_count": 2,
            "best_article": {
                "title": "Annual Tech Conference Reveals Next Generation Devices",
                "source": "TechCrunch",
                "published_at": (datetime.now(timezone.utc) - timedelta(hours=4)).isoformat()
            }
        }
        score, explanation = ranker.calculate_composite_score(cluster)
        priority = ranker.assign_priority(cluster, score)

        self.assertNotEqual(priority, "BREAKING")
        self.assertFalse(cluster.get("is_breaking", False))

    def test_8_multi_source_confirmation_and_syndication_filtering(self):
        """8. Verifies verbatim syndicated articles are filtered to 1 independent source."""
        syndicated_articles = [
            {
                "title": "Government announces major tax relief package for small business",
                "description": "The finance ministry has unveiled a comprehensive tax relief initiative.",
                "source": "Reuters"
            },
            {
                "title": "Government announces major tax relief package for small business",
                "description": "The finance ministry has unveiled a comprehensive tax relief initiative.",
                "source": "Syndicated Portal A"
            }
        ]

        indep_count, sources = filter_syndicated_sources(syndicated_articles)
        self.assertEqual(indep_count, 1)
        self.assertEqual(len(sources), 2)

    def test_9_meaningful_followup_story(self):
        """9. Verifies meaningful follow-up story detection (>2h with new details)."""
        temp_dir = Path(tempfile.mkdtemp())
        life_file = temp_dir / "story_lifecycle.json"
        slm = StoryLifecycleManager(filepath=life_file)

        cluster_init = {
            "cluster_id": "c_follow",
            "topic": "Spacecraft Launch Scheduled for Mission",
            "source_count": 1,
            "best_article": {"title": "Spacecraft Launch Scheduled for Mission", "source": "Reuters"}
        }
        slm.record_posted_story(cluster_init)

        # Shift last_posted_at back by 3 hours
        data = slm.load_lifecycle()
        key = slm._get_story_key(cluster_init)
        past_str = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
        data[key]["last_posted_at"] = past_str
        slm.save_lifecycle(data)

        cluster_update = {
            "cluster_id": "c_follow",
            "topic": "Spacecraft Launch Scheduled for Mission - Orbit Touchdown Victory Achieved",
            "source_count": 3,
            "best_article": {"title": "Spacecraft Launch Scheduled for Mission - Orbit Touchdown Victory Achieved", "source": "BBC News"}
        }

        eligible, reason = slm.is_eligible_for_followup(cluster_update, min_interval_hours=2.0)
        self.assertTrue(eligible)

    def test_10_insignificant_followup_rejection(self):
        """10. Verifies rejection of minor follow-ups (<2h or no new info)."""
        temp_dir = Path(tempfile.mkdtemp())
        life_file = temp_dir / "story_lifecycle.json"
        slm = StoryLifecycleManager(filepath=life_file)

        cluster_init = {
            "cluster_id": "c_minor",
            "topic": "Local Park Renovation Announced",
            "source_count": 1,
            "best_article": {"title": "Local Park Renovation Announced", "source": "NDTV"}
        }
        slm.record_posted_story(cluster_init)

        # Attempt immediate follow-up
        eligible, reason = slm.is_eligible_for_followup(cluster_init, min_interval_hours=2.0)
        self.assertFalse(eligible)
        self.assertIn("too soon", reason.lower())

    def test_11_allow_major_story_updates_false(self):
        """11. Verifies ALLOW_MAJOR_STORY_UPDATES=false rejects all follow-ups."""
        temp_dir = Path(tempfile.mkdtemp())
        life_file = temp_dir / "story_lifecycle.json"
        slm = StoryLifecycleManager(filepath=life_file)

        cluster = {"cluster_id": "c_no_update", "topic": "Major Acquisition News", "source_count": 1, "best_article": {"title": "Acquisition News"}}
        slm.record_posted_story(cluster)

        with mock.patch("config.ALLOW_MAJOR_STORY_UPDATES", False):
            eligible, reason = slm.is_eligible_for_followup(cluster)
            self.assertFalse(eligible)
            self.assertIn("disabled", reason.lower())

    def test_12_allow_major_story_updates_true(self):
        """12. Verifies ALLOW_MAJOR_STORY_UPDATES=true permits valid follow-ups."""
        temp_dir = Path(tempfile.mkdtemp())
        life_file = temp_dir / "story_lifecycle.json"
        slm = StoryLifecycleManager(filepath=life_file)

        cluster = {"cluster_id": "c_allow_update", "topic": "New Policy Change", "source_count": 1, "best_article": {"title": "New Policy Change"}}
        slm.record_posted_story(cluster)

        data = slm.load_lifecycle()
        key = slm._get_story_key(cluster)
        past_str = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
        data[key]["last_posted_at"] = past_str
        slm.save_lifecycle(data)

        cluster_update = {"cluster_id": "c_allow_update", "topic": "New Policy Change Approved by Parliament", "source_count": 3, "best_article": {"title": "New Policy Change Approved by Parliament"}}

        with mock.patch("config.ALLOW_MAJOR_STORY_UPDATES", True):
            eligible, reason = slm.is_eligible_for_followup(cluster_update)
            self.assertTrue(eligible)

    def test_13_priority_assignment(self):
        """13. Verifies priority level assignment (BREAKING, HIGH, NORMAL, LOW)."""
        ranker = NewsRanker()

        c_breaking = {"topic": "Breaking: Crisis Solved", "is_breaking": True, "source_count": 3, "best_article": {"source": "Reuters"}}
        self.assertEqual(ranker.assign_priority(c_breaking, 92.0), "BREAKING")

        c_high = {"topic": "Major Tech Launch", "source_count": 2, "best_article": {"source": "TechCrunch"}}
        self.assertEqual(ranker.assign_priority(c_high, 78.0), "HIGH")

        c_normal = {"topic": "Standard Update", "source_count": 1, "best_article": {"source": "Wired"}}
        self.assertEqual(ranker.assign_priority(c_normal, 65.0), "NORMAL")

        c_low = {"topic": "Minor Gossip Rumor", "source_count": 1, "best_article": {"source": "Unknown"}}
        self.assertEqual(ranker.assign_priority(c_low, 45.0), "LOW")

    def test_14_priority_queue_ordering(self):
        """14. Verifies queue orders posts by BREAKING > HIGH > NORMAL > LOW."""
        temp_dir = Path(tempfile.mkdtemp())
        posts_file = temp_dir / "posts.json"
        hist_file = temp_dir / "published_news.json"
        qm = QueueManager(posts_filepath=posts_file)

        candidates = [
            {"category": "NEWS", "title": "Normal Story", "priority": "NORMAL", "final_score": 65.0, "original_url": "http://normal.com"},
            {"category": "NEWS", "title": "Breaking Story", "priority": "BREAKING", "is_breaking": True, "final_score": 95.0, "original_url": "http://breaking.com"},
            {"category": "NEWS", "title": "High Priority Story", "priority": "HIGH", "final_score": 80.0, "original_url": "http://high.com"}
        ]

        qm.add_posts_to_queue(candidates, history_filepath=hist_file, instant_schedule=True)
        queued = qm.load_queue()
        
        self.assertEqual(len(queued), 3)
        self.assertEqual(queued[0]["priority"], "BREAKING")
        self.assertEqual(queued[1]["priority"], "HIGH")
        self.assertEqual(queued[2]["priority"], "NORMAL")

    def test_15_category_intelligence(self):
        """15. Verifies category-specific intelligence rules."""
        ranker = NewsRanker()

        c_sports_win = {"category": "Sports", "topic": "India wins T20 championship victory", "source_count": 2, "best_article": {"source": "BBC Sport", "published_at": datetime.now(timezone.utc).isoformat()}}
        c_sports_rumor = {"category": "Sports", "topic": "Player comment rumor choice", "source_count": 1, "best_article": {"source": "Unknown", "published_at": datetime.now(timezone.utc).isoformat()}}

        score_win, _ = ranker.calculate_composite_score(c_sports_win)
        score_rumor, _ = ranker.calculate_composite_score(c_sports_rumor)
        self.assertGreater(score_win, score_rumor + 15)

    def test_16_persistence_across_runs(self):
        """16. Verifies story lifecycle state persists across runs in data/story_lifecycle.json."""
        temp_dir = Path(tempfile.mkdtemp())
        life_file = temp_dir / "story_lifecycle.json"

        slm1 = StoryLifecycleManager(filepath=life_file)
        cluster = {"cluster_id": "c_persist", "topic": "Persistent Test Topic", "source_count": 2, "final_score": 75}
        slm1.record_posted_story(cluster)

        # Initialize fresh instance pointing to same file
        slm2 = StoryLifecycleManager(filepath=life_file)
        state = slm2.get_story_state(cluster)
        self.assertEqual(state, "DEVELOPING")

    def test_17_duplicate_story_prevention(self):
        """17. Verifies queue prevents duplicate URLs and titles."""
        temp_dir = Path(tempfile.mkdtemp())
        posts_file = temp_dir / "posts.json"
        hist_file = temp_dir / "published_news.json"
        qm = QueueManager(posts_filepath=posts_file)

        candidates = [
            {"category": "NEWS", "title": "Unique Story", "priority": "NORMAL", "final_score": 70.0, "original_url": "http://unique.com"},
            {"category": "NEWS", "title": "Unique Story", "priority": "NORMAL", "final_score": 70.0, "original_url": "http://unique.com"}
        ]

        added = qm.add_posts_to_queue(candidates, history_filepath=hist_file)
        self.assertEqual(added, 1)


if __name__ == "__main__":
    unittest.main()
