"""
news_ranker.py
--------------
PHASE 5 of the AI News Automation Agent.

Responsible for calculating transparent multi-factor composite scores (0 to 100) for story clusters based on:
- 25% Freshness Score
- 20% Source Quality Score
- 20% Importance Score
- 15% Trend Score
- 10% Cross-Source Confirmation Score
- 10% Category Relevance Score
"""

import logging
import re
from datetime import datetime, timezone, timedelta
from typing import List, Dict

import config
from news_collector import parse_published_time

logger = logging.getLogger("news_ranker")
if not logger.handlers:
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    logger.addHandler(handler)

HIGH_IMPORTANCE_KEYWORDS = {
    "breakthrough", "launches", "unveils", "announces", "war", "crisis", "deal",
    "raises", "discovers", "election", "president", "supreme court", "championship",
    "winner", "oscars", "record", "surges", "dead", "killed", "crash", "investigation"
}


class NewsRanker:
    def __init__(self):
        # Validate weights at initialization
        config.validate_score_weights()

    def calculate_freshness_score(self, published_at_str: str) -> float:
        """
        Calculates Freshness Score (0 to 100) based on age.
        """
        if not published_at_str:
            return 50.0

        pub_dt = parse_published_time(published_at_str)
        if not pub_dt:
            return 50.0

        now = datetime.now(timezone.utc)
        age = now - pub_dt

        if age < timedelta(hours=1):
            return 100.0
        elif age < timedelta(hours=3):
            return 85.0
        elif age < timedelta(hours=6):
            return 70.0
        elif age < timedelta(hours=12):
            return 55.0
        elif age < timedelta(hours=24):
            return 40.0
        else:
            return 20.0

    def calculate_source_score(self, source_name: str) -> float:
        """
        Calculates Source Quality Score (0 to 100) based on config.SOURCE_SCORES.
        """
        scores = getattr(config, "SOURCE_SCORES", {})
        default_score = getattr(config, "DEFAULT_SOURCE_SCORE", 70)
        return float(scores.get(source_name, default_score))

    def calculate_confirmation_score(self, source_count: int) -> float:
        """
        Calculates Cross-Source Confirmation Score (0 to 100).
        """
        if source_count >= 4:
            return 100.0
        elif source_count == 3:
            return 90.0
        elif source_count == 2:
            return 75.0
        else:
            return 50.0

    def calculate_importance_score(self, cluster: Dict) -> float:
        """
        Calculates Importance Score (0 to 100) based on topic keywords and source authority.
        """
        topic = cluster.get("topic", "").lower()
        base = 60.0

        # Keyword match boost
        words = set(re.sub(r"[^\w\s]", "", topic).split())
        matched = words.intersection(HIGH_IMPORTANCE_KEYWORDS)
        keyword_boost = min(25.0, len(matched) * 12.0)

        # Source count boost
        confirm_boost = min(15.0, (cluster.get("source_count", 1) - 1) * 7.5)

        return min(100.0, base + keyword_boost + confirm_boost)

    def calculate_composite_score(self, cluster: Dict) -> tuple[float, dict]:
        """
        Calculates final weighted composite score (0 to 100) and transparent explanation.
        """
        best_art = cluster.get("best_article", {})
        source_name = best_art.get("source", "")
        pub_at = best_art.get("published_at", "")

        freshness = self.calculate_freshness_score(pub_at)
        source_quality = self.calculate_source_score(source_name)
        importance = self.calculate_importance_score(cluster)
        trend = float(cluster.get("trend_score", 50))
        confirmation = self.calculate_confirmation_score(cluster.get("source_count", 1))
        category_relevance = 100.0

        w_fresh = getattr(config, "FRESHNESS_WEIGHT", 0.25)
        w_source = getattr(config, "SOURCE_WEIGHT", 0.20)
        w_import = getattr(config, "IMPORTANCE_WEIGHT", 0.20)
        w_trend = getattr(config, "TREND_WEIGHT", 0.15)
        w_confirm = getattr(config, "CONFIRMATION_WEIGHT", 0.10)
        w_cat = getattr(config, "CATEGORY_WEIGHT", 0.10)

        final_score = (
            w_fresh * freshness
            + w_source * source_quality
            + w_import * importance
            + w_trend * trend
            + w_confirm * confirmation
            + w_cat * category_relevance
        )

        explanation = {
            "freshness_score": round(freshness, 1),
            "source_quality_score": round(source_quality, 1),
            "importance_score": round(importance, 1),
            "trend_score": round(trend, 1),
            "confirmation_score": round(confirmation, 1),
            "category_relevance_score": round(category_relevance, 1),
            "weights": {
                "freshness": w_fresh,
                "source": w_source,
                "importance": w_import,
                "trend": w_trend,
                "confirmation": w_confirm,
                "category": w_cat
            },
            "reason": f"Covered by {cluster.get('source_count', 1)} source(s) with freshness={round(freshness)} and source_quality={round(source_quality)}"
        }

        return round(final_score, 1), explanation

    def rank_clusters(self, clusters: List[Dict]) -> List[Dict]:
        """
        Ranks story clusters programmatically based on final composite score.
        Populates final_score, importance_score, and score_explanation.
        """
        for cluster in clusters:
            score, explanation = self.calculate_composite_score(cluster)
            cluster["final_score"] = score
            cluster["importance_score"] = explanation["importance_score"]
            cluster["score_explanation"] = explanation

        # Sort in descending order of final_score
        sorted_clusters = sorted(clusters, key=lambda c: c.get("final_score", 0), reverse=True)
        logger.info("Ranked %d story clusters programmatically", len(sorted_clusters))
        return sorted_clusters
