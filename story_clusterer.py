"""
story_clusterer.py
------------------
PHASE 5 of the AI News Automation Agent.

Responsible for grouping related articles covering the same story across multiple sources
into unified Story Clusters to prevent repetitive posts and calculate cross-source confirmation.
"""

import hashlib
import logging
import re
from typing import List, Dict

import config

logger = logging.getLogger("story_clusterer")
if not logger.handlers:
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    logger.addHandler(handler)

STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "if", "because", "as", "what", "which",
    "this", "that", "these", "those", "then", "just", "so", "than", "such", "both",
    "through", "about", "against", "between", "into", "through", "during", "before",
    "after", "above", "below", "to", "from", "up", "upon", "down", "in", "out",
    "on", "off", "over", "under", "again", "further", "then", "once", "here",
    "there", "when", "where", "why", "how", "all", "any", "both", "each", "few",
    "more", "most", "other", "some", "such", "no", "nor", "not", "only", "own",
    "same", "so", "than", "too", "very", "s", "t", "can", "will", "just", "don",
    "should", "now", "says", "said", "new", "first", "unveils", "announces",
    "features", "capabilities", "breakthrough", "major", "latest", "update",
    "details", "reports", "shows", "set", "exclusive"
}


def extract_keywords(title: str) -> set[str]:
    """Extracts normalized key words from a title string."""
    if not title:
        return set()
    cleaned = re.sub(r"[^\w\s]", "", title.lower())
    tokens = cleaned.split()
    return {t for t in tokens if len(t) > 2 and t not in STOPWORDS}


def calculate_title_similarity(title1: str, title2: str) -> float:
    """
    Calculates Jaccard keyword similarity between two article titles (0.0 to 1.0).
    """
    kw1 = extract_keywords(title1)
    kw2 = extract_keywords(title2)

    if not kw1 or not kw2:
        return 0.0

    intersection = kw1.intersection(kw2)
    union = kw1.union(kw2)

    if not union:
        return 0.0

    return len(intersection) / len(union)


class StoryClusterer:
    def __init__(self, similarity_threshold: float = 0.25):
        self.similarity_threshold = similarity_threshold

    def select_best_article(self, articles: List[Dict]) -> Dict:
        """
        Selects the best representative article from a cluster based on
        source priority score and recency.
        """
        if not articles:
            return {}

        source_scores = getattr(config, "SOURCE_SCORES", {})
        default_score = getattr(config, "DEFAULT_SOURCE_SCORE", 70)

        def article_key(art):
            source = art.get("source", "")
            src_score = source_scores.get(source, default_score)
            pub_at = art.get("published_at", "")
            return (src_score, pub_at)

        sorted_arts = sorted(articles, key=article_key, reverse=True)
        return sorted_arts[0]

    def cluster_articles(self, articles: List[Dict]) -> List[Dict]:
        """
        Groups a list of normalized articles into story clusters.
        
        Returns:
            List of Story Cluster dictionaries.
        """
        if not articles:
            return []

        clusters = []

        for article in articles:
            title = article.get("title", "")
            category = article.get("category", "News")

            matched_cluster = None

            for cluster in clusters:
                # Only cluster within the same category
                if cluster["category"].lower() != category.lower():
                    continue

                # Compare against cluster representative title
                rep_title = cluster["best_article"].get("title", "")
                sim = calculate_title_similarity(title, rep_title)

                if sim >= self.similarity_threshold:
                    matched_cluster = cluster
                    break

            if matched_cluster:
                matched_cluster["articles"].append(article)

                # Add source if unique
                src = article.get("source", "")
                if src and src not in matched_cluster["sources"]:
                    matched_cluster["sources"].append(src)
                matched_cluster["source_count"] = len(matched_cluster["sources"])

                # Re-evaluate best article
                matched_cluster["best_article"] = self.select_best_article(matched_cluster["articles"])
            else:
                cluster_id = f"cluster_{hashlib.md5(title.encode('utf-8')).hexdigest()[:10]}"
                new_cluster = {
                    "cluster_id": cluster_id,
                    "topic": title,
                    "category": category,
                    "articles": [article],
                    "sources": [article.get("source", "")] if article.get("source") else [],
                    "source_count": 1,
                    "best_article": article,
                    "trend_score": 50,
                    "importance_score": 50,
                    "final_score": 50,
                    "score_explanation": {}
                }
                clusters.append(new_cluster)

        logger.info(
            "Clustered %d articles into %d distinct story clusters",
            len(articles),
            len(clusters)
        )
        return clusters
