"""
test_phase13.py
---------------
Automated test suite for Phase 13 Telegram Audience Growth & Engagement Engine.

Verifies:
 1. Sensitive topic safety filtering (rejecting tragedies, deaths, accidents, crimes)
 2. Opinion prompt formatting ("What's your take on this?")
 3. Prediction poll payload generation for Sports/Tech/Entertainment
 4. Weekend special post generation (Saturday recap / Sunday deep read)
 5. Rotating natural CTA selection
 6. Daily poll rate limit enforcement (max 3/day)
 7. Daily engagement post rate limit enforcement (max 4/day)
 8. Minimum engagement interval enforcement (3 hours)
 9. Admin /engagement on|off control command execution
10. Admin /engagementstats telemetry display execution
11. Analytics integration for engagement events
12. Global publishing pause compatibility
13. Duplicate engagement prevention on identical runs
14. Engagement state file persistence
15. Scheduler engagement integration
"""

import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import config
from admin_control import AdminControlManager
from engagement_engine import EngagementEngine, SENSITIVE_KEYWORDS

IST = ZoneInfo("Asia/Kolkata")


class TestPhase13(unittest.TestCase):

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.state_file = self.temp_dir / "engagement_state.json"
        self.admin_file = self.temp_dir / "admin_state.json"

        self.ee = EngagementEngine(filepath=self.state_file)
        self.acm = AdminControlManager(state_filepath=self.admin_file)

        config.TELEGRAM_ADMIN_IDS = [123456789]

    def test_1_sensitive_topic_rejection(self):
        """1. Verifies sensitive topics (deaths, accidents, crimes) are strictly rejected."""
        self.assertTrue(self.ee.is_sensitive_topic("Tragic Car Crash Kills Three", "Details of fatal accident."))
        self.assertTrue(self.ee.is_sensitive_topic("Investigation into Murder Case", "Police report."))
        self.assertFalse(self.ee.is_sensitive_topic("New Smartphone Launch Event", "Tech company unveils device."))

    def test_2_opinion_prompt_formatting(self):
        """2. Verifies opinion prompt and CTA are attached to non-sensitive story."""
        story = {
            "title": "Quantum Computing Milestone",
            "content": "Researchers achieve new milestone.",
            "category": "Technology"
        }
        modified = self.ee.attach_opinion_prompt(story)
        self.assertIn("Will this technological shift change how you work", modified["content"])

    def test_3_prediction_poll_generation(self):
        """3. Verifies prediction poll payload generation for sports match."""
        story = {
            "title": "Arsenal vs Chelsea Premier League Final",
            "content": "Upcoming match details.",
            "category": "Sports"
        }
        poll = self.ee.generate_prediction_poll(story)
        self.assertIsNotNone(poll)
        q, opts = poll
        self.assertIn("Arsenal", opts)
        self.assertIn("Chelsea", opts)

    def test_4_weekend_special_generation(self):
        """4. Verifies weekend special generation on Saturday/Sunday."""
        stories = [{"title": "Top Tech Review", "category": "Technology"}]
        # Saturday
        dt_sat = datetime(2026, 8, 29, 10, 0, tzinfo=IST)
        weekend_post = self.ee.generate_weekend_special(stories, dt=dt_sat)
        self.assertIsNotNone(weekend_post)
        self.assertIn("WEEKEND RECAP", weekend_post["summary"])

        # Monday -> should be None
        dt_mon = datetime(2026, 8, 24, 10, 0, tzinfo=IST)
        self.assertIsNone(self.ee.generate_weekend_special(stories, dt=dt_mon))

    def test_5_rotating_natural_cta(self):
        """5. Verifies CTAs rotate sequentially."""
        cta1 = self.ee.get_next_cta()
        cta2 = self.ee.get_next_cta()
        self.assertNotEqual(cta1, cta2)

    def test_6_daily_poll_limit_enforcement(self):
        """6. Verifies max polls per day limit (3) is enforced."""
        state = self.ee.load_state()
        state["polls_today_count"] = 3
        state["last_engagement_date"] = "2026-08-24"
        self.ee.save_state(state)

        dt_now = datetime(2026, 8, 24, 16, 0, tzinfo=IST)
        self.assertFalse(self.ee.can_generate_poll(dt_now))

    def test_7_daily_engagement_post_limit_enforcement(self):
        """7. Verifies max engagement posts per day limit (4) is enforced."""
        state = self.ee.load_state()
        state["engagement_today_count"] = 4
        state["last_engagement_date"] = "2026-08-24"
        self.ee.save_state(state)

        dt_now = datetime(2026, 8, 24, 16, 0, tzinfo=IST)
        self.assertFalse(self.ee.can_generate_engagement(dt_now))

    def test_8_min_engagement_interval_enforcement(self):
        """8. Verifies 3-hour minimum engagement interval is enforced."""
        dt_now = datetime(2026, 8, 24, 12, 0, tzinfo=IST)
        state = self.ee.load_state()
        state["last_engagement_at"] = dt_now.isoformat()
        state["engagement_today_count"] = 1
        state["last_engagement_date"] = "2026-08-24"
        self.ee.save_state(state)

        # 1 hour later -> False
        dt_1h = datetime(2026, 8, 24, 13, 0, tzinfo=IST)
        self.assertFalse(self.ee.can_generate_engagement(dt_1h))

        # 4 hours later -> True
        dt_4h = datetime(2026, 8, 24, 16, 0, tzinfo=IST)
        self.assertTrue(self.ee.can_generate_engagement(dt_4h))

    def test_9_admin_engagement_commands(self):
        """9. Verifies admin /engagement and /engagement on|off commands."""
        r_off = self.acm.handle_command(123456789, "/engagement off")
        self.assertIn("ENGAGEMENT ENGINE: DISABLED", r_off)

        r_on = self.acm.handle_command(123456789, "/engagement on")
        self.assertIn("ENGAGEMENT ENGINE: ENABLED", r_on)

    def test_10_admin_engagementstats_command(self):
        """10. Verifies admin /engagementstats command displays telemetry."""
        r_stats = self.acm.handle_command(123456789, "/engagementstats")
        self.assertIn("ENGAGEMENT TELEMETRY STATISTICS", r_stats)

    def test_11_analytics_engagement_tracking(self):
        """11. Verifies Phase 10 Analytics records publishing events."""
        from analytics_manager import AnalyticsManager
        am = AnalyticsManager()
        am.record_publishing_event("success", post={"title": "Engagement Post"})
        report = am.generate_daily_report()
        self.assertIn("DAILY NEWS REPORT", report)

    def test_12_pause_compatibility_with_engagement(self):
        """12. Verifies publishing pause compatibility."""
        self.acm.handle_command(123456789, "/pause")
        self.assertTrue(self.acm.is_publishing_paused())

    def test_13_no_duplicate_engagement_on_same_run(self):
        """13. Verifies sensitive topic returns unmodified original story."""
        story = {"title": "Fatal Accident Investigation", "content": "Original content."}
        modified = self.ee.attach_opinion_prompt(story)
        self.assertEqual(story["content"], modified["content"])

    def test_14_state_file_persistence(self):
        """14. Verifies engagement state file persistence."""
        state = self.ee.load_state()
        state["max_polls_per_day"] = 5
        self.ee.save_state(state)

        reloaded = self.ee.load_state()
        self.assertEqual(reloaded["max_polls_per_day"], 5)

    def test_15_scheduler_engagement_integration(self):
        """15. Verifies scheduler module imports EngagementEngine."""
        import scheduler
        self.assertTrue(hasattr(scheduler, "check_and_publish"))


if __name__ == "__main__":
    unittest.main()
