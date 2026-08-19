"""
news_collector.py
-----------------
PHASE 4 of the AI News Automation Agent.

Responsible for fetching, parsing, normalizing, and quality/age filtering news articles from RSS feeds.
Includes exponential backoff retry support for network errors.

Functions:
- parse_published_time(raw_date_str): Converts raw RSS date string into timezone-aware datetime.
- is_article_too_old(published_dt, max_age_hours): Checks if article exceeds max age.
- is_quality_article(article): Applies basic quality filters.
- parse_entry(entry, source_name, category): Standardizes entry dict.
- fetch_feed(feed_info): Safely parses a single RSS feed with retry logic.
- collect_news(feeds_config=None, max_age_hours=None): Collects news across categories.
- save_collected_news(articles, filepath): Saves collected articles to JSON storage.
"""

import hashlib
import json
import logging
import re
import shutil
import tempfile
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path

import feedparser
import config
from config.feeds import FEEDS
from retry_manager import retry_with_backoff

LOG_DIR = getattr(config, "LOG_DIR_PATH", Path(__file__).parent / "logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)


logger = logging.getLogger("news_collector")
if not logger.handlers:
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)
    
    file_handler = logging.FileHandler(LOG_DIR / "agent.log", encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)
COLLECTED_NEWS_FILE = DATA_DIR / "collected_news.json"


def generate_article_id(url: str, title: str) -> str:
    """Generates a stable unique ID based on article URL or title hash."""
    seed = (url.strip() or title.strip()).encode("utf-8")
    return hashlib.sha256(seed).hexdigest()[:16]


def parse_published_time(raw_date_str: str) -> datetime | None:
    """
    Parses raw RSS date strings into timezone-aware datetime objects.
    """
    if not raw_date_str:
        return None
    try:
        dt = parsedate_to_datetime(raw_date_str)
        if dt and dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        pass

    try:
        dt = datetime.fromisoformat(raw_date_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        pass

    return None


def is_article_too_old(published_at_str: str, max_age_hours: int = 24) -> bool:
    """
    Checks if an article is older than max_age_hours.
    Returns False if publication time is missing or unparseable.
    """
    if not published_at_str or not max_age_hours:
        return False

    pub_dt = parse_published_time(published_at_str)
    if not pub_dt:
        return False

    now = datetime.now(timezone.utc)
    age = now - pub_dt
    return age > timedelta(hours=max_age_hours)


def is_quality_article(article: dict, max_age_hours: int = 24) -> bool:
    """
    Quality filter:
    - URL must be present and valid
    - Title must be present and >= 10 characters
    - Must not be older than max_age_hours
    - Rejects promotional headlines
    """
    url = article.get("url", "").strip()
    title = article.get("title", "").strip()

    if not url or not url.startswith("http"):
        return False

    if not title or len(title) < 10:
        return False

    if is_article_too_old(article.get("published_at", ""), max_age_hours=max_age_hours):
        return False

    lower_title = title.lower()
    promo_keywords = ["sponsored:", "ad:", "promoted:", "[ad]", "discount code", "coupon"]
    if any(keyword in lower_title for keyword in promo_keywords):
        return False

    return True


def parse_entry(entry: dict, source_name: str, category: str) -> dict | None:
    """
    Standardizes an RSS entry into a consistent data model.
    Handles missing fields gracefully without crashing.
    """
    url = getattr(entry, "link", "") or entry.get("link", "")
    title = getattr(entry, "title", "") or entry.get("title", "")
    
    if not url and not title:
        return None

    description = (
        getattr(entry, "summary", "") 
        or entry.get("summary", "") 
        or getattr(entry, "description", "") 
        or entry.get("description", "")
    )

    published_at = (
        getattr(entry, "published", "") 
        or entry.get("published", "") 
        or getattr(entry, "updated", "") 
        or entry.get("updated", "")
    )

    if not published_at and hasattr(entry, "published_parsed") and entry.published_parsed:
        try:
            dt = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
            published_at = dt.isoformat()
        except Exception:
            pass

    if not published_at:
        published_at = datetime.now(timezone.utc).isoformat()

    image_url = ""
    if hasattr(entry, "media_content") and entry.media_content:
        for media in entry.media_content:
            if isinstance(media, dict) and "url" in media:
                image_url = media["url"]
                break
    if not image_url and hasattr(entry, "media_thumbnail") and entry.media_thumbnail:
        for thumb in entry.media_thumbnail:
            if isinstance(thumb, dict) and "url" in thumb:
                image_url = thumb["url"]
                break
    if not image_url and hasattr(entry, "enclosures") and entry.enclosures:
        for enc in entry.enclosures:
            if getattr(enc, "type", "").startswith("image/") or enc.get("type", "").startswith("image/"):
                image_url = getattr(enc, "href", "") or enc.get("href", "")
                if image_url:
                    break

    article_id = getattr(entry, "id", "") or entry.get("id", "")
    if not article_id:
        article_id = generate_article_id(url, title)

    return {
        "id": article_id,
        "title": title.strip() or "(No title)",
        "description": description.strip(),
        "url": url.strip(),
        "source": source_name,
        "category": category,
        "published_at": published_at,
        "image_url": image_url,
    }


def fetch_feed(feed_info: dict) -> list[dict]:
    """
    Fetches and parses a single RSS feed.
    Uses exponential backoff retry for network resilience.
    """
    name = feed_info.get("name", "Unknown Source")
    url = feed_info.get("url", "")
    category = feed_info.get("category", "General")

    if not url:
        logger.warning("Feed '%s' missing URL.", name)
        return []

    logger.info("Fetching %s feed from: %s", category, name)

    @retry_with_backoff(
        max_retries=getattr(config, "MAX_RETRIES", 3),
        initial_delay=getattr(config, "RETRY_DELAY_SECONDS", 5)
    )
    def _parse():
        parsed = feedparser.parse(url)
        if parsed.bozo and isinstance(parsed.bozo_exception, (IOError, ConnectionError, OSError)):
            raise parsed.bozo_exception
        return parsed

    try:
        parsed = _parse()
        entries = parsed.entries
        articles = []
        for entry in entries:
            article = parse_entry(entry, name, category)
            if article:
                articles.append(article)

        logger.info("Retrieved %d articles from %s", len(articles), name)
        return articles

    except Exception as e:
        logger.warning("Failed to fetch feed '%s' (%s) after retries: %s. Continuing with remaining sources.", name, url, e)
        return []


def collect_news(feeds_config: dict = None, max_age_hours: int = None) -> list[dict]:
    """
    Iterates over all configured RSS categories and feeds,
    collects, normalizes, and filters articles by quality & max age.
    """
    if feeds_config is None:
        feeds_config = FEEDS
    if max_age_hours is None:
        max_age_hours = getattr(config, "MAX_NEWS_AGE_HOURS", 24)

    all_articles = []
    rejected_count = 0

    for category, feed_list in feeds_config.items():
        logger.info("--- Collecting category: %s ---", category)
        category_fetched = 0
        category_accepted = 0

        for feed in feed_list:
            feed_info = dict(feed)
            feed_info["category"] = category
            fetched = fetch_feed(feed_info)
            category_fetched += len(fetched)

            for art in fetched:
                if is_quality_article(art, max_age_hours=max_age_hours):
                    all_articles.append(art)
                    category_accepted += 1
                else:
                    rejected_count += 1

        logger.info("[OK] %s: %d fetched, %d passed quality/age filter", category, category_fetched, category_accepted)

    logger.info("Total articles collected across all feeds: %d (%d rejected)", len(all_articles), rejected_count)
    return all_articles


def save_collected_news(articles: list[dict], filepath: Path = COLLECTED_NEWS_FILE):
    """Saves collected articles cleanly to JSON file."""
    tmp_fd, tmp_path = tempfile.mkstemp(dir=filepath.parent, prefix="news_", suffix=".tmp")
    try:
        with open(tmp_fd, "w", encoding="utf-8") as f:
            json.dump(articles, f, indent=2, ensure_ascii=False)
        shutil.move(tmp_path, filepath)
        logger.info("Saved %d articles to %s", len(articles), filepath)
    except Exception as e:
        Path(tmp_path).unlink(missing_ok=True)
        logger.error("Failed to save collected news: %s", e)
