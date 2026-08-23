"""
test_phase12.py
---------------
Automated test suite for Phase 12 Advanced Telegram Channel Automation.

Verifies:
 1. Morning briefing formatting (🌅 GOOD MORNING)
 2. Evening roundup formatting (🌙 TODAY'S TOP STORIES)
 3. Breaking news alerts fast-path & formatting (🚨 BREAKING NEWS)
 4. Trending digest formatting (🔥 TRENDING NOW)
 5. Sports alert category formatting (🏏 SPORTS UPDATE)
 6. Entertainment update category formatting (🎬 ENTERTAINMENT UPDATE)
 7. Technology digest category formatting (💻 TECH DIGEST)
 8. Interactive poll generation for suitable topics
 9. Poll rejection for sensitive/crisis topics
10. Post pinning safety logic
11. Admin rhythm configuration (/polls, /pin, /briefingtime, /rounduptime)
12. IST rhythm time checking logic
13. Spam & duplicate protection across summaries
14. Admin briefing & roundup command execution
15. Scheduler rhythm integration
"""

import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import config
from admin_control import AdminControlManager
from channel_automation import ChannelAutomationManager
from queue_manager import QueueManager

IST = ZoneInfo("Asia/Kolkata")


class TestPhase12(unittest.TestCase):

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.automation_file = self.temp_dir / "automation_state.json"
        self.admin_file = self.temp_dir / "admin_state.json"
        self.posts_file = self.temp_dir / "posts.json"

        self.cam = ChannelAutomationManager(filepath=self.automation_file)
        self.acm = AdminControlManager(state_filepath=self.admin_file)
        self.qm = QueueManager(posts_filepath=self.posts_file)

        config.TELEGRAM_ADMIN_IDS = [123456789]

    def test_1_morning_briefing_formatting(self):
        """1. Verifies morning briefing post formatting."""
        top_stories = [
            {"title": "Global Economic Summit Opens", "category": "News"},
            {"title": "Quantum Computing Breakthrough", "category": "Technology"},
            {"title": "Championship Final Tonight", "category": "Sports"},
            {"title": "Acclaimed Director Wins Award", "category": "Entertainment"}
        ]
        briefing = self.cam.generate_morning_briefing(top_stories)
        self.assertIn("GOOD MORNING", briefing["summary"])
        self.assertIn("Global Economic Summit", briefing["summary"])
        self.assertIn("Quantum Computing", briefing["summary"])

    def test_2_evening_roundup_formatting(self):
        """2. Verifies evening roundup post formatting."""
        top_stories = [
            {"title": "Major Tech Launch Event", "category": "Technology"},
            {"title": "Historic Election Results", "category": "News"}
        ]
        stats = {"news": 12, "technology": 8, "sports": 5, "entertainment": 3}
        roundup = self.cam.generate_evening_roundup(top_stories, cat_stats=stats)
        self.assertIn("TODAY'S TOP STORIES", roundup["summary"])
        self.assertIn("Category Breakdown:", roundup["summary"])

    def test_3_breaking_news_fast_path_and_header(self):
        """3. Verifies breaking news header and priority."""
        post = {
            "title": "Unprecedented Space Station Mission",
            "summary": "Astronauts dock safely.",
            "category": "News",
            "is_breaking": True,
            "score": 95
        }
        from publisher import format_html_post
        formatted = format_html_post(post)
        self.assertIn("BREAKING NEWS", formatted)

    def test_4_trending_digest_formatting(self):
        """4. Verifies trending digest formatting."""
        stories = [
            {"title": "Global Cyber Defense Initiative", "source_count": 5},
            {"title": "New Renewable Battery Unveiled", "source_count": 3}
        ]
        digest = self.cam.generate_trending_digest(stories)
        self.assertIn("TRENDING NOW", digest["summary"])
        self.assertIn("Cyber Defense", digest["summary"])

    def test_5_sports_alert_formatting(self):
        """5. Verifies sports alert category update formatting."""
        story = {"title": "Final Championship Result: Team A Wins", "category": "Sports"}
        updated = self.cam.generate_category_update(story)
        self.assertIn("SPORTS UPDATE", updated["title"])

    def test_6_entertainment_update_formatting(self):
        """6. Verifies entertainment update category formatting."""
        story = {"title": "Blockbuster Movie Trailer Released", "category": "Entertainment"}
        updated = self.cam.generate_category_update(story)
        self.assertIn("ENTERTAINMENT UPDATE", updated["title"])

    def test_7_technology_digest_formatting(self):
        """7. Verifies technology digest category formatting."""
        story = {"title": "Next Generation AI Model Launched", "category": "Technology"}
        updated = self.cam.generate_category_update(story)
        self.assertIn("TECH DIGEST", updated["title"])

    def test_8_poll_generation_for_suitable_topics(self):
        """8. Verifies poll generation for sports match topics."""
        story = {"title": "Real Madrid vs Barcelona Final Match", "category": "Sports"}
        poll = self.cam.generate_poll_payload(story)
        self.assertIsNotNone(poll)
        q, opts = poll
        self.assertIn("Who will win", q)
        self.assertIn("Real Madrid", opts)
        self.assertIn("Barcelona", opts)

    def test_9_poll_rejection_for_sensitive_news(self):
        """9. Verifies poll generation strictly rejects sensitive news topics."""
        story = {"title": "Tragic Highway Crash Kills Passengers", "category": "News"}
        poll = self.cam.generate_poll_payload(story)
        self.assertIsNone(poll)

    def test_10_post_pinning_safety(self):
        """10. Verifies post pinning entry point functions safely."""
        from publisher import pin_message
        # Should catch and return False cleanly without throwing exception when bot is unconfigured
        result = pin_message(12345)
        self.assertFalse(result)

    def test_11_admin_rhythm_configuration(self):
        """11. Verifies admin commands configure polls, pinning, and briefing times."""
        r1 = self.acm.handle_command(123456789, "/polls off")
        self.assertIn("POLLS: DISABLED", r1)

        r2 = self.acm.handle_command(123456789, "/pin off")
        self.assertIn("PINNING: DISABLED", r2)

        r3 = self.acm.handle_command(123456789, "/briefingtime 09:30")
        self.assertIn("MORNING BRIEFING TIME set to 09:30 IST", r3)

        r4 = self.acm.handle_command(123456789, "/rounduptime 21:00")
        self.assertIn("EVENING ROUNDUP TIME set to 21:00 IST", r4)

    def test_12_ist_rhythm_time_checking(self):
        """12. Verifies IST rhythm trigger logic."""
        # 8 AM IST
        dt_8am = datetime(2026, 8, 23, 8, 30, tzinfo=IST)
        self.assertTrue(self.cam.should_trigger_morning_briefing(dt_8am))

        # Mark briefing sent today
        state = self.cam.load_state()
        state["last_morning_briefing_date"] = "2026-08-23"
        self.cam.save_state(state)
        self.assertFalse(self.cam.should_trigger_morning_briefing(dt_8am))

    def test_13_spam_and_duplicate_protection(self):
        """13. Verifies polling interval rate limits."""
        dt_now = datetime(2026, 8, 23, 12, 0, tzinfo=IST)
        state = self.cam.load_state()
        state["last_poll_created_at"] = dt_now.isoformat()
        self.cam.save_state(state)

        # 1 hour later -> should return False
        dt_1h_later = datetime(2026, 8, 23, 13, 0, tzinfo=IST)
        self.assertFalse(self.cam.should_trigger_poll(dt_1h_later))

        # 5 hours later -> should return True
        dt_5h_later = datetime(2026, 8, 23, 17, 0, tzinfo=IST)
        self.assertTrue(self.cam.should_trigger_poll(dt_5h_later))

    def test_14_admin_briefing_and_roundup_commands(self):
        """14. Verifies admin /briefing and /roundup commands return valid summary output."""
        r_brief = self.acm.handle_command(123456789, "/briefing")
        self.assertIn("GOOD MORNING", r_brief)

        r_round = self.acm.handle_command(123456789, "/roundup")
        self.assertIn("TODAY'S TOP STORIES", r_round)

    def test_15_scheduler_rhythm_integration(self):
        """15. Verifies scheduler module imports and references channel automation."""
        import scheduler
        self.assertTrue(hasattr(scheduler, "check_and_publish"))


if __name__ == "__main__":
    unittest.main()
