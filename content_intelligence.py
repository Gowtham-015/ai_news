"""
content_intelligence.py
------------------------
PHASE 14 of the AI News Automation Agent.

Responsible for:
1. Story Value Engine: Calculates multi-factor story value scores (Freshness, Source Quality, Momentum, Uniqueness, Importance).
2. Configurable Source Quality Tiers: Classifies sources (Reuters/BBC/AP=1.0, TechCrunch/ESPN=0.9, default=0.70).
3. Story Lifecycle Tracking: Manages states (NEW -> DEVELOPING -> TRENDING -> BREAKING -> RESOLVED).
4. Category Diversity Enforcement: Prevents category clustering while preserving breaking news priority.
5. Breaking News Verification: Ensures breaking news is backed by reliable source quality or multi-source signals.
"""

import logging
import re
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple, Any
from zoneinfo import ZoneInfo

import config
from analytics_manager import get_ist_now

logger = logging.getLogger("content_intelligence")
if not logger.handlers:
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    logger.addHandler(handler)

IST = ZoneInfo("Asia/Kolkata")

DEFAULT_SOURCE_QUALITY_SCORES = {
    "reuters": 1.0,
    "bbc": 1.0,
    "ap_news": 1.0,
    "ap": 1.0,
    "techcrunch": 0.9,
    "espn": 0.9,
    "the_verge": 0.85,
    "wired": 0.85,
    "default": 0.70
}

BREAKING_KEYWORDS = ["breaking", "urgent", "just in", "bulletin", "alert", "developing"]


class ContentIntelligenceEngine:
    def __init__(self, source_scores: Optional[dict] = None):
        self.source_scores = source_scores or getattr(config, "SOURCE_QUALITY_SCORES", DEFAULT_SOURCE_QUALITY_SCORES)

    def get_source_quality_score(self, source_name: str) -> float:
        """Looks up source reliability score from configured source quality scores."""
        if not source_name:
            return self.source_scores.get("default", 0.70)
        src_clean = str(source_name).lower().strip().replace(" ", "_").replace("-", "_")
        for key, score in self.source_scores.items():
            if key != "default" and key in src_clean:
                return float(score)
        return float(self.source_scores.get("default", 0.70))

    def is_verified_breaking_news(self, story: dict) -> bool:
        """
        Validates breaking news signal reliability:
        Requires breaking keywords AND (source quality >= threshold OR multi-source coverage >= 2).
        """
        title = story.get("title", "").lower()
        content = story.get("content", "").lower()
        text = f"{title} {content}"

        has_breaking_kw = any(re.search(r"\b" + re.escape(kw) + r"\b", text) for kw in BREAKING_KEYWORDS)
        if not has_breaking_kw:
            return False

        source_name = story.get("source", "")
        sq_score = self.get_source_quality_score(source_name)
        source_count = story.get("source_count", 1)
        min_sq = getattr(config, "BREAKING_MIN_SOURCE_QUALITY", 0.85)

        return (sq_score >= min_sq) or (source_count >= 2)

    def calculate_story_value_score(self, story: dict, published_history: Optional[list] = None) -> float:
        """
        Calculates intelligent multi-factor Story Value score:
        Score = (Freshness * 0.25) + (Source Quality * 0.25) + (Momentum * 0.20) + (Uniqueness * 0.15) + (Importance * 0.15)
        """
        # 1. Freshness Score (0.0 to 1.0)
        age_hours = 0.0
        pub_time = story.get("published_time") or story.get("published_at")
        if pub_time:
            try:
                from news_collector import parse_published_time
                dt = parse_published_time(str(pub_time)).astimezone(IST)
                now = get_ist_now()
                age_hours = max(0.0, (now - dt).total_seconds() / 3600.0)
            except Exception:
                age_hours = 1.0
        freshness_score = max(0.0, 1.0 - (age_hours / 24.0))

        # 2. Source Quality Score (0.0 to 1.0)
        source_quality_score = self.get_source_quality_score(story.get("source", ""))

        # 3. Momentum Score (0.0 to 1.0)
        source_count = int(story.get("source_count", 1))
        momentum_score = min(1.0, source_count / 5.0)

        # 4. Uniqueness Score (0.0 to 1.0)
        uniqueness_score = 1.0
        if published_history:
            title = story.get("title", "").lower()
            for prev in published_history[-50:]:
                prev_title = prev.get("title", "").lower()
                if title and prev_title:
                    common_words = set(title.split()).intersection(set(prev_title.split()))
                    if len(common_words) >= 4:
                        uniqueness_score = 0.3
                        break

        # 5. Importance Score (0.0 to 1.0)
        importance_score = 0.7
        if self.is_verified_breaking_news(story):
            importance_score = 1.0
        elif str(story.get("priority", "")).upper() == "HIGH":
            importance_score = 0.85

        story_value = (
            (freshness_score * 0.25) +
            (source_quality_score * 0.25) +
            (momentum_score * 0.20) +
            (uniqueness_score * 0.15) +
            (importance_score * 0.15)
        )
        return round(story_value, 4)

    def get_story_lifecycle_state(self, story: dict, source_count: int = 1, age_hours: float = 0.0) -> str:
        """
        Tracks story lifecycle state transitions:
        NEW -> DEVELOPING -> TRENDING -> BREAKING -> RESOLVED
        """
        if self.is_verified_breaking_news(story):
            return "BREAKING"
        if age_hours >= 24.0:
            return "RESOLVED"
        if source_count >= 4:
            return "TRENDING"
        if source_count >= 2:
            return "DEVELOPING"
        return "NEW"

    def enforce_category_diversity(self, candidate_posts: list, published_history: Optional[list] = None, max_consecutive: int = 2) -> list:
        """
        Re-orders candidate posts to prevent category clustering (e.g. no more than 2 consecutive posts of the same category).
        Genuine breaking news posts bypass diversity rules and retain top position.
        """
        if not candidate_posts:
            return []

        recent_categories = []
        if published_history:
            for p in published_history[-max_consecutive:]:
                cat = str(p.get("category", "")).upper()
                if cat:
                    recent_categories.append(cat)

        reordered = []
        remaining = list(candidate_posts)

        while remaining:
            selected_idx = None
            for idx, post in enumerate(remaining):
                # Breaking news ALWAYS gets highest priority
                if post.get("is_breaking") or self.is_verified_breaking_news(post):
                    selected_idx = idx
                    break

                post_cat = str(post.get("category", "NEWS")).upper()
                # Check if adding this post exceeds max_consecutive for the same category
                recent_window = (recent_categories + [str(p.get("category", "NEWS")).upper() for p in reordered])[-max_consecutive:]
                if len(recent_window) >= max_consecutive and all(c == post_cat for c in recent_window):
                    continue  # Skip to avoid cluster

                selected_idx = idx
                break

            if selected_idx is None:
                # Fallback if all remaining belong to the same category
                selected_idx = 0

            chosen_post = remaining.pop(selected_idx)
            reordered.append(chosen_post)

        return reordered
