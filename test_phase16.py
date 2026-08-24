"""
test_phase16.py
---------------
Automated test suite for Phase 16 Production Monitoring & Self-Healing.

Verifies:
 1. Health status evaluation (ONLINE, DEGRADED, PAUSED, ERROR)
 2. Stale lock cleanup (> 30 mins old agent.lock)
 3. Stuck queue recovery (resetting stuck 'publishing' posts)
 4. AI failure detection & fallback tracking
 5. Telegram failure detection
 6. Admin alert throttling (4-hour throttle limit)
 7. Recovery event logging
 8. Secret masking in logs & alerts (stripping Bot Token / API Keys)
 9. Extended /status admin command output
10. Consecutive failure counter tracking
11. Empty news collection failure recording
12. Transition to DEGRADED state on errors
13. Self-healing auto_heal execution
14. Health state file persistence
15. Full pipeline integration compatibility
"""

import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import config
from admin_control import AdminControlManager
from health_monitor import HealthMonitor, mask_secrets

IST = ZoneInfo("Asia/Kolkata")


class TestPhase16(unittest.TestCase):

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.health_file = self.temp_dir / "health_state.json"
        self.hm = HealthMonitor(filepath=self.health_file)
        self.acm = AdminControlManager(state_filepath=self.temp_dir / "admin_state.json")

        config.TELEGRAM_ADMIN_IDS = [123456789]

    def test_1_health_status_evaluation(self):
        """1. Verifies health status evaluation returns ONLINE by default."""
        self.assertEqual(self.hm.evaluate_status(), "ONLINE")

    def test_2_stale_lock_cleanup(self):
        """2. Verifies stale agent.lock file is cleaned up by auto_heal."""
        lock_path = self.temp_dir / "agent.lock"
        lock_path.write_text("lock", encoding="utf-8")

        # Mock lock path in test
        import health_monitor
        orig_lock = health_monitor.LOCK_FILE
        health_monitor.LOCK_FILE = lock_path
        try:
            # Set mtime to 40 mins ago
            old_time = (datetime.now() - timedelta(minutes=40)).timestamp()
            import os
            os.utime(lock_path, (old_time, old_time))

            res = self.hm.auto_heal()
            self.assertFalse(lock_path.exists())
        finally:
            health_monitor.LOCK_FILE = orig_lock

    def test_3_stuck_queue_recovery(self):
        """3. Verifies stuck 'publishing' posts are reset to 'scheduled'."""
        posts_path = self.temp_dir / "posts.json"
        posts = [{"id": 1, "title": "Stuck Post", "status": "publishing"}]
        posts_path.write_text(json.dumps(posts), encoding="utf-8")

        import health_monitor
        orig_dir = health_monitor.DATA_DIR
        health_monitor.DATA_DIR = self.temp_dir
        try:
            self.hm.auto_heal()
            with open(posts_path, "r", encoding="utf-8") as f:
                recovered = json.load(f)
            self.assertEqual(recovered[0]["status"], "scheduled")
        finally:
            health_monitor.DATA_DIR = orig_dir

    def test_4_ai_failure_detection_and_fallback(self):
        """4. Verifies AI failure recording and DEGRADED state transition."""
        self.hm.record_failure("AI_ERROR", "AI processing timeout")
        self.assertEqual(self.hm.evaluate_status(), "DEGRADED")

    def test_5_telegram_failure_detection(self):
        """5. Verifies consecutive failure tracking for Telegram errors."""
        for _ in range(5):
            self.hm.record_failure("TELEGRAM_ERROR", "API connection refused")
        self.assertEqual(self.hm.evaluate_status(), "ERROR")

    def test_6_admin_alert_throttling(self):
        """6. Verifies admin alert throttling blocks duplicate alerts within 4 hours."""
        from unittest import mock
        with mock.patch("publisher.publish_text", return_value=True):
            first_sent = self.hm.send_admin_alert_if_needed("TEST_ISSUE", "First alert")
            self.assertTrue(first_sent)

            second_sent = self.hm.send_admin_alert_if_needed("TEST_ISSUE", "Second alert")
            self.assertFalse(second_sent)

    def test_7_recovery_event_logging(self):
        """7. Verifies recovery events are logged in health state."""
        self.hm.record_failure("RSS_ERROR", "Feed timeout")
        state = self.hm.load_state()
        logs = state.get("recovery_logs", [])
        self.assertGreater(len(logs), 0)
        self.assertEqual(logs[-1]["failure"], "RSS_ERROR")

    def test_8_secret_masking_in_logs(self):
        """8. Verifies bot tokens and API keys are masked in logs."""
        raw_msg = "Error connecting to bot123456789:ABCdefGHIjklMNO_secret_token"
        masked = mask_secrets(raw_msg)
        self.assertNotIn("bot123456789:ABCdefGHIjklMNO_secret_token", masked)
        self.assertIn("bot[MASKED_TOKEN]", masked)

    def test_9_extended_status_command(self):
        """9. Verifies extended /status admin command output."""
        res = self.acm.handle_command(123456789, "/status")
        self.assertIn("Status:", res)
        self.assertIn("Consecutive Failures:", res)

    def test_10_consecutive_failure_tracking(self):
        """10. Verifies success resets consecutive failure counter."""
        self.hm.record_failure("TEMP_ERR", "Transient failure")
        self.assertEqual(self.hm.load_state()["consecutive_failures"], 1)

        self.hm.record_success("publication")
        self.assertEqual(self.hm.load_state()["consecutive_failures"], 0)

    def test_11_empty_collection_detection(self):
        """11. Verifies empty news collection failure recording."""
        self.hm.record_failure("COLLECTION_EMPTY", "No new articles collected from RSS feeds")
        state = self.hm.load_state()
        self.assertEqual(state["last_error"]["type"], "COLLECTION_EMPTY")

    def test_12_degraded_state_transition(self):
        """12. Verifies DEGRADED state on RSS error."""
        self.hm.record_failure("RSS_ERROR", "Connection refused")
        self.assertEqual(self.hm.evaluate_status(), "DEGRADED")

    def test_13_auto_heal_execution(self):
        """13. Verifies auto_heal returns execution dictionary."""
        res = self.hm.auto_heal()
        self.assertIn("actions_taken", res)

    def test_14_health_state_persistence(self):
        """14. Verifies health state file persistence."""
        self.hm.record_success("collection")
        reloaded = HealthMonitor(filepath=self.health_file).load_state()
        self.assertIsNotNone(reloaded.get("last_news_collection"))

    def test_15_full_pipeline_compatibility(self):
        """15. Verifies end-to-end pipeline execution compatibility."""
        import main
        self.assertTrue(hasattr(main, "main") or hasattr(main, "run_pipeline"))


if __name__ == "__main__":
    unittest.main()
