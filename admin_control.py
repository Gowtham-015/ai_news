"""
admin_control.py
----------------
PHASE 11 of the AI News Automation Agent.

Responsible for:
1. Secure authorization checking against TELEGRAM_ADMIN_IDS.
2. Admin command handling (/status, /queue, /stats, /pause, /resume, /topnews, /retry, /test).
3. Category-level and global publishing pause/resume state management.
4. Safe retry execution preventing duplicate publishing.
5. Atomic persistence of admin state in data/admin_state.json.
6. Safe, non-blocking polling for Telegram admin updates.
"""

import asyncio
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
import deduplicator
from queue_manager import QueueManager
from analytics_manager import AnalyticsManager, get_ist_now

logger = logging.getLogger("admin_control")
if not logger.handlers:
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    logger.addHandler(handler)

IST = ZoneInfo("Asia/Kolkata")
DATA_DIR = getattr(config, "DATA_DIR_PATH", Path(__file__).parent / "data")
ADMIN_STATE_FILE = getattr(config, "ADMIN_STATE_FILE", DATA_DIR / "admin_state.json")


def _create_default_admin_state() -> dict:
    return {
        "is_paused": False,
        "paused_categories": [],
        "last_admin_command_at": None,
        "last_processed_update_id": 0
    }


class AdminControlManager:
    def __init__(self, state_filepath: Path = ADMIN_STATE_FILE):
        self.filepath = state_filepath

    def load_state(self) -> dict:
        """Loads admin control state atomically."""
        if not self.filepath.exists():
            return _create_default_admin_state()
        try:
            with open(self.filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
        except Exception as e:
            logger.error("Failed to load admin state file (%s): %s", self.filepath, e)
        return _create_default_admin_state()

    def save_state(self, data: dict):
        """Saves admin control state atomically."""
        self.filepath.parent.mkdir(parents=True, exist_ok=True)
        tmp_fd, tmp_path = tempfile.mkstemp(dir=self.filepath.parent, prefix="admin_", suffix=".tmp")
        try:
            with open(tmp_fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            shutil.move(tmp_path, self.filepath)
        except Exception as e:
            Path(tmp_path).unlink(missing_ok=True)
            logger.error("Failed to save admin control state: %s", e)

    def is_authorized(self, user_id: Any) -> bool:
        """
        Checks if the provided Telegram user ID is present in TELEGRAM_ADMIN_IDS.
        Returns False if admin list is empty or user_id is unauthorized.
        """
        if user_id is None:
            return False
        try:
            uid = int(user_id)
        except (ValueError, TypeError):
            logger.warning("Invalid user_id format passed to authorization check: %s", user_id)
            return False

        allowed_ids = getattr(config, "TELEGRAM_ADMIN_IDS", [])
        if not allowed_ids:
            logger.warning("Authorization check failed: TELEGRAM_ADMIN_IDS is empty or not configured.")
            return False

        if uid in allowed_ids:
            return True

        logger.warning("Unauthorized admin command attempt from user_id: %s", uid)
        return False

    def is_publishing_paused(self, category: Optional[str] = None) -> bool:
        """
        Returns True if publishing is globally paused or paused for the specific category.
        """
        state = self.load_state()
        if state.get("is_paused", False):
            return True
        if category:
            cat_upper = category.strip().upper()
            paused_cats = [c.upper() for c in state.get("paused_categories", [])]
            if cat_upper in paused_cats:
                return True
        return False

    def get_help_menu(self) -> str:
        """Returns readable command help menu."""
        return (
            "🤖 AI NEWS AGENT — ADMIN COMMAND MENU\n\n"
            "📊 MONITORING:\n"
            "/status - View system status & health\n"
            "/queue - View upcoming scheduled posts\n"
            "/stats - View today's analytics report\n"
            "/topnews - View current top candidate stories\n\n"
            "⚙️ CONTROL:\n"
            "/pause - Pause all Telegram publishing\n"
            "/pause <category> - Pause publishing for specific category (e.g. /pause sports)\n"
            "/resume - Resume Telegram publishing\n"
            "/resume <category> - Resume publishing for specific category\n"
            "/retry - Reset failed posts for re-attempt\n"
            "/test - Send admin test message\n"
        )

    def handle_command(self, user_id: int, command_text: str, queue_mgr: Optional[QueueManager] = None) -> str:
        """
        Executes admin control commands safely.
        Validates authorization prior to processing.
        """
        if not self.is_authorized(user_id):
            return "⛔ ACCESS DENIED: Unauthorized User ID."

        text = command_text.strip()
        parts = text.split()
        cmd = parts[0].lower() if parts else ""

        # Remove @bot_name suffix if present (e.g., /status@MyBot -> /status)
        if "@" in cmd:
            cmd = cmd.split("@")[0]

        now_str = get_ist_now().strftime("%Y-%m-%d %H:%M:%S IST")
        state = self.load_state()
        state["last_admin_command_at"] = now_str
        self.save_state(state)

        if cmd == "/status":
            return self._cmd_status(queue_mgr)
        elif cmd == "/queue":
            return self._cmd_queue(queue_mgr)
        elif cmd == "/stats":
            return self._cmd_stats()
        elif cmd == "/pause":
            cat_arg = parts[1] if len(parts) > 1 else None
            return self._cmd_pause(cat_arg)
        elif cmd == "/resume":
            cat_arg = parts[1] if len(parts) > 1 else None
            return self._cmd_resume(cat_arg)
        elif cmd == "/topnews":
            return self._cmd_topnews()
        elif cmd == "/retry":
            return self._cmd_retry(queue_mgr)
        elif cmd == "/test":
            return self._cmd_test(user_id)
        else:
            return f"❓ Unknown or invalid command: '{command_text}'\n\n" + self.get_help_menu()

    def _cmd_status(self, queue_mgr: Optional[QueueManager] = None) -> str:
        """Processes /status command."""
        state = self.load_state()
        is_paused = state.get("is_paused", False)
        paused_cats = state.get("paused_categories", [])

        if is_paused:
            status_str = "PAUSED (Global)"
        elif paused_cats:
            status_str = f"ONLINE (Paused categories: {', '.join(paused_cats)})"
        else:
            status_str = "ONLINE"

        # Load runtime agent state
        try:
            from state_manager import StateManager
            sm = StateManager()
            astate = sm.load_state()
            last_coll = astate.get("last_successful_collection_at") or astate.get("last_collection_at") or "None"
            next_coll = astate.get("next_collection_at") or "Scheduled via cron"
            last_err = astate.get("last_error") or "None"
        except Exception:
            last_coll = "N/A"
            next_coll = "N/A"
            last_err = "None"

        qm = queue_mgr or QueueManager()
        posts = qm.load_queue()
        scheduled_count = len([p for p in posts if p.get("status") in ("scheduled", "retrying")])

        am = AnalyticsManager()
        daily = am.generate_daily_report()
        pub_today = 0
        for line in daily.splitlines():
            if "Published:" in line and "📱" in daily:
                try:
                    pub_today = int(line.split("Published:")[1].split()[0])
                except Exception:
                    pass

        # Load published history for last post
        hist = deduplicator.load_published_history()
        last_post_str = hist[-1].get("published_time") or hist[-1].get("title", "None") if hist else "None"

        return (
            "🤖 AI NEWS AGENT — SYSTEM STATUS\n\n"
            f"Status: {status_str}\n"
            f"Last Collection: {last_coll}\n"
            f"Next Collection: {next_coll}\n"
            f"Queue: {scheduled_count} scheduled posts\n"
            f"Posts Published Today: {pub_today}\n"
            f"Last Telegram Post: {last_post_str}\n"
            f"Last Error: {last_err}"
        )

    def _cmd_queue(self, queue_mgr: Optional[QueueManager] = None) -> str:
        """Processes /queue command."""
        qm = queue_mgr or QueueManager()
        posts = qm.load_queue()
        due = [p for p in posts if p.get("status") in ("scheduled", "retrying")]

        if not due:
            return "📋 QUEUE MONITOR: No upcoming scheduled posts in queue."

        lines = ["📋 UPCOMING SCHEDULED POSTS\n"]
        for idx, p in enumerate(due[:10], 1):
            t_str = p.get("scheduled_time", "Immediate")
            cat = p.get("category", "NEWS").upper()
            prio = p.get("priority", "NORMAL").upper()
            title = p.get("title", "Untitled")
            st = p.get("status", "scheduled")
            lines.append(f"[{idx}] {t_str} | [{cat}] [{prio}] ({st})\n    Title: {title}\n")

        return "\n".join(lines)

    def _cmd_stats(self) -> str:
        """Processes /stats command."""
        am = AnalyticsManager()
        return am.generate_daily_report()

    def _cmd_pause(self, category: Optional[str] = None) -> str:
        """Processes /pause [category] command."""
        state = self.load_state()
        if category:
            cat_upper = category.strip().upper()
            cats = set(state.get("paused_categories", []))
            cats.add(cat_upper)
            state["paused_categories"] = list(cats)
            self.save_state(state)
            return f"⏸️ PUBLISHING PAUSED for category: {cat_upper}\n(News collection continues running)."
        else:
            state["is_paused"] = True
            self.save_state(state)
            return "⏸️ GLOBAL PUBLISHING PAUSED.\n(News collection continues running)."

    def _cmd_resume(self, category: Optional[str] = None) -> str:
        """Processes /resume [category] command."""
        state = self.load_state()
        if category:
            cat_upper = category.strip().upper()
            cats = [c for c in state.get("paused_categories", []) if c.upper() != cat_upper]
            state["paused_categories"] = cats
            self.save_state(state)
            return f"▶️ PUBLISHING RESUMED for category: {cat_upper}"
        else:
            state["is_paused"] = False
            self.save_state(state)
            return "▶️ GLOBAL PUBLISHING RESUMED."

    def _cmd_topnews(self) -> str:
        """Processes /topnews command."""
        am = AnalyticsManager()
        stories = am.get_top_stories("today")
        if not stories:
            return "🔥 TOP STORIES: No top stories recorded yet for today."

        lines = ["🔥 TODAY'S TOP STORIES\n"]
        for idx, s in enumerate(stories[:5], 1):
            lines.append(
                f"[{idx}] [{s.get('priority', 'NORMAL')}] {s.get('category', 'NEWS')} — {s.get('title')}\n"
                f"    Score: {s.get('score', 0)}/100 | Sources: {s.get('source_count', 1)}"
            )
        return "\n\n".join(lines)

    def _cmd_retry(self, queue_mgr: Optional[QueueManager] = None) -> str:
        """Processes /retry command cleanly, preventing duplicate publishing."""
        qm = queue_mgr or QueueManager()
        posts = qm.load_queue()
        pub_history = deduplicator.load_published_history()

        reset_count = 0
        skipped_count = 0

        for p in posts:
            st = p.get("status")
            if st in ("retrying", "permanently_failed"):
                url = p.get("original_url") or p.get("url", "")
                if url and deduplicator.is_duplicate_url(url, pub_history):
                    p["status"] = "published"
                    skipped_count += 1
                else:
                    p["status"] = "scheduled"
                    p["retry_count"] = 0
                    reset_count += 1

        if reset_count > 0 or skipped_count > 0:
            qm.save_queue(posts)
            return f"🔄 RETRY EXECUTION COMPLETE:\n- Reset for publishing: {reset_count} posts\n- Marked published (duplicates): {skipped_count} posts"
        return "🔄 RETRY EXECUTION: No failed or retrying posts found in queue."

    def _cmd_test(self, user_id: int) -> str:
        """Processes /test command."""
        msg = f"🧪 AI NEWS AGENT — ADMIN TEST MESSAGE\n\nAuthorized User ID: {user_id}\nTimestamp: {get_ist_now().strftime('%Y-%m-%d %H:%M:%S IST')}\nSystem Operational!"
        return msg

    def poll_and_process_commands(self) -> List[Dict]:
        """
        Polls Telegram Bot getUpdates API for incoming admin commands safely.
        Non-blocking, catch-all try...except.
        """
        token = getattr(config, "TELEGRAM_BOT_TOKEN", None)
        if not token:
            return []

        try:
            from telegram import Bot
            from telegram.request import HTTPXRequest
            req = HTTPXRequest(connect_timeout=5.0, read_timeout=5.0)
            bot = Bot(token=token, request=req)

            state = self.load_state()
            last_offset = state.get("last_processed_update_id", 0)

            async def _fetch():
                return await bot.get_updates(offset=last_offset + 1, timeout=2)

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                updates = loop.run_until_complete(_fetch())
            finally:
                loop.close()

            results = []
            max_update_id = last_offset

            for u in updates:
                max_update_id = max(max_update_id, u.update_id)
                msg = u.message or u.edited_message
                if not msg or not msg.text:
                    continue

                user_id = msg.from_user.id if msg.from_user else 0
                cmd_text = msg.text.strip()

                if cmd_text.startswith("/"):
                    response = self.handle_command(user_id, cmd_text)
                    results.append({"user_id": user_id, "command": cmd_text, "response": response})

                    # Send reply back to Telegram user if authorized
                    if self.is_authorized(user_id):
                        async def _reply(cid, txt):
                            await bot.send_message(chat_id=cid, text=txt)
                        l2 = asyncio.new_event_loop()
                        asyncio.set_event_loop(l2)
                        try:
                            l2.run_until_complete(_reply(msg.chat.id, response))
                        except Exception as e:
                            logger.error("Failed to send admin reply message: %s", e)
                        finally:
                            l2.close()

            if max_update_id > last_offset:
                state["last_processed_update_id"] = max_update_id
                self.save_state(state)

            return results
        except Exception as e:
            logger.warning("Failed during admin Telegram poll: %s", e)
            return []
