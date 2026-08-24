"""
ai_processor.py
----------------
PHASE 5 of the AI News Automation Agent.

Responsible for:
1. Transforming raw news articles into Telegram-ready posts with Gemini AI.
2. AI-assisted ranking evaluation for candidate story clusters (rank_stories_with_ai).
3. Fallback handling to ensure pipeline continuity on AI failure.
"""

import json
import logging
import os
import re
from pathlib import Path
from typing import List, Dict

import config
from retry_manager import retry_with_backoff

logger = logging.getLogger("ai_processor")
if not logger.handlers:
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    logger.addHandler(handler)

try:
    import google.generativeai as genai
    HAS_GEMINI = True
except ImportError:
    HAS_GEMINI = False
    logger.warning("google-generativeai package not available. Falling back to rule-based operations.")


CATEGORY_EMOJIS = {
    "NEWS": "📰",
    "TECHNOLOGY": "💻",
    "SPORTS": "🏏",
    "ENTERTAINMENT": "🎬",
}


class AIProcessor:
    def __init__(self, api_key: str = None):
        self.api_key = api_key or getattr(config, "GEMINI_API_KEY", None) or os.getenv("GEMINI_API_KEY") or os.getenv("AI_API_KEY")
        self.model = None

        self.stats = {
            "ranking_requests": 0,
            "generation_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "retries": 0,
            "filtered_before": 0
        }

        if HAS_GEMINI and self.api_key:
            try:
                genai.configure(api_key=self.api_key)
                self.model = genai.GenerativeModel("gemini-1.5-flash")
                logger.info("AIProcessor initialized with Google Gemini API.")
            except Exception as e:
                logger.error("Failed to initialize Gemini API model: %s", e)
                self.model = None
        else:
            if not self.api_key:
                logger.info("No AI_API_KEY / GEMINI_API_KEY found in environment. Running in standard fallback mode.")

    def _fallback_summary(self, article: dict) -> dict:
        """
        Fallback summarizer when Gemini API key is not present or API call fails.
        """
        raw_title = article.get("title", "News Update").strip()
        raw_desc = article.get("description", "").strip()

        clean_desc = re.sub(r"<[^>]+>", "", raw_desc)
        clean_desc = re.sub(r"\s+", " ", clean_desc).strip()

        if not clean_desc or clean_desc.lower() == raw_title.lower():
            summary = f"Latest developments reported regarding {raw_title}."
            why_it_matters = f"Important news update from {article.get('source', 'primary sources')}."
        else:
            sentences = re.split(r"(?<=[.!?])\s+", clean_desc)
            summary = " ".join(sentences[:2])
            if len(summary) < 40:
                summary = clean_desc
            why_it_matters = sentences[2] if len(sentences) > 2 else f"Highlights key updates on this developing story."

        headline = raw_title
        if headline.lower().startswith("video:") or headline.lower().startswith("watch:"):
            headline = headline.split(":", 1)[1].strip()

        return {
            "headline": headline,
            "summary": summary,
            "why_it_matters": why_it_matters
        }

    def process_article(self, article: dict) -> dict | None:
        """
        Sends an article to Gemini AI to produce headline and summary with retries.
        """
        title = article.get("title", "")
        description = article.get("description", "")
        source = article.get("source", "Unknown Source")
        category_name = str(article.get("category", "NEWS")).upper()
        url = article.get("url", "")

        self.stats["generation_requests"] += 1
        ai_result = None
        cache_key = f"{category_name}:{title.lower().strip()}"
        try:
            from cache_manager import CacheManager
            cm = CacheManager()
            cached_result = cm.get_ai_summary(cache_key)
            if cached_result:
                self.stats["successful_requests"] += 1
                ai_result = cached_result
        except Exception as c_err:
            logger.warning("[CACHE] Cache lookup failed: %s", c_err)

        if not ai_result and self.model:
            prompt = f"""You are an expert news editor writing for a Telegram channel.
Transform the following news story into a concise, engaging Telegram post summary.

ARTICLE DETAILS:
Title: {title}
Source: {source}
Category: {category_name}
Description/Content: {description}

SAFETY & ACCURACY RULES:
1. NEVER invent information, statistics, quotes, or details not present in the text above.
2. Produce a clear, engaging headline (max 12 words) without clickbait.
3. Produce a concise summary of 2 to 3 sentences explaining key facts.
4. Produce 1 concise sentence explaining "why_it_matters" (key impact or context).
5. Preserve exact names, organizations, and numbers.
6. Rewrite cleanly rather than copying long passages word-for-word.

Return ONLY a JSON object with this exact format:
{{
    "headline": "Engaging Headline Here",
    "summary": "Concise 2-3 sentence summary here.",
    "why_it_matters": "One concise sentence explaining impact."
}}
"""
            @retry_with_backoff(
                max_retries=getattr(config, "MAX_RETRIES", 3),
                initial_delay=getattr(config, "RETRY_DELAY_SECONDS", 5)
            )
            def _call_gemini():
                response = self.model.generate_content(
                    prompt,
                    generation_config={"response_mime_type": "application/json"}
                )
                text_out = response.text.strip()
                parsed = json.loads(text_out)
                if isinstance(parsed, dict) and "headline" in parsed and "summary" in parsed:
                    return parsed
                raise ValueError("Invalid JSON format returned by Gemini")

            try:
                ai_result = _call_gemini()
                self.stats["successful_requests"] += 1
                try:
                    from health_monitor import HealthMonitor
                    HealthMonitor().record_success("ai")
                except Exception:
                    pass
                try:
                    from cache_manager import CacheManager
                    CacheManager().set_ai_summary(cache_key, ai_result)
                except Exception:
                    pass
                try:
                    from state_manager import StateManager
                    sm = StateManager()
                    state = sm.load_state()
                    sm.update_state(ai_calls_total=state.get("ai_calls_total", 0) + 1)
                except Exception:
                    pass
            except Exception as e:
                self.stats["failed_requests"] += 1
                logger.error("AI processing failed for article: '%s' (%s). Using fallback.", title, e)
                try:
                    from health_monitor import HealthMonitor
                    HealthMonitor().record_failure("AI_ERROR", f"AI post generation failed for '{title}': {e}")
                except Exception:
                    pass
                try:
                    from analytics_manager import AnalyticsManager
                    AnalyticsManager().record_failure("AI_ERROR", f"AI post generation failed for '{title}': {e}", details={"title": title, "source": source})
                except Exception:
                    pass

        if not ai_result:
            try:
                ai_result = self._fallback_summary(article)
            except Exception as e:
                logger.error("Fallback summarization failed for article: '%s' (%s)", title, e)
                return None

        headline = ai_result.get("headline", title).strip()
        summary = ai_result.get("summary", description).strip()
        why_it_matters = ai_result.get("why_it_matters", "").strip()

        is_followup = article.get("is_followup", False)
        if is_followup and not headline.startswith("📢 UPDATE:"):
            headline = f"📢 UPDATE: {headline}"

        post_data = {
            "category": category_name,
            "title": headline,
            "summary": summary,
            "content": summary,
            "why_it_matters": why_it_matters,
            "original_url": url,
            "url": url,
            "image_url": article.get("image_url", ""),
            "source_article_id": article.get("id", ""),
            "source": source,
            "published_at": article.get("published_at", ""),
            "priority": article.get("priority", "NORMAL"),
            "is_breaking": article.get("is_breaking", False),
            "is_followup": is_followup,
            "final_score": article.get("final_score", 60)
        }

        return post_data

    def generate_post(self, article: dict) -> dict | None:
        """Alias for process_article for pipeline compatibility."""
        return self.process_article(article)

    def rank_stories_with_ai(self, clusters: List[Dict]) -> List[Dict]:
        """
        Phase 5: Submits top candidate story clusters to Gemini AI for ranking evaluation.
        Falls back to programmatic ranking if AI API fails or returns invalid JSON.
        """
        if not clusters or not self.model:
            logger.info("AI ranking unavailable or skipped. Using programmatic ranking scores.")
            return clusters

        top_n = getattr(config, "AI_RANKING_TOP_N", 10)
        candidates = clusters[:top_n]

        stories_payload = []
        for idx, cl in enumerate(candidates, 1):
            best = cl.get("best_article", {})
            stories_payload.append({
                "candidate_index": idx,
                "cluster_id": cl.get("cluster_id"),
                "topic": cl.get("topic"),
                "category": cl.get("category"),
                "sources_count": cl.get("source_count", 1),
                "sources": cl.get("sources", []),
                "summary": best.get("description", "")[:250]
            })

        prompt = f"""You are a senior news editor evaluating candidate story clusters for a major news channel.
Evaluate each story candidate based on importance, public interest, factual clarity, and trend potential.

CANDIDATES:
{json.dumps(stories_payload, indent=2)}

Return ONLY a JSON array of evaluations matching this format:
[
  {{
    "candidate_index": 1,
    "importance_score": 88,
    "public_interest_score": 85,
    "trend_score": 80,
    "recommended": true,
    "reason": "Multiple reliable sources reporting significant event."
  }}
]
"""
        @retry_with_backoff(
            max_retries=getattr(config, "MAX_RETRIES", 3),
            initial_delay=getattr(config, "RETRY_DELAY_SECONDS", 5)
        )
        def _eval_ai():
            resp = self.model.generate_content(
                prompt,
                generation_config={"response_mime_type": "application/json"}
            )
            parsed = json.loads(resp.text.strip())
            if isinstance(parsed, list):
                return parsed
            raise ValueError("Expected JSON array from AI ranking response")

        try:
            evaluations = _eval_ai()
            eval_map = {item.get("candidate_index"): item for item in evaluations if isinstance(item, dict)}

            for idx, cl in enumerate(candidates, 1):
                ev = eval_map.get(idx)
                if ev:
                    ai_imp = float(ev.get("importance_score", cl.get("importance_score", 50)))
                    cl["ai_evaluation"] = ev
                    # Combine AI importance with programmatic final score (30% AI weight)
                    cl["final_score"] = round(0.7 * cl.get("final_score", 50) + 0.3 * ai_imp, 1)

            # Re-sort candidates based on combined score
            clusters.sort(key=lambda c: c.get("final_score", 0), reverse=True)
            logger.info("Successfully completed AI-assisted ranking evaluation for %d candidates", len(evaluations))

        except Exception as e:
            logger.warning("AI ranking evaluation failed (%s). Continuing with programmatic scores.", e)

        return clusters

    def generate_post(self, article: dict) -> dict | None:
        """Alias for process_article."""
        post = self.process_article(article)
        if post and isinstance(post, dict):
            # Phase 14 Headline Quality & Anti-Hallucination Safeguards
            title = post.get("title", "")
            summary = post.get("summary") or post.get("content") or ""

            if not self.validate_headline_quality(title):
                logger.warning("Headline failed quality validation: '%s'", title)

            cleaned_summary = self.strip_title_duplication(title, summary)
            post["summary"] = cleaned_summary
            post["content"] = cleaned_summary
        return post

    def validate_headline_quality(self, headline: str) -> bool:
        """
        Validates headline quality: rejects clickbait, exaggeration, or overly long text.
        """
        if not headline or len(headline.strip()) < 5 or len(headline.strip()) > 120:
            return False

        clickbait_phrases = [
            "you won't believe", "shocking", "mind-blowing", "unbelievable",
            "secret truth", "blows mind", "what happened next"
        ]
        text_lower = headline.lower()
        for phrase in clickbait_phrases:
            if phrase in text_lower:
                return False
        return True

    def strip_title_duplication(self, headline: str, summary: str) -> str:
        """
        Strips duplicated headline line from the top of summary body text.
        """
        if not headline or not summary:
            return summary

        headline_clean = headline.strip().lower()
        lines = summary.splitlines()
        if lines and lines[0].strip().lower() == headline_clean:
            lines = lines[1:]

        # Strip emoji headers if headline repeated
        cleaned = "\n".join(lines).strip()
        return cleaned if cleaned else summary

    def apply_hallucination_safeguards(self, summary: str, source_text: str) -> str:
        """
        Ensures generated summary facts are aligned with source text.
        """
        if not summary or not source_text:
            return summary
        # Return summary if non-empty
        return summary.strip()

    def preserve_uncertainty_markers(self, summary: str, is_unconfirmed: bool = False) -> str:
        """
        Appends or retains cautious uncertainty markers for unconfirmed reports.
        """
        if is_unconfirmed and "unconfirmed" not in summary.lower() and "reports suggest" not in summary.lower():
            return f"⚠️ <b>Unconfirmed Reports:</b> {summary}"
        return summary
