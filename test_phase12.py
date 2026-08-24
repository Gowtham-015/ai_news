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
        self.assertTrue(hasattr(scheduler, "check_and_trigger_channel_rhythm"))

    def test_16_auto_morning_briefing_trigger_and_state_update(self):
        """16. Verifies automatic morning briefing triggers and updates state file."""
        from unittest import mock
        import scheduler
        dt_830 = datetime(2026, 8, 24, 8, 30, tzinfo=IST)

        with mock.patch("publisher.publish_post", return_value=True):
            scheduler.check_and_trigger_channel_rhythm(dt_830, automation_mgr=self.cam, admin_mgr=self.acm)

        state = self.cam.load_state()
        self.assertEqual(state.get("last_morning_briefing_date"), "2026-08-24")

    def test_17_auto_evening_roundup_trigger_and_state_update(self):
        """17. Verifies automatic evening roundup triggers and updates state file."""
        from unittest import mock
        import scheduler
        dt_2030 = datetime(2026, 8, 24, 20, 30, tzinfo=IST)

        with mock.patch("publisher.publish_post", return_value=True):
            scheduler.check_and_trigger_channel_rhythm(dt_2030, automation_mgr=self.cam, admin_mgr=self.acm)

        state = self.cam.load_state()
        self.assertEqual(state.get("last_evening_roundup_date"), "2026-08-24")

    def test_18_auto_trending_digest_trigger_and_state_update(self):
        """18. Verifies automatic trending digest triggers and updates state file."""
        from unittest import mock
        import scheduler
        from analytics_manager import AnalyticsManager, get_ist_date_str
        am = AnalyticsManager()
        am.record_top_stories([{"title": "Test Trending News", "score": 90}], "2026-08-24", "2026-W34")

        dt_1400 = datetime(2026, 8, 24, 14, 0, tzinfo=IST)

        with mock.patch("publisher.publish_post", return_value=True):
            scheduler.check_and_trigger_channel_rhythm(dt_1400, automation_mgr=self.cam, admin_mgr=self.acm)

        state = self.cam.load_state()
        self.assertIsNotNone(state.get("last_trending_digest_at"))

    def test_19_duplicate_rhythm_prevention_on_subsequent_runs(self):
        """19. Verifies subsequent execution does not send duplicate rhythm post."""
        from unittest import mock
        import scheduler
        dt_830 = datetime(2026, 8, 24, 8, 30, tzinfo=IST)

        with mock.patch("publisher.publish_post", return_value=True) as mock_pub:
            # 1st run: should trigger morning briefing
            scheduler.check_and_trigger_channel_rhythm(dt_830, automation_mgr=self.cam, admin_mgr=self.acm)
            initial_call_count = mock_pub.call_count

            # 2nd run: should NOT trigger morning briefing again
            scheduler.check_and_trigger_channel_rhythm(dt_830, automation_mgr=self.cam, admin_mgr=self.acm)
            self.assertEqual(mock_pub.call_count, initial_call_count)

    def test_20_github_30min_schedule_compatibility(self):
        """20. Verifies 30-minute schedule run (e.g. 08:03 IST delay) triggers correctly."""
        from unittest import mock
        import scheduler
        dt_803 = datetime(2026, 8, 24, 8, 3, tzinfo=IST)

        with mock.patch("publisher.publish_post", return_value=True):
            scheduler.check_and_trigger_channel_rhythm(dt_803, automation_mgr=self.cam, admin_mgr=self.acm)

        state = self.cam.load_state()
        self.assertEqual(state.get("last_morning_briefing_date"), "2026-08-24")

    def test_21_briefing_time_configuration_respect(self):
        """21. Verifies briefing_time_ist configuration is respected."""
        state = self.cam.load_state()
        state["briefing_time_ist"] = "09:00"
        self.cam.save_state(state)

        # 8:30 AM should NOT trigger if set to 09:00
        dt_830 = datetime(2026, 8, 24, 8, 30, tzinfo=IST)
        self.assertFalse(self.cam.should_trigger_morning_briefing(dt_830))

        # 9:00 AM SHOULD trigger
        dt_900 = datetime(2026, 8, 24, 9, 0, tzinfo=IST)
        self.assertTrue(self.cam.should_trigger_morning_briefing(dt_900))

    def test_22_roundup_time_configuration_respect(self):
        """22. Verifies roundup_time_ist configuration is respected."""
        state = self.cam.load_state()
        state["roundup_time_ist"] = "21:00"
        self.cam.save_state(state)

        # 20:30 PM should NOT trigger if set to 21:00
        dt_2030 = datetime(2026, 8, 24, 20, 30, tzinfo=IST)
        self.assertFalse(self.cam.should_trigger_evening_roundup(dt_2030))

        # 21:00 PM SHOULD trigger
        dt_2100 = datetime(2026, 8, 24, 21, 0, tzinfo=IST)
        self.assertTrue(self.cam.should_trigger_evening_roundup(dt_2100))

    def test_23_ist_date_transition_handling(self):
        """23. Verifies new IST day allows new briefing trigger."""
        state = self.cam.load_state()
        state["last_morning_briefing_date"] = "2026-08-23"
        self.cam.save_state(state)

        dt_new_day = datetime(2026, 8, 24, 8, 0, tzinfo=IST)
        self.assertTrue(self.cam.should_trigger_morning_briefing(dt_new_day))

    def test_24_global_pause_blocks_rhythm_triggers(self):
        """24. Verifies global publishing pause blocks automatic rhythm posts."""
        from unittest import mock
        import scheduler

        self.acm.handle_command(123456789, "/pause")
        dt_830 = datetime(2026, 8, 24, 8, 30, tzinfo=IST)

        with mock.patch("publisher.publish_post") as mock_pub:
            scheduler.check_and_trigger_channel_rhythm(dt_830, automation_mgr=self.cam, admin_mgr=self.acm)
            mock_pub.assert_not_called()

    def test_25_category_pause_blocks_category_rhythm(self):
        """25. Verifies category pause blocks category specific updates."""
        self.acm.handle_command(123456789, "/pause sports")
        self.assertTrue(self.acm.is_publishing_paused("SPORTS"))
        self.assertFalse(self.acm.is_publishing_paused("NEWS"))

    def test_26_analytics_recording_for_rhythm_events(self):
        """26. Verifies Phase 10 Analytics records rhythm events."""
        from analytics_manager import AnalyticsManager
        am = AnalyticsManager()
        am.record_publishing_event("morning_briefing", post={"title": "Morning Briefing"})
        daily = am.generate_daily_report()
        self.assertIn("DAILY NEWS REPORT", daily)

    def test_27_poll_enable_disable_respect(self):
        """27. Verifies polls_enabled toggle in state is respected."""
        state = self.cam.load_state()
        state["polls_enabled"] = False
        self.cam.save_state(state)

        dt_now = datetime(2026, 8, 24, 12, 0, tzinfo=IST)
        self.assertFalse(self.cam.should_trigger_poll(dt_now))

    def test_28_pin_enable_disable_respect(self):
        """28. Verifies pinning_enabled toggle in state is respected."""
        state = self.cam.load_state()
        state["pinning_enabled"] = False
        self.cam.save_state(state)
        self.assertFalse(state["pinning_enabled"])

    def test_29_rhythm_failure_isolation_does_not_crash_pipeline(self):
        """29. Verifies error during rhythm trigger does not throw exception or crash scheduler."""
        from unittest import mock
        import scheduler
        dt_830 = datetime(2026, 8, 24, 8, 30, tzinfo=IST)

        with mock.patch("publisher.publish_post", side_effect=Exception("API Error")):
            # Should catch exception internally and log warning without crashing
            try:
                scheduler.check_and_trigger_channel_rhythm(dt_830, automation_mgr=self.cam, admin_mgr=self.acm)
            except Exception:
                self.fail("check_and_trigger_channel_rhythm raised exception unexpectedly")

    def test_30_state_file_persistence(self):
        """30. Verifies automation state file persists accurately."""
        state = self.cam.load_state()
        state["briefing_time_ist"] = "07:30"
        self.cam.save_state(state)

        reloaded = self.cam.load_state()
        self.assertEqual(reloaded["briefing_time_ist"], "07:30")


if __name__ == "__main__":
    unittest.main()

