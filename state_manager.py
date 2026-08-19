"""
state_manager.py
----------------
PHASE 4 & PHASE 5 of the AI News Automation Agent.

Responsible for:
1. Single-instance process lock protection (data/agent.lock) to prevent duplicate daemons.
2. Runtime status tracking (data/agent_state.json).
3. Enhanced status reporting for 'python main.py --status' (Windows Auto-Start detection & live daemon health).
"""

import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import config

logger = logging.getLogger("state_manager")
if not logger.handlers:
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    logger.addHandler(handler)

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)

LOCK_FILE = DATA_DIR / "agent.lock"
STATE_FILE = DATA_DIR / "agent_state.json"
TASK_NAME = "AI News Automation Agent"


def is_process_running(pid: int) -> bool:
    """Checks if a process with the given PID is currently active."""
    if pid <= 0:
        return False
    if sys.platform == "win32":
        import ctypes
        kernel32 = ctypes.windll.kernel32
        SYNCHRONIZE = 0x00100000
        process = kernel32.OpenProcess(SYNCHRONIZE, False, pid)
        if process:
            kernel32.CloseHandle(process)
            return True
        return False
    else:
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False


def check_autostart_task_enabled() -> bool:
    """Checks whether the Windows Scheduled Task or Startup shortcut is registered and enabled."""
    if sys.platform != "win32":
        return False
    try:
        cmd = ["schtasks", "/query", "/tn", TASK_NAME]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        if res.returncode == 0:
            return True
    except Exception:
        pass

    try:
        appdata = os.environ.get("APPDATA")
        if appdata:
            startup_shortcut = Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / f"{TASK_NAME}.lnk"
            if startup_shortcut.exists():
                return True
    except Exception:
        pass

    return False


class StateManager:
    def __init__(self, lock_path: Path = LOCK_FILE, state_path: Path = STATE_FILE):
        self.lock_path = lock_path
        self.state_path = state_path
        self.is_locked_by_me = False

    def get_running_pid(self) -> int | None:
        """Returns the PID of the active daemon if currently running, else None."""
        if not self.lock_path.exists():
            return None
        try:
            with open(self.lock_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
                pid = int(content) if content.isdigit() else None
                if pid and is_process_running(pid):
                    return pid
        except Exception:
            pass
        return None

    def acquire_lock(self) -> bool:
        """
        Attempts to acquire single-instance lock for daemon mode.
        Returns True if acquired successfully, False if another active process holds the lock.
        """
        current_pid = os.getpid()

        if self.lock_path.exists():
            try:
                with open(self.lock_path, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                    existing_pid = int(content) if content.isdigit() else None
            except Exception:
                existing_pid = None

            if existing_pid:
                if is_process_running(existing_pid):
                    logger.warning(
                        "Another instance of AI News Automation Agent is already running (PID: %d).",
                        existing_pid
                    )
                    return False
                else:
                    logger.info("Cleaning up stale lock file from previous process (PID: %d).", existing_pid)

        tmp_fd, tmp_path = tempfile.mkstemp(dir=self.lock_path.parent, prefix="lock_", suffix=".tmp")
        try:
            with open(tmp_fd, "w", encoding="utf-8") as f:
                f.write(str(current_pid))
            shutil.move(tmp_path, self.lock_path)
            self.is_locked_by_me = True
            logger.info("Acquired process lock successfully (PID: %d).", current_pid)
            return True
        except Exception as e:
            Path(tmp_path).unlink(missing_ok=True)
            logger.error("Failed to acquire lock file: %s", e)
            return False

    def release_lock(self):
        """Releases process lock upon clean shutdown."""
        if self.lock_path.exists():
            try:
                self.lock_path.unlink(missing_ok=True)
                logger.info("Released process lock cleanly.")
            except Exception as e:
                logger.error("Failed to remove lock file: %s", e)
        self.is_locked_by_me = False

    def load_state(self) -> dict:
        """Loads runtime state from data/agent_state.json."""
        if not self.state_path.exists():
            return {
                "status": "stopped",
                "started_at": None,
                "last_collection_at": None,
                "next_collection_at": None,
                "last_successful_collection_at": None,
                "queue_size": 0,
                "published_count": 0,
                "last_error": None
            }
        try:
            with open(self.state_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
        except Exception as e:
            logger.error("Failed to read state file %s: %s", self.state_path, e)
        return {"status": "unknown"}

    def update_state(self, **kwargs):
        """
        Updates agent_state.json atomically with provided key-value parameters.
        """
        state = self.load_state()
        state.update(kwargs)

        tmp_fd, tmp_path = tempfile.mkstemp(dir=self.state_path.parent, prefix="state_", suffix=".tmp")
        try:
            with open(tmp_fd, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2, ensure_ascii=False)
            shutil.move(tmp_path, self.state_path)
        except Exception as e:
            Path(tmp_path).unlink(missing_ok=True)
            logger.error("Failed to update agent_state.json: %s", e)

    def print_status_report(self):
        """Prints a human-readable agent status report for 'python main.py --status'."""
        state = self.load_state()
        running_pid = self.get_running_pid()

        if running_pid:
            current_status = "RUNNING"
            pid_str = str(running_pid)
        else:
            if state.get("last_error"):
                current_status = "ERROR"
            elif state.get("status") == "collecting":
                current_status = "COLLECTING"
            else:
                current_status = "STOPPED"
            pid_str = "N/A"

        # Calculate next collection time if available
        last_coll = state.get("last_collection_at")
        next_coll = state.get("next_collection_at")
        if not next_coll and last_coll:
            try:
                last_dt = datetime.strptime(last_coll, "%Y-%m-%d %H:%M:%S")
                interval = getattr(config, "NEWS_COLLECTION_INTERVAL_MINUTES", 30)
                next_coll = (last_dt + timedelta(minutes=interval)).strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                next_coll = "N/A"

        pub_history_file = DATA_DIR / "published_news.json"
        pub_count = 0
        if pub_history_file.exists():
            try:
                with open(pub_history_file, "r", encoding="utf-8") as f:
                    history = json.load(f)
                    if isinstance(history, list):
                        pub_count = len(history)
            except Exception:
                pass

        posts_file = Path(__file__).parent / "posts.json"
        queue_count = 0
        if posts_file.exists():
            try:
                with open(posts_file, "r", encoding="utf-8") as f:
                    posts = json.load(f)
                    if isinstance(posts, list):
                        queue_count = len([p for p in posts if p.get("status") == "scheduled"])
            except Exception:
                pass

        autostart_enabled = check_autostart_task_enabled()

        print("\n==================================================")
        print(" AI NEWS AUTOMATION AGENT - SYSTEM STATUS")
        print("==================================================")
        print(f"\nStatus: {current_status}\n")
        print(f"PID: {pid_str}\n")
        print(f"Started At:\n{state.get('started_at') or 'N/A'}\n")
        print(f"Last Collection:\n{last_coll or 'N/A'}\n")
        print(f"Next Collection:\n{next_coll or 'N/A'}\n")
        print(f"Queue:\n{queue_count} / {getattr(config, 'MAX_QUEUE_SIZE', 20)}\n")
        print(f"Published Articles:\n{pub_count}\n")
        print(f"Intelligent Ranking:\n{'ENABLED' if getattr(config, 'ENABLE_INTELLIGENT_RANKING', True) else 'DISABLED'}\n")
        print(f"Trend Detection:\n{'ENABLED' if getattr(config, 'ENABLE_TREND_DETECTION', True) else 'DISABLED'}\n")
        print(f"AI Ranking:\n{'ENABLED' if getattr(config, 'ENABLE_AI_RANKING', True) else 'DISABLED'}\n")
        print(f"Windows Auto-Start:\n{'ENABLED' if autostart_enabled else 'DISABLED'}\n")
        if state.get("last_error"):
            print(f"Last Error:\n{state.get('last_error')}\n")
        print("==================================================\n")
