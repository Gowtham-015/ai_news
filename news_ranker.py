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

INDIA_PRIORITY_KEYWORDS = {
    "india", "indian", "isro", "delhi", "mumbai", "bengaluru", "chennai", "kolkata",
    "ipl", "bcci", "hockey", "cricket", "chandrayaan", "gaganyaan", "upi", "made in india",
    "gdp", "modi", "sensex", "nifty", "bharat", "pakistan", "win", "victory", "defeats"
}

GEOPOLITICS_KEYWORDS = {
    "trump", "kim jong un", "white house", "geopolitics", "summit", "diplomacy",
    "sanctions", "pentagon", "foreign policy", "north korea", "us-china", "iran",
    "putin", "zelensky", "xi jinping", "biden", "kremlin", "nato"
}


CATEGORY_HIGH_PRIORITY_KEYWORDS = {
    "SPORTS": {"win", "wins", "victory", "defeats", "final", "finals", "championship", "cup", "gold", "medal", "trophy", "record", "world record", "grand prix", "tournament"},
    "TECHNOLOGY": {"ai", "gpt", "gemini", "claude", "breakthrough", "launch", "launches", "unveils", "model", "chip", "quantum", "banning", "antitrust", "policy", "robotics"},
    "ENTERTAINMENT": {"release", "premiere", "trailer", "oscars", "emmy", "grammy", "box office", "record", "series", "season", "marvel", "dc", "prime video", "netflix"},
    "NEWS": {"disaster", "earthquake", "crisis", "war", "peace", "election", "president", "prime minister", "supreme court", "treaty", "sanctions", "budget", "gdp"}
}

CATEGORY_LOW_PRIORITY_KEYWORDS = {
    "SPORTS": {"rumor", "speculation", "claims", "hopes", "thinks", "comments", "opinion"},
    "TECHNOLOGY": {"rumor", "leak", "may get", "could have", "render", "patent"},
    "ENTERTAINMENT": {"spotted", "seen", "gossip", "dating", "outfit", "vacation"},
    "NEWS": {"opinion", "column", "local update", "routine"}
}


def filter_syndicated_sources(articles: List[Dict]) -> tuple[int, list[str]]:
    """
    Identifies verbatim syndicated news copies (Jaccard title/desc similarity > 0.70)
    and returns independent source count and list of unique reporting sources.
    """
    if not articles:
        return 0, []

    from story_clusterer import extract_keywords

    unique_sources = []
    independent_count = 0

    seen_keyword_sets = []

    for art in articles:
        src = art.get("source", "")
        title = art.get("title", "")
        desc = art.get("description", "")
        kw = extract_keywords(f"{title} {desc}")

        is_syndicated = False
        for prev_kw in seen_keyword_sets:
            if not kw or not prev_kw:
                continue
            inter = kw.intersection(prev_kw)
            union = kw.union(prev_kw)
            sim = len(inter) / len(union) if union else 0
            if sim > 0.70:
                is_syndicated = True
                break

        if not is_syndicated:
            seen_keyword_sets.append(kw)
            independent_count += 1
            if src and src not in unique_sources:
                unique_sources.append(src)
        else:
            if src and src not in unique_sources:
                unique_sources.append(src)

    return max(1, independent_count), unique_sources


class NewsRanker:
    def __init__(self):
        # Validate weights at initialization
        config.validate_score_weights()
        try:
            from content_intelligence import ContentIntelligenceEngine
            self.cie = ContentIntelligenceEngine()
        except Exception:
            self.cie = None

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
        Calculates Source Quality Score (0 to 100) based on config.SOURCE_SCORES & ContentIntelligenceEngine.
        """
        scores = getattr(config, "SOURCE_SCORES", {})
        default_score = getattr(config, "DEFAULT_SOURCE_SCORE", 70)
        cfg_score = float(scores.get(source_name, default_score))
        if hasattr(self, "cie") and self.cie:
            try:
                cie_sq = self.cie.get_source_quality_score(source_name) * 100.0
                return max(cfg_score, cie_sq)
            except Exception:
                pass
        return cfg_score

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

    def calculate_category_intelligence_boost(self, cluster: Dict) -> tuple[float, str]:
        """
        Category intelligence rule:
        Evaluates category-specific priority keywords to boost major launches, results,
        and breakthroughs over minor gossip/rumors.
        """
        cat = str(cluster.get("category", "News")).upper()
        topic = cluster.get("topic", "").lower()
        words = set(re.sub(r"[^\w\s]", "", topic).split())

        high_kw = CATEGORY_HIGH_PRIORITY_KEYWORDS.get(cat, set())
        low_kw = CATEGORY_LOW_PRIORITY_KEYWORDS.get(cat, set())

        high_match = words.intersection(high_kw)
        low_match = words.intersection(low_kw)

        if high_match:
            boost = min(25.0, len(high_match) * 12.5)
            reason = f"High category priority match ({cat}: {', '.join(high_match)})"
            return boost, reason
        elif low_match:
            penalty = -15.0
            reason = f"Low category priority match ({cat}: {', '.join(low_match)})"
            return penalty, reason
        return 0.0, f"Standard category relevance for {cat}"

    def calculate_importance_score(self, cluster: Dict) -> float:
        """
        Calculates Importance Score (0 to 100) based on topic keywords, India boost, Geopolitics boost, category intelligence, and source authority.
        """
        topic = cluster.get("topic", "").lower()
        base = 55.0

        # Keyword match boost
        words = set(re.sub(r"[^\w\s]", "", topic).split())
        matched = words.intersection(HIGH_IMPORTANCE_KEYWORDS)
        keyword_boost = min(25.0, len(matched) * 12.0)

        # India news & development priority boost
        india_matched = words.intersection(INDIA_PRIORITY_KEYWORDS)
        india_boost = 25.0 if india_matched else 0.0

        # Geopolitics priority boost
        geo_matched = words.intersection(GEOPOLITICS_KEYWORDS) or ("trump" in topic or "kim" in topic)
        geo_boost = 20.0 if geo_matched else 0.0

        # Category intelligence boost/penalty
        cat_boost, _ = self.calculate_category_intelligence_boost(cluster)

        # Source count boost
        confirm_boost = min(15.0, (cluster.get("source_count", 1) - 1) * 7.5)

        return min(100.0, max(10.0, base + keyword_boost + india_boost + geo_boost + cat_boost + confirm_boost))

    def evaluate_breaking_news(self, cluster: Dict, final_score: float) -> tuple[bool, str]:
        """
        Determines breaking news classification based on multiple signals:
        - Freshness (< 2 hours / freshness_score >= 85)
        - High Importance / Crisis keywords
        - Independent source confirmation (>= 2 independent sources)
        - High Trend Velocity (>= 2.0 mentions/hr)
        - Source Quality (Tier 1 source)
        - AI Evaluation flag if present
        """
        if cluster.get("is_breaking"):
            return True, cluster.get("breaking_reason", "Pre-flagged as breaking news")

        topic = cluster.get("topic", "").lower()
        freshness = cluster.get("score_explanation", {}).get("freshness_score", 50)
        importance = cluster.get("score_explanation", {}).get("importance_score", 50)
        sources = cluster.get("independent_source_count", cluster.get("source_count", 1))
        velocity = cluster.get("trend_velocity", 0.0)
        source_name = cluster.get("best_article", {}).get("source", "")
        source_score = self.calculate_source_score(source_name)

        has_crisis_kw = any(kw in topic for kw in ["breaking", "earthquake", "tsunami", "disaster", "explosion", "attack", "emergency", "crisis", "crash"])
        
        signals = []
        if freshness >= 85:
            signals.append("freshness<2h")
        if has_crisis_kw:
            signals.append("crisis_keywords")
        if sources >= 2:
            signals.append(f"sources={sources}")
        if velocity >= 2.0:
            signals.append(f"velocity={velocity:.1f}x")
        if source_score >= 90:
            signals.append(f"tier1_source={source_name}")

        if hasattr(self, "cie") and self.cie:
            try:
                target_story = cluster.get("best_article") or cluster
                if self.cie.is_verified_breaking_news(target_story):
                    return True, "Verified breaking news signal from ContentIntelligenceEngine"
            except Exception:
                pass

        threshold = getattr(config, "BREAKING_NEWS_SCORE_THRESHOLD", 90)
        
        if has_crisis_kw and freshness >= 80:
            reason = f"Breaking crisis event detected ({', '.join(signals)})"
            return True, reason
        elif freshness >= 85 and sources >= 2 and velocity >= 2.0:
            reason = f"Rapidly escalating multi-source breaking story ({', '.join(signals)})"
            return True, reason
        elif final_score >= threshold and has_crisis_kw:
            reason = f"High-score breaking event ({final_score:.1f} score, {', '.join(signals)})"
            return True, reason

        return False, "Not classified as breaking news"

    def assign_priority(self, cluster: Dict, final_score: float) -> str:
        """
        Assigns priority levels:
        - BREAKING (Priority 1): multi-signal breaking classification
        - HIGH (Priority 2): score >= 75
        - NORMAL (Priority 3): score >= 60
        - LOW (Priority 4): score < 60
        """
        is_breaking, reason = self.evaluate_breaking_news(cluster, final_score)
        if is_breaking:
            cluster["is_breaking"] = True
            cluster["breaking_reason"] = reason
            return "BREAKING"
        elif final_score >= 75:
            return "HIGH"
        elif final_score >= 60:
            return "NORMAL"
        else:
            return "LOW"

    def calculate_composite_score(self, cluster: Dict) -> tuple[float, dict]:
        """
        Calculates final weighted composite score (0 to 100) and transparent explanation.
        """
        best_art = cluster.get("best_article", {})
        source_name = best_art.get("source", "")
        pub_at = best_art.get("published_at", "")

        # Syndicated source filtering
        articles = cluster.get("articles", [])
        indep_sources, unique_srcs = filter_syndicated_sources(articles)
        cluster["independent_source_count"] = indep_sources
        cluster["source_count"] = len(unique_srcs)

        freshness = self.calculate_freshness_score(pub_at)
        source_quality = self.calculate_source_score(source_name)
        importance = self.calculate_importance_score(cluster)
        trend = float(cluster.get("trend_score", 50))
        confirmation = self.calculate_confirmation_score(indep_sources)
        
        cat_boost, cat_reason = self.calculate_category_intelligence_boost(cluster)
        category_relevance = max(20.0, min(100.0, 75.0 + cat_boost))

        # Calculate Content Intelligence Story Value Score
        story_value_score = 70.0
        if hasattr(self, "cie") and self.cie:
            try:
                story_value_score = self.cie.calculate_story_value_score(best_art or cluster) * 100.0
            except Exception:
                pass
        cluster["story_value_score"] = round(story_value_score, 1)

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
            "story_value_score": round(story_value_score, 1),
            "category_reason": cat_reason,
            "independent_sources": indep_sources,
            "weights": {
                "freshness": w_fresh,
                "source": w_source,
                "importance": w_import,
                "trend": w_trend,
                "confirmation": w_confirm,
                "category": w_cat
            },
            "reason": f"Covered by {indep_sources} independent source(s) ({cat_reason})"
        }

        return round(final_score, 1), explanation

    def rank_clusters(self, clusters: List[Dict]) -> List[Dict]:
        """
        Ranks story clusters programmatically based on final composite score and assigns priority levels.
        Populates final_score, importance_score, priority, and score_explanation.
        """
        for cluster in clusters:
            score, explanation = self.calculate_composite_score(cluster)
            priority = self.assign_priority(cluster, score)
            cluster["final_score"] = score
            cluster["importance_score"] = explanation["importance_score"]
            cluster["priority"] = priority
            cluster["score_explanation"] = explanation

        # Sort priority mapping
        prio_order = {"BREAKING": 1, "HIGH": 2, "NORMAL": 3, "LOW": 4}
        sorted_clusters = sorted(
            clusters,
            key=lambda c: (prio_order.get(c.get("priority", "NORMAL"), 3), -c.get("final_score", 0))
        )
        logger.info("Ranked %d story clusters programmatically with priority assignment", len(sorted_clusters))
        return sorted_clusters
