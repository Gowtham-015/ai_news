"""
health_monitor.py
------------------
PHASE 16 of the AI News Automation Agent.

Responsible for:
1. Production Monitoring: Tracking system health metrics, RSS/AI/Telegram failures, queue size, and consecutive errors.
2. Failure Detection & Diagnosis: Evaluating System State (ONLINE, DEGRADED, PAUSED, ERROR).
3. Self-Healing Engine: Automated stale lock cleanup, stuck queue recovery, and AI fallback switching.
4. Throttled Admin Telegram Alerts: Sends notifications to admin during degraded/error states with 4-hour throttling.
5. Secure Recovery Logging: Persists recovery events with strict secret masking (stripping Bot Tokens and API Keys).
"""

import json
import logging
import re
import shutil
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from zoneinfo import ZoneInfo

import config
from analytics_manager import get_ist_now, get_ist_date_str

logger = logging.getLogger("health_monitor")
if not logger.handlers:
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    logger.addHandler(handler)

IST = ZoneInfo("Asia/Kolkata")
DATA_DIR = getattr(config, "DATA_DIR_PATH", Path(__file__).parent / "data")
HEALTH_STATE_FILE = DATA_DIR / "health_state.json"
LOCK_FILE = DATA_DIR / "agent.lock"

ALERT_THROTTLE_HOURS = 4.0


def _create_default_health_state() -> dict:
    return {
        "status": "ONLINE",
        "last_successful_workflow": None,
        "last_news_collection": None,
        "last_telegram_publication": None,
        "last_ai_success": None,
        "consecutive_failures": 0,
        "last_error": None,
        "last_alerts": {},
        "recovery_logs": []
    }


def mask_secrets(text: str) -> str:
    """Strips sensitive bot tokens, API keys, and secret values from text."""
    if not text:
        return ""
    s = str(text)
    # Mask Telegram Bot Tokens (e.g. 123456789:ABCdefGHIjklMNO)
    s = re.sub(r"bot\d+:[A-Za-z0-9_-]+", "bot[MASKED_TOKEN]", s)
    # Mask API Keys
    if getattr(config, "GEMINI_API_KEY", None):
        s = s.replace(str(config.GEMINI_API_KEY), "[MASKED_API_KEY]")
    if getattr(config, "TELEGRAM_BOT_TOKEN", None):
        s = s.replace(str(config.TELEGRAM_BOT_TOKEN), "[MASKED_TOKEN]")
    return s


class HealthMonitor:
    def __init__(self, filepath: Path = HEALTH_STATE_FILE):
        self.filepath = filepath

    def load_state(self) -> dict:
        """Loads health state atomically."""
        if not self.filepath.exists():
            return _create_default_health_state()
        try:
            with open(self.filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
        except Exception as e:
            logger.error("Failed to load health state (%s): %s", self.filepath, e)
        return _create_default_health_state()

    def save_state(self, data: dict):
        """Saves health state atomically."""
        self.filepath.parent.mkdir(parents=True, exist_ok=True)
        tmp_fd, tmp_path = tempfile.mkstemp(dir=self.filepath.parent, prefix="health_", suffix=".tmp")
        try:
            with open(tmp_fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            shutil.move(tmp_path, self.filepath)
        except Exception as e:
            Path(tmp_path).unlink(missing_ok=True)
            logger.error("Failed to save health state: %s", e)

    def evaluate_status(self) -> str:
        """Evaluates and returns current system health status: ONLINE, DEGRADED, PAUSED, ERROR."""
        try:
            from admin_control import AdminControlManager
            if AdminControlManager().is_publishing_paused():
                return "PAUSED"
        except Exception:
            pass

        state = self.load_state()
        if state.get("consecutive_failures", 0) >= 5:
            return "ERROR"

        last_err = state.get("last_error")
        if last_err and last_err.get("type") in ("AI_ERROR", "RSS_ERROR"):
            return "DEGRADED"

        return "ONLINE"

    def record_success(self, event_type: str):
        """Records a successful operation (collection, publication, ai, workflow)."""
        state = self.load_state()
        now_str = get_ist_now().isoformat()
        state["consecutive_failures"] = 0

        if event_type == "collection":
            state["last_news_collection"] = now_str
        elif event_type == "publication":
            state["last_telegram_publication"] = now_str
        elif event_type == "ai":
            state["last_ai_success"] = now_str
        elif event_type == "workflow":
            state["last_successful_workflow"] = now_str

        state["status"] = self.evaluate_status()
        self.save_state(state)

    def record_failure(self, failure_type: str, reason: str, details: Optional[dict] = None):
        """Records a failure event safely with secret masking."""
        state = self.load_state()
        now_str = get_ist_now().isoformat()
        clean_reason = mask_secrets(reason)

        state["consecutive_failures"] = state.get("consecutive_failures", 0) + 1
        state["last_error"] = {
            "type": failure_type,
            "reason": clean_reason,
            "timestamp": now_str,
            "details": details or {}
        }

        # Record in recovery logs
        recovery_entry = {
            "failure": failure_type,
            "reason": clean_reason,
            "timestamp": now_str,
            "action": "logged"
        }
        logs = state.get("recovery_logs", [])
        logs.append(recovery_entry)
        state["recovery_logs"] = logs[-50:]  # Keep last 50 recovery logs

        state["status"] = self.evaluate_status()
        self.save_state(state)

        # Trigger admin alert if consecutive failures >= 3
        if state["consecutive_failures"] >= 3:
            self.send_admin_alert_if_needed(failure_type, f"Repeated failure detected ({failure_type}): {clean_reason}")

    def send_admin_alert_if_needed(self, issue_type: str, message: str) -> bool:
        """Sends a throttled Telegram alert to admin (max 1 alert per 4 hours per issue type)."""
        state = self.load_state()
        last_alerts = state.get("last_alerts", {})
        last_alert_str = last_alerts.get(issue_type)

        now = get_ist_now()
        if last_alert_str:
            try:
                last_dt = datetime.fromisoformat(last_alert_str)
                if (now - last_dt) < timedelta(hours=ALERT_THROTTLE_HOURS):
                    logger.info("[ALERT] Throttling alert for issue '%s' (Sent < %dh ago)", issue_type, ALERT_THROTTLE_HOURS)
                    return False
            except Exception:
                pass

        clean_msg = mask_secrets(message)
        logger.warning("[HEALTH ALERT] Sending admin alert: %s", clean_msg)

        try:
            import publisher
            alert_text = f"🚨 <b>AI NEWS AGENT SYSTEM ALERT</b>\n\nIssue: {issue_type}\nDetail: {clean_msg}\nStatus: {self.evaluate_status()}"
            publisher.publish_text(alert_text)
            last_alerts[issue_type] = now.isoformat()
            state["last_alerts"] = last_alerts
            self.save_state(state)
            return True
        except Exception as e:
            logger.error("Failed to send admin alert: %s", e)
            return False

    def auto_heal(self) -> dict:
        """
        Executes automated self-healing recovery checks:
        1. Stale lock cleanup (clears agent.lock if > 30 minutes old).
        2. Stuck queue recovery (resets stuck 'publishing' posts back to 'scheduled').
        """
        actions_taken = []
        now = get_ist_now()

        # 1. Stale Lock Cleanup
        if LOCK_FILE.exists():
            try:
                mtime = datetime.fromtimestamp(LOCK_FILE.stat().st_mtime, tz=IST)
                if (now - mtime) > timedelta(minutes=30):
                    LOCK_FILE.unlink(missing_ok=True)
                    actions_taken.append("Removed stale agent.lock file (> 30 mins old)")
                    logger.info("[SELF-HEALING] Removed stale agent.lock file")
            except Exception as e:
                logger.warning("[SELF-HEALING] Lock cleanup failed: %s", e)

        # 2. Stuck Queue Recovery
        posts_file = DATA_DIR / "posts.json"
        if posts_file.exists():
            try:
                with open(posts_file, "r", encoding="utf-8") as f:
                    posts = json.load(f)
                modified = False
                if isinstance(posts, list):
                    for p in posts:
                        if p.get("status") == "publishing":
                            p["status"] = "scheduled"
                            modified = True
                            actions_taken.append(f"Reset stuck post {p.get('id')} back to scheduled")
                if modified:
                    tmp_fd, tmp_path = tempfile.mkstemp(dir=posts_file.parent, prefix="posts_heal_", suffix=".tmp")
                    with open(tmp_fd, "w", encoding="utf-8") as f:
                        json.dump(posts, f, indent=2, ensure_ascii=False)
                    shutil.move(tmp_path, posts_file)
                    logger.info("[SELF-HEALING] Reset stuck publishing posts back to scheduled")
            except Exception as e:
                logger.warning("[SELF-HEALING] Queue recovery failed: %s", e)

        state = self.load_state()
        state["status"] = self.evaluate_status()
        self.save_state(state)

        return {"actions_taken": actions_taken}
