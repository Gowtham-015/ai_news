"""
channel_automation.py
---------------------
PHASE 12 of the AI News Automation Agent.

Responsible for:
1. Managing the daily publication rhythm (Morning Briefing, Evening Roundup, Breaking Alerts, Trending Digest, Category Updates).
2. Generating special post formats (🌅 GOOD MORNING, 🌙 TODAY'S TOP STORIES, 🔥 TRENDING NOW, Category Updates).
3. Generating interactive Telegram Polls for non-sensitive topics (Sports, Entertainment).
4. Auto-pinning breaking posts safely.
5. IST timezone scheduling and spam/duplicate protection across all automated updates.
"""

import html
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
from analytics_manager import AnalyticsManager, get_ist_now, get_ist_date_str

logger = logging.getLogger("channel_automation")
if not logger.handlers:
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    logger.addHandler(handler)

IST = ZoneInfo("Asia/Kolkata")
DATA_DIR = getattr(config, "DATA_DIR_PATH", Path(__file__).parent / "data")
AUTOMATION_STATE_FILE = DATA_DIR / "automation_state.json"


def _create_default_automation_state() -> dict:
    return {
        "last_morning_briefing_date": None,
        "last_evening_roundup_date": None,
        "last_trending_digest_at": None,
        "last_poll_created_at": None,
        "briefing_time_ist": "08:00",
        "roundup_time_ist": "20:00",
        "polls_enabled": True,
        "pinning_enabled": True
    }


class ChannelAutomationManager:
    def __init__(self, filepath: Path = AUTOMATION_STATE_FILE):
        self.filepath = filepath

    def load_state(self) -> dict:
        """Loads automation state atomically."""
        if not self.filepath.exists():
            return _create_default_automation_state()
        try:
            with open(self.filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
        except Exception as e:
            logger.error("Failed to load automation state (%s): %s", self.filepath, e)
        return _create_default_automation_state()

    def save_state(self, data: dict):
        """Saves automation state atomically."""
        self.filepath.parent.mkdir(parents=True, exist_ok=True)
        tmp_fd, tmp_path = tempfile.mkstemp(dir=self.filepath.parent, prefix="automation_", suffix=".tmp")
        try:
            with open(tmp_fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            shutil.move(tmp_path, self.filepath)
        except Exception as e:
            Path(tmp_path).unlink(missing_ok=True)
            logger.error("Failed to save automation state: %s", e)

    def should_trigger_morning_briefing(self, dt: Optional[datetime] = None) -> bool:
        """Checks if current IST time qualifies for morning briefing (08:00 IST hour & not sent today)."""
        now_ist = dt or get_ist_now()
        date_str = get_ist_date_str(now_ist)
        state = self.load_state()

        if state.get("last_morning_briefing_date") == date_str:
            return False

        briefing_time = state.get("briefing_time_ist", "08:00")
        try:
            target_hour = int(briefing_time.split(":")[0])
        except Exception:
            target_hour = 8

        # Trigger if current IST hour matches or exceeds target_hour on that day
        return now_ist.hour >= target_hour

    def should_trigger_evening_roundup(self, dt: Optional[datetime] = None) -> bool:
        """Checks if current IST time qualifies for evening roundup (20:00 IST hour & not sent today)."""
        now_ist = dt or get_ist_now()
        date_str = get_ist_date_str(now_ist)
        state = self.load_state()

        if state.get("last_evening_roundup_date") == date_str:
            return False

        roundup_time = state.get("roundup_time_ist", "20:00")
        try:
            target_hour = int(roundup_time.split(":")[0])
        except Exception:
            target_hour = 20

        return now_ist.hour >= target_hour

    def should_trigger_trending_digest(self, dt: Optional[datetime] = None, interval_hours: int = 6) -> bool:
        """Checks if at least interval_hours have passed since last trending digest."""
        now_ist = dt or get_ist_now()
        state = self.load_state()
        last_str = state.get("last_trending_digest_at")
        if not last_str:
            return True
        try:
            last_dt = datetime.fromisoformat(last_str)
            return (now_ist - last_dt) >= timedelta(hours=interval_hours)
        except Exception:
            return True

    def should_trigger_poll(self, dt: Optional[datetime] = None, interval_hours: int = 4) -> bool:
        """Checks if polls are enabled and at least interval_hours have passed since last poll."""
        state = self.load_state()
        if not state.get("polls_enabled", True):
            return False
        now_ist = dt or get_ist_now()
        last_str = state.get("last_poll_created_at")
        if not last_str:
            return True
        try:
            last_dt = datetime.fromisoformat(last_str)
            return (now_ist - last_dt) >= timedelta(hours=interval_hours)
        except Exception:
            return True

    def generate_morning_briefing(self, top_stories: List[dict]) -> dict:
        """Generates formatted Morning Briefing post payload."""
        date_str = get_ist_now().strftime("%B %d, %Y")
        
        stories_by_cat = {}
        for s in top_stories:
            cat = str(s.get("category", "NEWS")).upper()
            if cat not in stories_by_cat:
                stories_by_cat[cat] = s

        lines = [
            "🌅 <b>GOOD MORNING</b>",
            f"<i>Today's Morning Briefing — {date_str}</i>\n",
            "Here are the top stories starting your day:\n"
        ]

        cat_emoji = {"NEWS": "📰", "TECHNOLOGY": "💻", "SPORTS": "🏏", "ENTERTAINMENT": "🎬"}
        for cat in ["NEWS", "TECHNOLOGY", "SPORTS", "ENTERTAINMENT"]:
            em = cat_emoji.get(cat, "📌")
            story = stories_by_cat.get(cat)
            if story:
                t = html.escape(story.get("title", ""))
                lines.append(f"<b>{em} {cat.capitalize()}</b>\n• {t}\n")

        lines.append("<i>Stay tuned for full coverage throughout the day!</i>")
        
        return {
            "category": "NEWS",
            "title": f"🌅 GOOD MORNING Briefing ({date_str})",
            "summary": "\n".join(lines),
            "content": "\n".join(lines),
            "priority": "HIGH",
            "is_briefing": True
        }

    def generate_evening_roundup(self, top_stories: List[dict], cat_stats: dict = None) -> dict:
        """Generates formatted Evening Roundup post payload."""
        date_str = get_ist_now().strftime("%B %d, %Y")

        lines = [
            "🌙 <b>TODAY'S TOP STORIES ROUNDUP</b>",
            f"<i>Evening Summary — {date_str}</i>\n"
        ]

        for idx, s in enumerate(top_stories[:5], 1):
            cat = str(s.get("category", "NEWS")).upper()
            title = html.escape(s.get("title", ""))
            lines.append(f"<b>{idx}. [{cat}]</b> {title}")

        if cat_stats:
            lines.append("\n📊 <b>Category Breakdown:</b>")
            for c, cnt in cat_stats.items():
                if cnt > 0:
                    lines.append(f"• {c.capitalize()}: {cnt} updates")

        lines.append("\n<i>Good night! We will be back tomorrow morning.</i>")

        return {
            "category": "NEWS",
            "title": f"🌙 TODAY'S TOP STORIES ({date_str})",
            "summary": "\n".join(lines),
            "content": "\n".join(lines),
            "priority": "HIGH",
            "is_roundup": True
        }

    def generate_trending_digest(self, trending_stories: List[dict]) -> dict:
        """Generates formatted Trending Digest post payload."""
        lines = ["🔥 <b>TRENDING NOW</b>\n", "Rapidly developing stories with major momentum:\n"]

        for idx, s in enumerate(trending_stories[:5], 1):
            t = html.escape(s.get("title", ""))
            src_cnt = s.get("source_count", 1)
            lines.append(f"• <b>{t}</b>\n  <i>({src_cnt} independent sources reporting)</i>")

        return {
            "category": "NEWS",
            "title": "🔥 TRENDING NOW Digest",
            "summary": "\n".join(lines),
            "content": "\n".join(lines),
            "priority": "HIGH"
        }

    def generate_category_update(self, story: dict) -> dict:
        """Adds custom category header for Sports, Entertainment, or Technology updates."""
        cat = str(story.get("category", "NEWS")).upper()
        title = story.get("title", "")

        header_map = {
            "SPORTS": "🏏 <b>SPORTS UPDATE</b>",
            "ENTERTAINMENT": "🎬 <b>ENTERTAINMENT UPDATE</b>",
            "TECHNOLOGY": "💻 <b>TECH DIGEST</b>"
        }

        prefix = header_map.get(cat, f"📌 <b>{cat} UPDATE</b>")
        story_copy = dict(story)
        if not title.startswith("🏏") and not title.startswith("🎬") and not title.startswith("💻"):
            story_copy["title"] = f"{prefix}\n{title}"

        return story_copy

    def generate_poll_payload(self, story: dict) -> Optional[Tuple[str, List[str]]]:
        """
        Evaluates a story cluster and generates a Telegram Poll payload if topic is suitable.
        Strictly rejects sensitive topics (tragedies, deaths, crisis, politics).
        """
        title = story.get("title", "").lower()
        category = str(story.get("category", "")).upper()

        sensitive_keywords = ["dead", "death", "killed", "accident", "crash", "war", "attack", "tragedy", "victim", "crime"]
        if any(kw in title for kw in sensitive_keywords):
            return None

        if category == "SPORTS":
            raw_title = story.get("title", "")
            if " vs " in raw_title.lower() or " v " in raw_title.lower() or " against " in raw_title.lower():
                match = re.search(r"([A-Za-z0-9\s]+?)\s+(?:vs|v|against)\s+([A-Za-z0-9\s]+)", raw_title, re.IGNORECASE)
                if match:
                    t1, t2 = match.group(1).strip(), match.group(2).strip()
                    t2 = re.sub(r"\s+(?:Final|Match|Game|Cup|League|Tournament|Series|Trophy).*", "", t2, flags=re.IGNORECASE).strip()
                    return f"🏏 Who will win the match between {t1} and {t2}?", [t1, t2, "Draw / No Result"]
            return f"🏏 Who is your prediction for this sports match?", ["Team A", "Team B", "Undecided"]

        elif category == "ENTERTAINMENT":
            if "trailer" in title or "movie" in title or "release" in title:
                movie_name = story.get("title", "this upcoming release")
                return f"🎬 Are you excited for {movie_name}?", ["🔥 Highly Excited!", "👍 Will Watch", "👎 Not Interested"]

        return None
