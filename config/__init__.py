"""
config package initializer
---------------------------
Combines environment secrets configuration (.env loading) with RSS feed configurations
and Phase 5 Intelligent Ranking settings.
"""

import os
from dotenv import load_dotenv

from config.feeds import FEEDS

load_dotenv()

def _sanitize_val(val: str | None, key_name: str) -> str | None:
    if not val:
        return None
    val = val.strip().strip('"').strip("'")
    if "=" in val and val.split("=", 1)[0].strip().upper() in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHANNEL_ID", "BOT_KEYFILE", "SECRETFILE", "GEMINI_API_KEY", "AI_API_KEY", "KEY"):
        val = val.split("=", 1)[1].strip().strip('"').strip("'")
    if key_name == "TELEGRAM_CHANNEL_ID" and val.isdigit():
        val = f"-100{val}"
    return val

TELEGRAM_BOT_TOKEN = _sanitize_val(os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_KEYFILE"), "TELEGRAM_BOT_TOKEN")
TELEGRAM_CHANNEL_ID = _sanitize_val(os.getenv("TELEGRAM_CHANNEL_ID") or os.getenv("SECRETFILE"), "TELEGRAM_CHANNEL_ID")
GEMINI_API_KEY = _sanitize_val(os.getenv("GEMINI_API_KEY") or os.getenv("AI_API_KEY"), "GEMINI_API_KEY")

# Phase 11 Telegram Admin Control Settings
raw_admin = os.getenv("TELEGRAM_ADMIN_IDS", "")
TELEGRAM_ADMIN_IDS = [
    int(x.strip()) for x in raw_admin.split(",") if x.strip().replace("-", "").isdigit()
]


from pathlib import Path
import shutil

BASE_DIR = Path(__file__).parent.parent.resolve()

DATA_DIR_PATH = Path(os.getenv("DATA_DIR", BASE_DIR / "data")).resolve()
LOG_DIR_PATH = Path(os.getenv("LOG_DIR", BASE_DIR / "logs")).resolve()

POSTS_FILE = DATA_DIR_PATH / "posts.json"
AGENT_STATE_FILE = DATA_DIR_PATH / "agent_state.json"
COLLECTED_NEWS_FILE = DATA_DIR_PATH / "collected_news.json"
PUBLISHED_NEWS_FILE = DATA_DIR_PATH / "published_news.json"
TREND_CACHE_FILE = DATA_DIR_PATH / "trend_cache.json"
LOCK_FILE = DATA_DIR_PATH / "agent.lock"
ANALYTICS_DIR = DATA_DIR_PATH / "analytics"
ADMIN_STATE_FILE = DATA_DIR_PATH / "admin_state.json"

# Phase 10 Analytics & Statistics Settings
ANALYTICS_ENABLED = os.getenv("ANALYTICS_ENABLED", "true").lower() == "true"
ANALYTICS_RETENTION_DAYS = int(os.getenv("ANALYTICS_RETENTION_DAYS", "90"))


def ensure_data_dir_and_migrate():
    """
    Ensures DATA_DIR_PATH and LOG_DIR_PATH exist.
    If root posts.json exists and DATA_DIR/posts.json does NOT exist:
    migrates/copies root posts.json to DATA_DIR/posts.json safely.
    """
    DATA_DIR_PATH.mkdir(parents=True, exist_ok=True)
    LOG_DIR_PATH.mkdir(parents=True, exist_ok=True)

    root_posts = BASE_DIR / "posts.json"
    target_posts = POSTS_FILE

    if root_posts.exists() and not target_posts.exists():
        try:
            shutil.copy2(root_posts, target_posts)
            print(f"[config] Migrated root posts.json to {target_posts}")
        except Exception as e:
            print(f"[config] Failed to copy root posts.json to data dir: {e}")


# Phase 3 Configuration Defaults
MAX_NEWS_AGE_HOURS = int(os.getenv("MAX_NEWS_AGE_HOURS", "24"))
POSTS_PER_CATEGORY = int(os.getenv("POSTS_PER_CATEGORY", "2"))


# Phase 4 Autonomous & Reliability Settings
NEWS_COLLECTION_INTERVAL_MINUTES = int(os.getenv("NEWS_COLLECTION_INTERVAL_MINUTES", "30"))
MAX_QUEUE_SIZE = int(os.getenv("MAX_QUEUE_SIZE", "20"))
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))
RETRY_DELAY_SECONDS = int(os.getenv("RETRY_DELAY_SECONDS", "10"))
HEARTBEAT_INTERVAL_MINUTES = int(os.getenv("HEARTBEAT_INTERVAL_MINUTES", "10"))

# Phase 5 Intelligent Ranking & Trend Detection Settings
ENABLE_INTELLIGENT_RANKING = os.getenv("ENABLE_INTELLIGENT_RANKING", "true").lower() == "true"
ENABLE_TREND_DETECTION = os.getenv("ENABLE_TREND_DETECTION", "true").lower() == "true"
ENABLE_AI_RANKING = os.getenv("ENABLE_AI_RANKING", "true").lower() == "true"

AI_RANKING_TOP_N = int(os.getenv("AI_RANKING_TOP_N", "10"))
BREAKING_NEWS_SCORE_THRESHOLD = int(os.getenv("BREAKING_NEWS_SCORE_THRESHOLD", "90"))
ALLOW_MAJOR_STORY_UPDATES = os.getenv("ALLOW_MAJOR_STORY_UPDATES", "true").lower() == "true"

# Ranking Score Weights (Must sum to 1.0)
FRESHNESS_WEIGHT = float(os.getenv("FRESHNESS_WEIGHT", "0.25"))
SOURCE_WEIGHT = float(os.getenv("SOURCE_WEIGHT", "0.20"))
IMPORTANCE_WEIGHT = float(os.getenv("IMPORTANCE_WEIGHT", "0.20"))
TREND_WEIGHT = float(os.getenv("TREND_WEIGHT", "0.15"))
CONFIRMATION_WEIGHT = float(os.getenv("CONFIRMATION_WEIGHT", "0.10"))
CATEGORY_WEIGHT = float(os.getenv("CATEGORY_WEIGHT", "0.10"))

# Phase 7 Frequency Control & Category Balancing Defaults
MAX_POSTS_PER_HOUR = int(os.getenv("MAX_POSTS_PER_HOUR", "4"))
MAX_POSTS_PER_DAY = int(os.getenv("MAX_POSTS_PER_DAY", "30"))
MIN_POST_INTERVAL_MINUTES = int(os.getenv("MIN_POST_INTERVAL_MINUTES", "15"))
MAX_POSTS_PER_CATEGORY_PER_DAY = int(os.getenv("MAX_POSTS_PER_CATEGORY_PER_DAY", "10"))

DEFAULT_SOURCE_SCORE = int(os.getenv("DEFAULT_SOURCE_SCORE", "70"))
SOURCE_TIERS = {
    "Tier 1": ["NDTV News", "Times of India", "TOI Sports", "NDTV Sports", "The Hindu", "Economic Times Tech", "BBC News", "Reuters"],
    "Tier 2": ["TechCrunch", "Wired", "Variety", "ESPN Cricinfo", "Hollywood Reporter"],
    "Tier 3": ["BBC Sport", "The Verge"]
}

SOURCE_SCORES = {
    "NDTV News": 95,
    "Times of India": 95,
    "TOI Sports": 95,
    "NDTV Sports": 95,
    "The Hindu": 95,
    "Economic Times Tech": 95,
    "ESPN Cricinfo": 90,
    "BBC News": 90,
    "Reuters": 90,
    "TechCrunch": 85,
    "Wired": 85,
    "Variety": 85,
    "Hollywood Reporter": 85,
    "BBC Sport": 75,
}





def validate_score_weights() -> bool:
    """Validates that score weights total exactly 1.0."""
    total = (
        FRESHNESS_WEIGHT
        + SOURCE_WEIGHT
        + IMPORTANCE_WEIGHT
        + TREND_WEIGHT
        + CONFIRMATION_WEIGHT
        + CATEGORY_WEIGHT
    )
    if round(total, 4) != 1.0:
        raise ValueError(f"Ranking weights must sum to 1.0 (current sum: {total:.4f})")
    return True


# Run validation at module import
validate_score_weights()


def validate_config():
    """
    Checks that required environment variables exist in .env.
    """
    missing = []

    if not TELEGRAM_BOT_TOKEN:
        missing.append("TELEGRAM_BOT_TOKEN")

    if not TELEGRAM_CHANNEL_ID:
        missing.append("TELEGRAM_CHANNEL_ID")

    if missing:
        missing_list = ", ".join(missing)
        raise ValueError(
            "\n\n"
            "========================================\n"
            " GITHUB ACTIONS CONFIGURATION ERROR\n"
            "========================================\n"
            f"Missing required secret value(s): {missing_list}\n\n"
            "How to fix this:\n"
            "1. Open your GitHub Repository Secrets page:\n"
            "   https://github.com/Gowtham-015/ai_news/settings/secrets/actions\n"
            "2. Click 'New repository secret' and add:\n"
            "   - TELEGRAM_BOT_TOKEN\n"
            "   - TELEGRAM_CHANNEL_ID\n"
            "3. Save the secrets and re-run the workflow.\n"
            "========================================\n"
        )


    print("[config] Configuration loaded successfully. (Token hidden for security)")


__all__ = [
    "FEEDS",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHANNEL_ID",
    "GEMINI_API_KEY",
    "DATA_DIR_PATH",
    "LOG_DIR_PATH",
    "POSTS_FILE",
    "AGENT_STATE_FILE",
    "COLLECTED_NEWS_FILE",
    "PUBLISHED_NEWS_FILE",
    "TREND_CACHE_FILE",
    "LOCK_FILE",
    "ANALYTICS_DIR",
    "ANALYTICS_ENABLED",
    "ANALYTICS_RETENTION_DAYS",
    "TELEGRAM_ADMIN_IDS",
    "ADMIN_STATE_FILE",
    "ensure_data_dir_and_migrate",
    "MAX_NEWS_AGE_HOURS",
    "POSTS_PER_CATEGORY",
    "NEWS_COLLECTION_INTERVAL_MINUTES",
    "MAX_QUEUE_SIZE",
    "MAX_RETRIES",
    "RETRY_DELAY_SECONDS",
    "HEARTBEAT_INTERVAL_MINUTES",
    "ENABLE_INTELLIGENT_RANKING",
    "ENABLE_TREND_DETECTION",
    "ENABLE_AI_RANKING",
    "AI_RANKING_TOP_N",
    "BREAKING_NEWS_SCORE_THRESHOLD",
    "ALLOW_MAJOR_STORY_UPDATES",
    "FRESHNESS_WEIGHT",
    "SOURCE_WEIGHT",
    "IMPORTANCE_WEIGHT",
    "TREND_WEIGHT",
    "CONFIRMATION_WEIGHT",
    "CATEGORY_WEIGHT",
    "DEFAULT_SOURCE_SCORE",
    "SOURCE_SCORES",
    "validate_score_weights",
    "validate_config",
]

