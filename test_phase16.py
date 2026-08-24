"""
test_phase16.py
---------------
Automated test suite for Phase 16 Production Monitoring & Self-Healing Telemetry.

Verifies:
 1. Collection success telemetry
 2. Collection failure telemetry
 3. AI success telemetry
 4. AI failure telemetry
 5. Telegram success telemetry
 6. Telegram failure telemetry
 7. Workflow success telemetry
 8. Workflow failure telemetry
 9. Consecutive failures counter
10. Health state transition (ONLINE, DEGRADED, PAUSED, ERROR)
11. Recovery logging
12. Alert throttling enforcement (4-hour throttle window)
13. Pause state evaluation
14. Secret masking in logs & alerts
15. Auto-healing execution (stale locks & stuck queues)
16. Telemetry failure isolation (health monitor issues never crash pipeline)
"""

import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

import config
from admin_control import AdminControlManager
from health_monitor import HealthMonitor, mask_secrets


class TestPhase16(unittest.TestCase):

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.health_file = self.temp_dir / "health_state.json"
        self.hm = HealthMonitor(filepath=self.health_file)
        self.acm = AdminControlManager(state_filepath=self.temp_dir / "admin_state.json")
        config.TELEGRAM_ADMIN_IDS = [123456789]

    def test_1_collection_success_telemetry(self):
        """1. Verifies collection success recording."""
        self.hm.record_success("collection")
        state = self.hm.load_state()
        self.assertIsNotNone(state.get("last_news_collection"))

    def test_2_collection_failure_telemetry(self):
        """2. Verifies collection failure recording."""
        self.hm.record_failure("COLLECTION_FAILURE", "RSS connection timeout")
        state = self.hm.load_state()
        self.assertEqual(state["last_error"]["type"], "COLLECTION_FAILURE")

    def test_3_ai_success_telemetry(self):
        """3. Verifies AI success recording."""
        self.hm.record_success("ai")
        state = self.hm.load_state()
        self.assertIsNotNone(state.get("last_ai_success"))

    def test_4_ai_failure_telemetry(self):
        """4. Verifies AI failure recording."""
        self.hm.record_failure("AI_ERROR", "Gemini API rate limit exceeded")
        state = self.hm.load_state()
        self.assertEqual(state["last_error"]["type"], "AI_ERROR")

    def test_5_telegram_success_telemetry(self):
        """5. Verifies Telegram publication success recording."""
        self.hm.record_success("publication")
        state = self.hm.load_state()
        self.assertIsNotNone(state.get("last_telegram_publication"))

    def test_6_telegram_failure_telemetry(self):
        """6. Verifies Telegram publication failure recording."""
        self.hm.record_failure("TELEGRAM_FAILURE", "Telegram API connection refused")
        state = self.hm.load_state()
        self.assertEqual(state["last_error"]["type"], "TELEGRAM_FAILURE")

    def test_7_workflow_success_telemetry(self):
        """7. Verifies workflow success recording."""
        self.hm.record_success("workflow")
        state = self.hm.load_state()
        self.assertIsNotNone(state.get("last_successful_workflow"))

    def test_8_workflow_failure_telemetry(self):
        """8. Verifies workflow failure recording."""
        self.hm.record_failure("WORKFLOW_FAILURE", "Pipeline crash")
        state = self.hm.load_state()
        self.assertEqual(state["last_error"]["type"], "WORKFLOW_FAILURE")

    def test_9_consecutive_failures_counter(self):
        """9. Verifies consecutive failures increment and reset."""
        self.hm.record_failure("ERR1", "Reason 1")
        self.hm.record_failure("ERR2", "Reason 2")
        self.assertEqual(self.hm.load_state()["consecutive_failures"], 2)

        self.hm.record_success("publication")
        self.assertEqual(self.hm.load_state()["consecutive_failures"], 0)

    def test_10_health_state_transitions(self):
        """10. Verifies status transitions between ONLINE, DEGRADED, and ERROR."""
        self.assertEqual(self.hm.evaluate_status(), "ONLINE")
        self.hm.record_failure("AI_ERROR", "Quota exceeded")
        self.assertEqual(self.hm.evaluate_status(), "DEGRADED")

        for _ in range(5):
            self.hm.record_failure("TELEGRAM_FAILURE", "Conn error")
        self.assertEqual(self.hm.evaluate_status(), "ERROR")

    def test_11_recovery_logging(self):
        """11. Verifies recovery events are stored in recovery_logs."""
        self.hm.record_failure("RSS_TIMEOUT", "Feed unresponsive")
        state = self.hm.load_state()
        logs = state.get("recovery_logs", [])
        self.assertGreater(len(logs), 0)

    def test_12_alert_throttling(self):
        """12. Verifies admin alert throttling blocks repeated alerts within 4 hours."""
        from unittest import mock
        with mock.patch("publisher.publish_text", return_value=True):
            first = self.hm.send_admin_alert_if_needed("TEST_ISSUE", "First alert message")
            self.assertTrue(first)
            second = self.hm.send_admin_alert_if_needed("TEST_ISSUE", "Second alert message")
            self.assertFalse(second)

    def test_13_pause_state_evaluation(self):
        """13. Verifies system reports PAUSED state when global publishing is paused."""
        from unittest import mock
        with mock.patch("admin_control.AdminControlManager.is_publishing_paused", return_value=True):
            self.assertEqual(self.hm.evaluate_status(), "PAUSED")

    def test_14_secret_masking(self):
        """14. Verifies sensitive tokens and API keys are masked."""
        raw = "Connecting to bot123456789:ABCdefGHIjklMNO_secret"
        masked = mask_secrets(raw)
        self.assertNotIn("bot123456789:ABCdefGHIjklMNO_secret", masked)
        self.assertIn("bot[MASKED_TOKEN]", masked)

    def test_15_auto_healing_execution(self):
        """15. Verifies auto_heal execution clears stale locks and stuck queue items."""
        lock_path = self.temp_dir / "agent.lock"
        lock_path.write_text("lock", encoding="utf-8")
        old_time = (datetime.now() - timedelta(minutes=40)).timestamp()
        os.utime(lock_path, (old_time, old_time))

        import health_monitor
        orig_lock = health_monitor.LOCK_FILE
        health_monitor.LOCK_FILE = lock_path
        try:
            res = self.hm.auto_heal()
            self.assertFalse(lock_path.exists())
            self.assertIn("actions_taken", res)
        finally:
            health_monitor.LOCK_FILE = orig_lock

    def test_16_telemetry_failure_isolation(self):
        """16. Verifies a broken health monitor never crashes pipeline execution."""
        bad_hm = HealthMonitor(filepath=Path("/invalid/path/health.json"))
        try:
            bad_hm.record_success("collection")
        except Exception as e:
            self.fail(f"Telemetry call raised unexpected exception: {e}")


if __name__ == "__main__":
    unittest.main()
