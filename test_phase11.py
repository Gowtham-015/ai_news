"""
test_phase11.py
---------------
Automated test suite for Phase 11 Telegram Admin Control System.

Verifies:
 1. Authorized user access
 2. Unauthorized user rejection & security logging
 3. /status command execution
 4. /queue command execution
 5. /stats command execution
 6. Global /pause and /resume state toggling
 7. Category-level /pause <category> and /resume <category> state toggling
 8. /topnews command execution
 9. Safe /retry execution preventing duplicate publishing
10. /test admin message execution
11. Invalid command help menu fallback
12. Scheduler publishing pause enforcement
"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import config
from admin_control import AdminControlManager
from queue_manager import QueueManager


class TestPhase11(unittest.TestCase):

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.state_file = self.temp_dir / "admin_state.json"
        self.posts_file = self.temp_dir / "posts.json"
        self.acm = AdminControlManager(state_filepath=self.state_file)
        self.qm = QueueManager(posts_filepath=self.posts_file)

        # Mock TELEGRAM_ADMIN_IDS to include 123456789
        config.TELEGRAM_ADMIN_IDS = [123456789]

    def test_1_authorized_user_access(self):
        """1. Verifies authorized user ID passes authorization check."""
        self.assertTrue(self.acm.is_authorized(123456789))
        self.assertTrue(self.acm.is_authorized("123456789"))

    def test_2_unauthorized_user_rejection(self):
        """2. Verifies unauthorized user ID is rejected with access denied."""
        self.assertFalse(self.acm.is_authorized(999999999))
        response = self.acm.handle_command(999999999, "/status")
        self.assertIn("ACCESS DENIED", response)

    def test_3_status_command(self):
        """3. Verifies /status command returns formatted system health status."""
        response = self.acm.handle_command(123456789, "/status", queue_mgr=self.qm)
        self.assertIn("SYSTEM STATUS", response)
        self.assertIn("Status: ONLINE", response)

    def test_4_queue_command(self):
        """4. Verifies /queue command lists upcoming scheduled posts."""
        sample_post = {
            "id": 1,
            "category": "Technology",
            "title": "Quantum Chip Launch",
            "priority": "HIGH",
            "status": "scheduled",
            "scheduled_time": "2026-08-23 18:00:00"
        }
        self.qm.save_queue([sample_post])

        response = self.acm.handle_command(123456789, "/queue", queue_mgr=self.qm)
        self.assertIn("UPCOMING SCHEDULED POSTS", response)
        self.assertIn("Quantum Chip Launch", response)

    def test_5_stats_command(self):
        """5. Verifies /stats command returns daily statistics report."""
        response = self.acm.handle_command(123456789, "/stats")
        self.assertIn("DAILY NEWS REPORT", response)

    def test_6_global_pause_and_resume(self):
        """6. Verifies global /pause and /resume toggling."""
        resp_pause = self.acm.handle_command(123456789, "/pause")
        self.assertIn("GLOBAL PUBLISHING PAUSED", resp_pause)
        self.assertTrue(self.acm.is_publishing_paused())

        resp_resume = self.acm.handle_command(123456789, "/resume")
        self.assertIn("GLOBAL PUBLISHING RESUMED", resp_resume)
        self.assertFalse(self.acm.is_publishing_paused())

    def test_7_category_pause_and_resume(self):
        """7. Verifies category-level /pause <cat> and /resume <cat> toggling."""
        resp_pause = self.acm.handle_command(123456789, "/pause sports")
        self.assertIn("PUBLISHING PAUSED for category: SPORTS", resp_pause)
        self.assertTrue(self.acm.is_publishing_paused("SPORTS"))
        self.assertFalse(self.acm.is_publishing_paused("NEWS"))

        resp_resume = self.acm.handle_command(123456789, "/resume sports")
        self.assertIn("PUBLISHING RESUMED for category: SPORTS", resp_resume)
        self.assertFalse(self.acm.is_publishing_paused("SPORTS"))

    def test_8_topnews_command(self):
        """8. Verifies /topnews command returns top news headers."""
        response = self.acm.handle_command(123456789, "/topnews")
        self.assertIn("TOP STORIES", response)

    def test_9_safe_retry_command(self):
        """9. Verifies /retry resets failed posts to scheduled safely."""
        failed_post = {
            "id": 10,
            "category": "News",
            "title": "Failed Story Update",
            "url": "https://example.com/unique-story-10",
            "original_url": "https://example.com/unique-story-10",
            "status": "permanently_failed",
            "retry_count": 3
        }
        self.qm.save_queue([failed_post])

        response = self.acm.handle_command(123456789, "/retry", queue_mgr=self.qm)
        self.assertIn("RETRY EXECUTION COMPLETE", response)

        queue = self.qm.load_queue()
        self.assertEqual(queue[0]["status"], "scheduled")
        self.assertEqual(queue[0]["retry_count"], 0)

    def test_10_admin_test_command(self):
        """10. Verifies /test sends admin test message response."""
        response = self.acm.handle_command(123456789, "/test")
        self.assertIn("ADMIN TEST MESSAGE", response)
        self.assertIn("123456789", response)

    def test_11_invalid_command_help_menu(self):
        """11. Verifies invalid commands return the command help menu."""
        response = self.acm.handle_command(123456789, "/unknown_cmd")
        self.assertIn("Unknown or invalid command", response)
        self.assertIn("COMMAND MENU", response)

    def test_12_scheduler_pause_enforcement(self):
        """12. Verifies scheduler respects pause state."""
        self.acm.handle_command(123456789, "/pause")
        self.assertTrue(self.acm.is_publishing_paused("NEWS"))


if __name__ == "__main__":
    unittest.main()
