"""
deduplicator.py
---------------
PHASE 3, 4 & 5 of the AI News Automation Agent.

Responsible for identifying duplicate news articles and preventing re-publication of previously posted stories.

Duplicates are detected based on:
1. Exact or canonical URL match
2. Article ID match
3. Normalized title match (fallback)
4. Persistent published news history (data/published_news.json)
"""

import json
import logging
import re
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, urlunparse

logger = logging.getLogger("deduplicator")
if not logger.handlers:
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    logger.addHandler(handler)

import config

DATA_DIR = getattr(config, "DATA_DIR_PATH", Path(__file__).parent / "data")
DATA_DIR.mkdir(parents=True, exist_ok=True)
PUBLISHED_NEWS_FILE = getattr(config, "PUBLISHED_NEWS_FILE", DATA_DIR / "published_news.json")



def normalize_url(url: str) -> str:
    """
    Normalizes a URL by stripping tracking parameters (utm_*, ref, rss),
    trailing slashes, and lowercasing scheme/netloc.
    """
    if not url:
        return ""
    try:
        parsed = urlparse(url.strip())
        clean_scheme = parsed.scheme.lower()
        clean_netloc = parsed.netloc.lower()
        clean_path = parsed.path.rstrip("/")
        
        if parsed.query:
            queryParams = parsed.query.split("&")
            filtered_params = [
                param for param in queryParams
                if not any(param.startswith(prefix) for prefix in ["utm_", "at_medium", "at_campaign", "ref=", "rss="])
            ]
            clean_query = "&".join(filtered_params)
        else:
            clean_query = ""

        return urlunparse((clean_scheme, clean_netloc, clean_path, parsed.params, clean_query, ""))
    except Exception:
        return url.strip().lower()


def is_duplicate_url(url: str, history: list = None) -> bool:
    """Returns True if normalized URL matches any entry in published history."""
    if not url:
        return False
    if history is None:
        history = load_published_history()
    norm_target = normalize_url(url)
    if not norm_target:
        return False
    for item in history:
        item_u = normalize_url(item.get("original_url") or item.get("url") or "")
        if item_u and item_u == norm_target:
            return True
    return False


def normalize_title(title: str) -> str:
    """
    Normalizes a title string for deduplication comparison:
    - Lowercase
    - Removes punctuation and special characters
    - Collapses multiple spaces
    """
    if not title:
        return ""
    text = title.lower()
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def load_published_history(filepath: Path = None) -> list[dict]:
    """Loads previously published article history from data/published_news.json."""
    if filepath is None:
        filepath = PUBLISHED_NEWS_FILE
    if not filepath.exists():
        return []
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
    except Exception as e:
        logger.error("Failed to load published history from %s: %s", filepath, e)
    return []


def record_published_history(
    articles: list[dict], 
    filepath: Path = None
):
    """
    Records newly published articles to data/published_news.json.
    Prevents re-posting in future runs.
    """
    if filepath is None:
        filepath = PUBLISHED_NEWS_FILE

    history = load_published_history(filepath)
    existing_urls = {normalize_url(item.get("url", "")) for item in history}
    existing_ids = {str(item.get("article_id", "")) for item in history}

    added = 0
    now_str = datetime.now(timezone.utc).isoformat()

    for art in articles:
        art_id = str(art.get("id") or art.get("source_article_id") or "")
        url = art.get("url") or art.get("original_url") or ""
        norm_u = normalize_url(url)

        if (norm_u and norm_u in existing_urls) or (art_id and art_id in existing_ids):
            continue

        history.append({
            "article_id": art_id,
            "url": url,
            "title": art.get("title", ""),
            "category": art.get("category", ""),
            "source": art.get("source", ""),
            "published_at": art.get("published_at", ""),
            "posted_at": now_str
        })
        if norm_u:
            existing_urls.add(norm_u)
        if art_id:
            existing_ids.add(art_id)
        added += 1

    if added > 0:
        tmp_fd, tmp_path = tempfile.mkstemp(dir=filepath.parent, prefix="pub_", suffix=".tmp")
        try:
            with open(tmp_fd, "w", encoding="utf-8") as f:
                json.dump(history, f, indent=2, ensure_ascii=False)
            shutil.move(tmp_path, filepath)
            logger.info("Recorded %d new articles to persistent published history (%s)", added, filepath)
        except Exception as e:
            Path(tmp_path).unlink(missing_ok=True)
            logger.error("Failed to save published history: %s", e)


def is_fuzzy_duplicate_title(title1: str, title2: str) -> bool:
    """
    Checks if two titles share significant keyword overlap (Jaccard similarity >= 0.45
    or matching 3+ key entity words), ignoring common stop words.
    """
    if not title1 or not title2:
        return False
    
    stop_words = {"the", "a", "an", "in", "on", "of", "to", "for", "with", "at", "by", "from", "and", "or", "is", "are", "was", "were", "be", "has", "have", "had", "it", "its", "this", "that", "after", "as", "about"}
    
    words1 = {w for w in re.sub(r"[^\w\s]", "", title1.lower()).split() if len(w) > 2 and w not in stop_words}
    words2 = {w for w in re.sub(r"[^\w\s]", "", title2.lower()).split() if len(w) > 2 and w not in stop_words}
    
    if not words1 or not words2:
        return False
        
    common = words1.intersection(words2)
    if len(common) >= 3:
        return True
        
    jaccard = len(common) / len(words1.union(words2))
    return jaccard >= 0.45


def filter_duplicates(
    articles: list[dict],
    existing_articles: list[dict] = None,
    history_filepath: Path = None
) -> tuple[list[dict], int, int]:
    """
    Filters duplicate articles from a list of collected articles.
    Compares against:
    1. Batch duplicates (within current collection)
    2. Previously published history (published_news.json)
    3. Fuzzy title & key entity overlap
    """
    if history_filepath is None:
        history_filepath = PUBLISHED_NEWS_FILE

    seen_ids = set()
    seen_urls = set()
    seen_titles = set()
    history_raw_titles = []

    # Pre-populate from published history
    history = load_published_history(history_filepath)
    history_duplicates_count = 0

    for item in history:
        if item.get("article_id"):
            seen_ids.add(str(item["article_id"]))
        if item.get("url"):
            seen_urls.add(normalize_url(item["url"]))
        if item.get("title"):
            history_raw_titles.append(item["title"])
            norm_t = normalize_title(item["title"])
            if norm_t:
                seen_titles.add(norm_t)

    # Pre-populate from optional existing articles (e.g., currently scheduled posts)
    if existing_articles:
        for art in existing_articles:
            if art.get("id"):
                seen_ids.add(str(art["id"]))
            if art.get("url") or art.get("original_url"):
                seen_urls.add(normalize_url(art.get("url") or art.get("original_url")))
            if art.get("title"):
                history_raw_titles.append(art["title"])
                norm_t = normalize_title(art["title"])
                if norm_t:
                    seen_titles.add(norm_t)

    unique_articles = []
    batch_duplicates_count = 0

    for article in articles:
        art_id = str(article.get("id", ""))
        raw_url = article.get("url", "")
        norm_url = normalize_url(raw_url)
        raw_title = article.get("title", "")
        norm_title = normalize_title(raw_title)

        is_duplicate = False

        if art_id and art_id in seen_ids:
            is_duplicate = True
        elif norm_url and norm_url in seen_urls:
            is_duplicate = True
        elif norm_title and norm_title in seen_titles:
            is_duplicate = True
        elif raw_title:
            # Fuzzy match against history titles
            for prev_t in history_raw_titles:
                if is_fuzzy_duplicate_title(raw_title, prev_t):
                    is_duplicate = True
                    break

        if is_duplicate:
            batch_duplicates_count += 1
            logger.debug("Duplicate filtered: '%s' (%s)", article.get("title"), raw_url)

        else:
            if art_id:
                seen_ids.add(art_id)
            if norm_url:
                seen_urls.add(norm_url)
            if norm_title:
                seen_titles.add(norm_title)
            unique_articles.append(article)

    logger.info("Deduplication complete: %d total articles, %d duplicates removed, %d unique remaining",
                len(articles), batch_duplicates_count, len(unique_articles))

    return unique_articles
