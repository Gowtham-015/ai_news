"""
engagement_engine.py
--------------------
PHASE 13 of the AI News Automation Agent.

Responsible for:
1. Generating interactive audience engagement features (Opinion Prompts, Prediction Polls, Weekend Specials, Rotating CTAs).
2. Strict sensitive-topic safety filtering (rejecting tragedies, deaths, accidents, crimes, disasters).
3. Configurable frequency limits & rate-limiting (max 3 polls/day, max 4 engagement posts/day).
4. Persisting engagement state in data/engagement_state.json.
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
from analytics_manager import get_ist_now, get_ist_date_str

logger = logging.getLogger("engagement_engine")
if not logger.handlers:
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    logger.addHandler(handler)

IST = ZoneInfo("Asia/Kolkata")
DATA_DIR = getattr(config, "DATA_DIR_PATH", Path(__file__).parent / "data")
ENGAGEMENT_STATE_FILE = DATA_DIR / "engagement_state.json"

SENSITIVE_KEYWORDS = [
    "dead", "death", "killed", "kill", "accident", "crash", "war", "attack",
    "tragedy", "victim", "crime", "allegation", "murder", "disaster", "suicide",
    "shooting", "fatal", "casualty", "terror", "hostage"
]

ROTATING_CTAS = [
    "💬 What's your take on this? Share your thoughts below!",
    "🔔 Stay ahead of the curve with real-time AI & Tech updates.",
    "💡 How do you think this development will impact the industry?",
    "📌 Do you agree with this update? Let us know in the comments!",
    "✨ Follow for more breaking tech & news coverage."
]


def _create_default_engagement_state() -> dict:
    return {
        "enabled": True,
        "polls_today_count": 0,
        "engagement_today_count": 0,
        "last_engagement_date": None,
        "last_poll_at": None,
        "last_engagement_at": None,
        "polls_rejected_count": 0,
        "cta_index": 0,
        "max_polls_per_day": 3,
        "max_engagement_per_day": 4
    }


class EngagementEngine:
    def __init__(self, filepath: Path = ENGAGEMENT_STATE_FILE):
        self.filepath = filepath

    def load_state(self) -> dict:
        """Loads engagement state atomically."""
        if not self.filepath.exists():
            return _create_default_engagement_state()
        try:
            with open(self.filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
        except Exception as e:
            logger.error("Failed to load engagement state (%s): %s", self.filepath, e)
        return _create_default_engagement_state()

    def save_state(self, data: dict):
        """Saves engagement state atomically."""
        self.filepath.parent.mkdir(parents=True, exist_ok=True)
        tmp_fd, tmp_path = tempfile.mkstemp(dir=self.filepath.parent, prefix="engagement_", suffix=".tmp")
        try:
            with open(tmp_fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            shutil.move(tmp_path, self.filepath)
        except Exception as e:
            Path(tmp_path).unlink(missing_ok=True)
            logger.error("Failed to save engagement state: %s", e)

    def _sync_daily_counters(self, state: dict, now_dt: Optional[datetime] = None) -> dict:
        """Resets daily counters when a new IST date starts."""
        now_ist = now_dt or get_ist_now()
        today_str = get_ist_date_str(now_ist)
        if state.get("last_engagement_date") != today_str:
            state["last_engagement_date"] = today_str
            state["polls_today_count"] = 0
            state["engagement_today_count"] = 0
        return state

    def is_sensitive_topic(self, title: str, content: str = "") -> bool:
        """
        Strict safety filter evaluating title & content against sensitive keywords.
        Returns True if story is sensitive (tragedy, death, crime, accident).
        """
        text = f"{title} {content}".lower()
        for kw in SENSITIVE_KEYWORDS:
            if re.search(r"\b" + re.escape(kw) + r"\b", text):
                return True
        return False

    def get_next_cta(self) -> str:
        """Returns the next natural CTA in sequence to prevent repetitive phrasing."""
        state = self.load_state()
        idx = state.get("cta_index", 0) % len(ROTATING_CTAS)
        cta = ROTATING_CTAS[idx]
        state["cta_index"] = idx + 1
        self.save_state(state)
        return cta

    def can_generate_poll(self, dt: Optional[datetime] = None) -> bool:
        """Checks if poll frequency limits allow poll creation."""
        state = self.load_state()
        if not state.get("enabled", True):
            return False

        now_ist = dt or get_ist_now()
        state = self._sync_daily_counters(state, now_ist)
        self.save_state(state)

        max_polls = state.get("max_polls_per_day", 3)
        if state.get("polls_today_count", 0) >= max_polls:
            return False

        last_str = state.get("last_poll_at")
        if last_str:
            try:
                last_dt = datetime.fromisoformat(last_str)
                if (now_ist - last_dt) < timedelta(hours=3):
                    return False
            except Exception:
                pass

        return True

    def can_generate_engagement(self, dt: Optional[datetime] = None) -> bool:
        """Checks if engagement frequency limits allow engagement prompt generation."""
        state = self.load_state()
        if not state.get("enabled", True):
            return False

        now_ist = dt or get_ist_now()
        state = self._sync_daily_counters(state, now_ist)
        self.save_state(state)

        max_eng = state.get("max_engagement_per_day", 4)
        if state.get("engagement_today_count", 0) >= max_eng:
            return False

        last_str = state.get("last_engagement_at")
        if last_str:
            try:
                last_dt = datetime.fromisoformat(last_str)
                if (now_ist - last_dt) < timedelta(hours=3):
                    return False
            except Exception:
                pass

        return True

    def attach_opinion_prompt(self, story: dict, dt: Optional[datetime] = None) -> dict:
        """
        Attaches a natural opinion prompt and rotating CTA to story content if non-sensitive.
        Returns modified story dictionary.
        """
        title = story.get("title", "")
        content = story.get("content") or story.get("summary") or ""

        if self.is_sensitive_topic(title, content):
            return story

        if not self.can_generate_engagement(dt):
            return story

        category = str(story.get("category", "NEWS")).upper()
        prompts_by_cat = {
            "TECHNOLOGY": "🤔 Will this technological shift change how you work or live?",
            "SPORTS": "🏆 What's your prediction for the next match?",
            "ENTERTAINMENT": "🎬 Are you planning to watch or stream this?",
            "NEWS": "🤔 What do you think about this development?"
        }

        prompt_q = prompts_by_cat.get(category, "🤔 What's your opinion on this story?")
        cta = self.get_next_cta()

        story_copy = dict(story)
        orig_content = story_copy.get("content", "")
        story_copy["content"] = f"{orig_content}\n\n{prompt_q}\n\n{cta}"

        # Update engagement state counters
        now_ist = dt or get_ist_now()
        state = self.load_state()
        state = self._sync_daily_counters(state, now_ist)
        state["engagement_today_count"] = state.get("engagement_today_count", 0) + 1
        state["last_engagement_at"] = now_ist.isoformat()
        self.save_state(state)

        return story_copy

    def generate_prediction_poll(self, story: dict, dt: Optional[datetime] = None) -> Optional[Tuple[str, List[str]]]:
        """
        Generates an interactive prediction poll payload for suitable Sports, Tech, or Entertainment topics.
        Strictly rejects sensitive topics.
        """
        title = story.get("title", "")
        content = story.get("content", "")

        if self.is_sensitive_topic(title, content):
            state = self.load_state()
            state["polls_rejected_count"] = state.get("polls_rejected_count", 0) + 1
            self.save_state(state)
            logger.info("Engagement poll rejected due to sensitive topic: '%s'", title)
            return None

        if not self.can_generate_poll(dt):
            return None

        category = str(story.get("category", "NEWS")).upper()
        raw_title = story.get("title", "")

        poll_payload = None

        if category == "SPORTS":
            if " vs " in raw_title.lower() or " v " in raw_title.lower() or " against " in raw_title.lower():
                match = re.search(r"([A-Za-z0-9\s]+?)\s+(?:vs|v|against)\s+([A-Za-z0-9\s]+)", raw_title, re.IGNORECASE)
                if match:
                    t1, t2 = match.group(1).strip(), match.group(2).strip()
                    t2 = re.sub(r"\s+(?:Premier|Final|Match|Game|Cup|League|Tournament|Series|Trophy).*", "", t2, flags=re.IGNORECASE).strip()
                    poll_payload = (f"🏆 Prediction Poll: Who will win between {t1} and {t2}?", [t1, t2, "Draw / Tie"])
            if not poll_payload:
                poll_payload = (f"🏆 Prediction Poll: Who is your pick for this match?", ["Team A", "Team B", "Undecided"])

        elif category == "TECHNOLOGY":
            poll_payload = (f"💻 Tech Poll: Will you adopt or use this new tech update?", ["🔥 Yes, immediately", "🤔 Maybe later", "❌ Not interested"])

        elif category == "ENTERTAINMENT":
            poll_payload = (f"🎬 Entertainment Poll: Are you looking forward to this release?", ["🔥 Super excited!", "👍 Will check it out", "👎 Skip it"])

        if poll_payload:
            now_ist = dt or get_ist_now()
            state = self.load_state()
            state = self._sync_daily_counters(state, now_ist)
            state["polls_today_count"] = state.get("polls_today_count", 0) + 1
            state["last_poll_at"] = now_ist.isoformat()
            self.save_state(state)

        return poll_payload

    def generate_weekend_special(self, top_stories: List[dict], dt: Optional[datetime] = None) -> Optional[dict]:
        """
        Generates formatted Weekend Special payload (🗓️ WEEKEND RECAP on Saturday, 🌟 SUNDAY READ on Sunday).
        """
        now_ist = dt or get_ist_now()
        weekday = now_ist.weekday()  # 5 = Saturday, 6 = Sunday

        if weekday not in (5, 6):
            return None

        header = "🗓️ <b>WEEKEND RECAP</b>" if weekday == 5 else "🌟 <b>SUNDAY DEEP READ</b>"
        subhead = "Top long-form stories and major developments to catch up on this weekend:"

        lines = [header, f"<i>{subhead}</i>\n"]
        for idx, s in enumerate(top_stories[:5], 1):
            cat = str(s.get("category", "NEWS")).upper()
            title = html.escape(s.get("title", ""))
            lines.append(f"<b>{idx}. [{cat}]</b> {title}")

        lines.append("\n<i>Enjoy your weekend reading with AI News Agent!</i>")

        return {
            "category": "NEWS",
            "title": f"{header} ({get_ist_date_str(now_ist)})",
            "summary": "\n".join(lines),
            "content": "\n".join(lines),
            "priority": "HIGH",
            "is_weekend_special": True
        }
