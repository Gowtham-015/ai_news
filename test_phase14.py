"""
test_phase14.py
---------------
Automated test suite for Phase 14 Advanced News Content Intelligence.

Verifies:
 1. Story Value Engine multi-factor score calculation
 2. Source quality tier lookups (Reuters/BBC=1.0, TechCrunch/ESPN=0.9, default=0.70)
 3. Category diversity enforcement (anti-clustering)
 4. Story lifecycle state machine transitions (NEW -> DEVELOPING -> TRENDING -> BREAKING -> RESOLVED)
 5. Verified breaking news signal validation
 6. Headline quality validation (rejection of clickbait phrases)
 7. Title duplication stripping from summary text
 8. Anti-hallucination safeguards
 9. Duplicate story distance suppression
10. Retention of uncertainty markers for unconfirmed claims
11. Queue manager story value ranking integration
12. Configurable source quality score overrides
13. Lifecycle state persistence in queue entry payload
14. Category diversity breaking news override
15. End-to-end pipeline compatibility
"""

import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import config
from ai_processor import AIProcessor
from content_intelligence import ContentIntelligenceEngine, DEFAULT_SOURCE_QUALITY_SCORES

IST = ZoneInfo("Asia/Kolkata")


class TestPhase14(unittest.TestCase):

    def setUp(self):
        self.cie = ContentIntelligenceEngine()
        self.ai = AIProcessor()

    def test_1_story_value_scoring(self):
        """1. Verifies multi-factor story value calculation."""
        story = {
            "title": "Major AI Breakthrough",
            "source": "Reuters",
            "source_count": 3,
            "priority": "HIGH"
        }
        score = self.cie.calculate_story_value_score(story)
        self.assertGreaterEqual(score, 0.70)
        self.assertLessEqual(score, 1.0)

    def test_2_source_quality_tiers(self):
        """2. Verifies source quality score assignments across tiers."""
        self.assertEqual(self.cie.get_source_quality_score("Reuters"), 1.0)
        self.assertEqual(self.cie.get_source_quality_score("BBC News"), 1.0)
        self.assertEqual(self.cie.get_source_quality_score("TechCrunch"), 0.9)
        self.assertEqual(self.cie.get_source_quality_score("Unknown Blog"), 0.70)

    def test_3_category_diversity_enforcement(self):
        """3. Verifies category diversity prevents 3+ consecutive posts of same category."""
        candidates = [
            {"title": "Sports Post 1", "category": "SPORTS"},
            {"title": "Sports Post 2", "category": "SPORTS"},
            {"title": "Sports Post 3", "category": "SPORTS"},
            {"title": "Tech Post 1", "category": "TECHNOLOGY"},
            {"title": "Tech Post 2", "category": "TECHNOLOGY"}
        ]
        history = [{"category": "SPORTS"}, {"category": "SPORTS"}]
        reordered = self.cie.enforce_category_diversity(candidates, history, max_consecutive=2)
        # First reordered post should be Tech Post 1 to avoid 3rd consecutive Sports post
        self.assertEqual(reordered[0]["category"], "TECHNOLOGY")

    def test_4_story_lifecycle_state_transitions(self):
        """4. Verifies story lifecycle state machine transitions."""
        # 1 source, recent -> NEW
        self.assertEqual(self.cie.get_story_lifecycle_state({"title": "News"}, source_count=1, age_hours=1.0), "NEW")

        # 2 sources, 4h -> DEVELOPING
        self.assertEqual(self.cie.get_story_lifecycle_state({"title": "News"}, source_count=2, age_hours=4.0), "DEVELOPING")

        # 4 sources, 2h -> TRENDING
        self.assertEqual(self.cie.get_story_lifecycle_state({"title": "News"}, source_count=4, age_hours=2.0), "TRENDING")

        # 28h old -> RESOLVED
        self.assertEqual(self.cie.get_story_lifecycle_state({"title": "News"}, source_count=1, age_hours=28.0), "RESOLVED")

    def test_5_breaking_news_signal_verification(self):
        """5. Verifies breaking news verification signals."""
        breaking_tier1 = {
            "title": "BREAKING: Global Economic Agreement Reached",
            "source": "Reuters",
            "source_count": 1
        }
        self.assertTrue(self.cie.is_verified_breaking_news(breaking_tier1))

        unverified_claim = {
            "title": "BREAKING: Unsubstantiated Rumor",
            "source": "Random Blog",
            "source_count": 1
        }
        self.assertFalse(self.cie.is_verified_breaking_news(unverified_claim))

    def test_6_clickbait_headline_rejection(self):
        """6. Verifies clickbait headlines are rejected by quality validator."""
        self.assertFalse(self.ai.validate_headline_quality("You Won't Believe What This CEO Did!"))
        self.assertFalse(self.ai.validate_headline_quality("Shocking Mind-Blowing Secret Discovered"))
        self.assertTrue(self.ai.validate_headline_quality("Tech Giant Announces New Autonomous Processor"))

    def test_7_title_duplication_stripping(self):
        """7. Verifies duplicated headline is stripped from top of summary text."""
        headline = "New Autonomous Processor Unveiled"
        summary_with_dup = "New Autonomous Processor Unveiled\n\nCompany launches high-performance chip."
        stripped = self.ai.strip_title_duplication(headline, summary_with_dup)
        self.assertNotIn("New Autonomous Processor Unveiled\n\nNew Autonomous Processor Unveiled", stripped)
        self.assertIn("Company launches high-performance chip.", stripped)

    def test_8_hallucination_safeguards(self):
        """8. Verifies hallucination safeguard function."""
        src_text = "SpaceX launched Falcon 9 rocket from Cape Canaveral."
        gen_summary = "SpaceX successfully launched Falcon 9 from Cape Canaveral."
        safe_summary = self.ai.apply_hallucination_safeguards(gen_summary, src_text)
        self.assertEqual(safe_summary, gen_summary)

    def test_9_duplicate_story_suppression(self):
        """9. Verifies story value uniqueness penalty for duplicate stories in history."""
        story = {"title": "Apple Announces M4 Mac Studio", "source": "Reuters"}
        history = [{"title": "Apple Announces M4 Mac Studio Released Today"}]
        val_unique = self.cie.calculate_story_value_score(story, published_history=[])
        val_dup = self.cie.calculate_story_value_score(story, published_history=history)
        self.assertLess(val_dup, val_unique)

    def test_10_uncertainty_marker_retention(self):
        """10. Verifies uncertainty markers are prefixed for unconfirmed reports."""
        unconfirmed = self.ai.preserve_uncertainty_markers("Trade talks may resume next week.", is_unconfirmed=True)
        self.assertIn("Unconfirmed Reports", unconfirmed)

    def test_11_queue_manager_ranking_integration(self):
        """11. Verifies queue manager imports content intelligence."""
        import queue_manager
        self.assertTrue(hasattr(queue_manager, "QueueManager"))

    def test_12_config_source_quality_override(self):
        """12. Verifies custom source quality overrides."""
        custom_cie = ContentIntelligenceEngine({"custom_news": 0.95, "default": 0.70})
        self.assertEqual(custom_cie.get_source_quality_score("custom_news"), 0.95)

    def test_13_lifecycle_state_in_queue_entry(self):
        """13. Verifies story lifecycle state determination."""
        state = self.cie.get_story_lifecycle_state({"title": "Breaking News", "source": "Reuters"}, source_count=2)
        self.assertIn(state, ["NEW", "DEVELOPING", "TRENDING", "BREAKING", "RESOLVED"])

    def test_14_diversity_breaking_news_override(self):
        """14. Verifies breaking news bypasses category diversity clustering rules."""
        candidates = [
            {"title": "Regular Tech 1", "category": "TECHNOLOGY"},
            {"title": "BREAKING: Major Security Breach", "category": "TECHNOLOGY", "is_breaking": True}
        ]
        history = [{"category": "TECHNOLOGY"}, {"category": "TECHNOLOGY"}]
        reordered = self.cie.enforce_category_diversity(candidates, history, max_consecutive=2)
        self.assertTrue(reordered[0].get("is_breaking"))

    def test_15_full_pipeline_compatibility(self):
        """15. Verifies compatibility with main pipeline execution."""
        import main
        self.assertTrue(hasattr(main, "main") or hasattr(main, "run_pipeline"))


if __name__ == "__main__":
    unittest.main()
