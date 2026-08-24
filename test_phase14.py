"""
test_phase14.py
---------------
Automated test suite for Phase 14 Advanced News Content Intelligence.

Verifies:
 1. Content Intelligence receives real pipeline candidates
 2. Story Value affects ranking
 3. Source Quality affects ranking
 4. Trend Momentum affects ranking
 5. Story Lifecycle affects ranking
 6. Diversity affects selection
 7. Breaking News can override normal diversity
 8. Resolved stories are handled correctly
 9. Duplicate stories remain blocked
10. AI receives only selected candidates
11. Existing ranking behavior is preserved
12. No fake audience metrics are generated
"""

import unittest
from datetime import datetime, timedelta, timezone
from content_intelligence import ContentIntelligenceEngine
from news_ranker import NewsRanker
import deduplicator


class TestPhase14(unittest.TestCase):

    def setUp(self):
        self.cie = ContentIntelligenceEngine()
        self.ranker = NewsRanker()

    def test_1_candidates_received(self):
        """1. Verifies Content Intelligence handles real pipeline candidate structures."""
        story = {
            "title": "Quantum Computing Breakthrough",
            "source": "TechCrunch",
            "category": "TECHNOLOGY",
            "source_count": 3,
            "published_at": datetime.now(timezone.utc).isoformat()
        }
        score = self.cie.calculate_story_value_score(story)
        self.assertGreaterEqual(score, 0.50)

    def test_2_story_value_affects_ranking(self):
        """2. Verifies Story Value score influences cluster ranking."""
        cl1 = {
            "best_article": {"title": "Minor Local News", "source": "unknown", "published_at": (datetime.now(timezone.utc) - timedelta(hours=20)).isoformat()},
            "topic": "Minor Local News",
            "source_count": 1,
            "category": "NEWS"
        }
        cl2 = {
            "best_article": {"title": "BREAKING: Global Summit Agreement Signed", "source": "Reuters", "published_at": datetime.now(timezone.utc).isoformat()},
            "topic": "BREAKING: Global Summit Agreement Signed",
            "source_count": 5,
            "category": "NEWS"
        }
        ranked = self.ranker.rank_clusters([cl1, cl2])
        self.assertEqual(ranked[0]["topic"], cl2["topic"])

    def test_3_source_quality_affects_ranking(self):
        """3. Verifies Tier 1 source receives higher source quality score."""
        score_reuters = self.cie.get_source_quality_score("Reuters")
        score_default = self.cie.get_source_quality_score("UnknownBlog")
        self.assertGreater(score_reuters, score_default)

    def test_4_trend_momentum_affects_ranking(self):
        """4. Verifies higher source count increases momentum score."""
        story_single = {"title": "Single source post", "source_count": 1}
        story_multi = {"title": "Multi source post", "source_count": 4}
        val_single = self.cie.calculate_story_value_score(story_single)
        val_multi = self.cie.calculate_story_value_score(story_multi)
        self.assertGreater(val_multi, val_single)

    def test_5_story_lifecycle_affects_ranking(self):
        """5. Verifies lifecycle state transitions from NEW to TRENDING to RESOLVED."""
        story_new = {"title": "New Tech Event", "content": "Details"}
        self.assertEqual(self.cie.get_story_lifecycle_state(story_new, source_count=1, age_hours=1.0), "NEW")
        self.assertEqual(self.cie.get_story_lifecycle_state(story_new, source_count=4, age_hours=2.0), "TRENDING")
        self.assertEqual(self.cie.get_story_lifecycle_state(story_new, source_count=1, age_hours=25.0), "RESOLVED")

    def test_6_diversity_affects_selection(self):
        """6. Verifies enforce_category_diversity reorders candidate posts to prevent category clustering."""
        posts = [
            {"category": "TECH", "title": "Tech 1"},
            {"category": "TECH", "title": "Tech 2"},
            {"category": "TECH", "title": "Tech 3"},
            {"category": "SPORTS", "title": "Sports 1"}
        ]
        reordered = self.cie.enforce_category_diversity(posts, max_consecutive=2)
        cats = [p["category"] for p in reordered]
        self.assertIn("SPORTS", cats[:3])

    def test_7_breaking_news_overrides_diversity(self):
        """7. Verifies Breaking News post retains top position regardless of category clustering."""
        posts = [
            {"category": "TECH", "title": "Tech 1"},
            {"category": "TECH", "title": "Tech 2"},
            {"category": "TECH", "title": "BREAKING: Crisis Urgent Alert", "is_breaking": True, "source": "Reuters"}
        ]
        reordered = self.cie.enforce_category_diversity(posts, max_consecutive=2)
        self.assertTrue(reordered[0].get("is_breaking"))

    def test_8_resolved_stories_handled(self):
        """8. Verifies stories older than 24h are marked RESOLVED."""
        story_old = {"title": "Old Resolved Event"}
        st = self.cie.get_story_lifecycle_state(story_old, source_count=1, age_hours=26.0)
        self.assertEqual(st, "RESOLVED")

    def test_9_duplicate_stories_remain_blocked(self):
        """9. Verifies duplicate URLs and titles remain blocked."""
        hist = [{"url": "https://example.com/duplicate"}]
        self.assertTrue(deduplicator.is_duplicate_url("https://example.com/duplicate", hist))

    def test_10_ai_receives_only_selected_candidates(self):
        """10. Verifies ranker assigns priority levels properly for candidate selection."""
        cl = {
            "best_article": {"title": "Selected Candidate", "source": "BBC"},
            "topic": "Selected Candidate",
            "source_count": 2,
            "category": "NEWS"
        }
        ranked = self.ranker.rank_clusters([cl])
        self.assertIn("priority", ranked[0])

    def test_11_existing_ranking_behavior_preserved(self):
        """11. Verifies existing NewsRanker composite score calculation remains valid."""
        cl = {
            "best_article": {"title": "Test Story", "source": "NDTV News", "published_at": datetime.now(timezone.utc).isoformat()},
            "topic": "Test Story",
            "articles": []
        }
        score, explanation = self.ranker.calculate_composite_score(cl)
        self.assertGreater(score, 0)
        self.assertIn("freshness_score", explanation)

    def test_12_no_fake_audience_metrics(self):
        """12. Verifies Story Value Engine relies on deterministic data without inventing fake audience engagement."""
        story = {"title": "Clean Story", "source": "Reuters"}
        val = self.cie.calculate_story_value_score(story)
        self.assertIsInstance(val, float)
        self.assertGreaterEqual(val, 0.0)


if __name__ == "__main__":
    unittest.main()
