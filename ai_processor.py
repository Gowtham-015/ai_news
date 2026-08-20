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
        else:
            sentences = re.split(r"(?<=[.!?])\s+", clean_desc)
            summary = " ".join(sentences[:3])
            if len(summary) < 40:
                summary = clean_desc

        headline = raw_title
        if headline.lower().startswith("video:") or headline.lower().startswith("watch:"):
            headline = headline.split(":", 1)[1].strip()

        return {
            "headline": headline,
            "summary": summary
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

        ai_result = None

        if self.model:
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
3. Produce a concise summary of 2 to 4 sentences explaining key facts.
4. Preserve exact names, organizations, and numbers.
5. If the story includes direct quotes from world leaders, sports stars, or prominent figures (e.g. Donald Trump, Kim Jong Un, Prime Minister, Coaches), preserve and highlight the direct quote in quotation marks as it drives high subscriber engagement!
6. Rewrite cleanly rather than copying long passages word-for-word.


Return ONLY a JSON object with this exact format:
{{
    "headline": "Engaging Headline Here",
    "summary": "Concise 2-4 sentence summary here."
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
            except Exception as e:
                logger.error("AI processing failed for article: '%s' (%s). Using fallback.", title, e)

        if not ai_result:
            try:
                ai_result = self._fallback_summary(article)
            except Exception as e:
                logger.error("Fallback summarization failed for article: '%s' (%s)", title, e)
                return None

        headline = ai_result.get("headline", title).strip()
        summary = ai_result.get("summary", description).strip()
        why_it_matters = ai_result.get("why_it_matters", "").strip()

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
            "published_at": article.get("published_at", "")
        }


        return post_data

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
        return self.process_article(article)
