"""
main.py
-------
PHASE 5 MASTER AUTOMATION AGENT for AI News Automation Agent.

Features:
- Continuous autonomous operation using APScheduler BlockingScheduler.
- Single-instance process lock protection (data/agent.lock).
- Story clustering across multi-source RSS feeds (story_clusterer.py).
- Trend detection & momentum calculation (trend_detector.py).
- Intelligent multi-factor programmatic news ranking (news_ranker.py).
- AI-assisted ranking evaluations (ai_processor.py).
- Queue-aware future scheduling (queue_manager.py).
- Exponential backoff retries for RSS and AI requests (retry_manager.py).
- Graceful shutdown handling on CTRL+C (SIGINT / SIGTERM).
- Rotating log file handler (logs/agent.log).
- Heartbeat logging and state tracking (data/agent_state.json).
- CLI flags: --daemon, --dry-run, --test, --rank-test, --status, --max-per-cat.
"""

import sys
import logging
import tempfile
from logging.handlers import RotatingFileHandler
import argparse
import signal
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Ensure UTF-8 output encoding for Windows terminal printing
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import config
from news_collector import collect_news, save_collected_news
from deduplicator import filter_duplicates, load_published_history
from story_clusterer import StoryClusterer
from trend_detector import TrendDetector
from news_ranker import NewsRanker
from ai_processor import AIProcessor
from queue_manager import QueueManager
from state_manager import StateManager
import scheduler

from story_lifecycle import StoryLifecycleManager

LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
agent_log_path = LOG_DIR / "agent.log"

rotating_handler = RotatingFileHandler(
    agent_log_path, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
)
rotating_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))

stream_handler = logging.StreamHandler()
stream_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))

logger = logging.getLogger("main_pipeline")
logger.setLevel(logging.INFO)
if not logger.handlers:
    logger.addHandler(stream_handler)
    logger.addHandler(rotating_handler)

state_mgr = StateManager()
queue_mgr = QueueManager()
clusterer = StoryClusterer()
trend_det = TrendDetector()
ranker = NewsRanker()
lifecycle_mgr = StoryLifecycleManager()

# Global lock to prevent overlapping collection cycles
_collection_in_progress = False


def execute_pipeline(
    max_per_category: int = None,
    dry_run: bool = False,
    test_mode: bool = False,
    rank_test: bool = False,
    instant_schedule: bool = False,
):

    """
    Executes the Phase 9 intelligent news automation pipeline safely.
    Queues posts to posts.json with priority and scheduled times without publishing directly.
    """
    global _collection_in_progress

    if _collection_in_progress:
        logger.warning("News collection cycle is already in progress. Skipping duplicate execution.")
        return

    _collection_in_progress = True
    now_str = datetime.now(scheduler.TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")

    # If test mode, use isolated temporary paths so test data never contaminates production files
    if test_mode:
        temp_dir = Path(tempfile.mkdtemp())
        test_posts_file = temp_dir / "posts.json"
        test_hist_file = temp_dir / "published_news.json"
        test_lifecycle_file = temp_dir / "story_lifecycle.json"
        active_queue_mgr = QueueManager(posts_filepath=test_posts_file)
        active_lifecycle_mgr = StoryLifecycleManager(filepath=test_lifecycle_file)
        active_hist_path = test_hist_file
    else:
        state_mgr.update_state(status="collecting", last_collection_at=now_str)
        active_queue_mgr = queue_mgr
        active_lifecycle_mgr = lifecycle_mgr
        active_hist_path = None

    try:
        if not test_mode:
            config.validate_config()

        if max_per_category is None:
            max_per_category = getattr(config, "POSTS_PER_CATEGORY", 2)

        if test_mode:
            max_per_category = 1

        print("\n==================================================")
        print("AI NEWS AUTOMATION AGENT")
        print("PHASE 9 — SMART TELEGRAM CONTENT INTELLIGENCE")
        print("==================================================")

        t_pipeline_start = time.perf_counter()

        # STEP 1 & 2: Load feeds & Collect news
        print("\n[1] Loading RSS feeds...")
        print("\n[2] Collecting news...")

        t_start = time.perf_counter()
        raw_articles = collect_news(max_age_hours=getattr(config, "MAX_NEWS_AGE_HOURS", 24))
        d_collect = time.perf_counter() - t_start

        cat_counts = {}
        source_collected_counts = {}
        for a in raw_articles:
            c = a.get("category", "General")
            cat_counts[c] = cat_counts.get(c, 0) + 1
            src = a.get("source", "Unknown")
            source_collected_counts[src] = source_collected_counts.get(src, 0) + 1

        emoji_map = {
            "News": "📰",
            "Technology": "💻",
            "Sports": "🏏",
            "Entertainment": "🎬",
        }

        for cat_name in ["News", "Technology", "Sports", "Entertainment"]:
            cnt = cat_counts.get(cat_name, 0)
            em = emoji_map.get(cat_name, "📌")
            print(f"{em} {cat_name}: {cnt} articles")

        if not test_mode:
            save_collected_news(raw_articles)

        # STEP 3 & 4: Deduplicate and check previously published history
        print("\n[3] Removing duplicates...")
        t_start = time.perf_counter()
        existing_posts = active_queue_mgr.load_queue()
        existing_news_ref = [
            {"url": p.get("original_url", ""), "title": p.get("title", "")}
            for p in existing_posts
        ]

        unique_articles = filter_duplicates(
            raw_articles,
            existing_articles=existing_news_ref,
            history_filepath=active_hist_path if test_mode else None
        )
        removed_dups = len(raw_articles) - len(unique_articles)
        d_dedup = time.perf_counter() - t_start
        print(f"Duplicates removed: {removed_dups}")

        print("\n[4] Removing previously published articles...")
        pub_history = load_published_history(filepath=active_hist_path) if test_mode else load_published_history()
        print(f"Previously published: {len(pub_history)}")

        # STEP 5: Story Clustering
        print("\n[5] Story Clustering...")
        t_start = time.perf_counter()
        clusters = clusterer.cluster_articles(unique_articles)
        d_cluster = time.perf_counter() - t_start
        print(f"Story clusters created: {len(clusters)}")

        # STEP 6: Trend Detection
        print("\n[6] Trend Detection & Momentum Analysis...")
        t_start = time.perf_counter()
        clusters = trend_det.analyze_trends(clusters)
        d_trend = time.perf_counter() - t_start

        # STEP 7: Programmatic News Ranking & Priority Assignment
        print("\n[7] Programmatic News Ranking & Priority Assignment...")
        t_start = time.perf_counter()
        ranked_clusters = ranker.rank_clusters(clusters)
        d_rank = time.perf_counter() - t_start

        top_score = ranked_clusters[0].get("final_score", 0) if ranked_clusters else 0
        if not test_mode:
            state_mgr.update_state(
                candidates_last_cycle=len(raw_articles),
                top_story_score=top_score
            )

        # STEP 8: AI-Assisted Ranking (if enabled)
        t_start = time.perf_counter()
        if getattr(config, "ENABLE_AI_RANKING", True):
            print("\n[8] AI-Assisted Ranking Evaluation...")
            ai_processor = AIProcessor()
            ranked_clusters = ai_processor.rank_stories_with_ai(ranked_clusters)
        else:
            ai_processor = AIProcessor()
        d_ai_rank = time.perf_counter() - t_start

        # Handle --rank-test CLI mode
        if rank_test:
            print("\n==================================================")
            print(" TOP STORY CLUSTERS (RANK TEST)")
            print("==================================================")
            for idx, cl in enumerate(ranked_clusters[:10], 1):
                best = cl["best_article"]
                exp = cl.get("score_explanation", {})
                state = active_lifecycle_mgr.get_story_state(cl)
                print(f"\n[{idx}] [{cl.get('priority')}] {best.get('category', '').upper()} - {best.get('title')}")
                print(f"    Final Score: {cl.get('final_score')} / 100 | Priority: {cl.get('priority')} | State: {state}")
                print(f"    Sources ({cl.get('source_count')}): {', '.join(cl.get('sources', []))}")
                print(f"    Breakdown: Freshness={exp.get('freshness_score')}, Source={exp.get('source_quality_score')}, Importance={exp.get('importance_score')}, Trend={exp.get('trend_score')}, Confirmation={exp.get('confirmation_score')}")
                print(f"    Reason: {exp.get('reason')}")

            print("\n[RANK TEST COMPLETE] Displayed top candidate rankings.\n")
            if not test_mode:
                state_mgr.update_state(status="running" if state_mgr.is_locked_by_me else "idle")
            return

        # STEP 9: Story Lifecycle & Category-Aware Selection
        print("\n[9] Story Lifecycle & Category-Aware Selection...")
        t_start = time.perf_counter()
        category_needs = active_queue_mgr.calculate_category_needs(target_per_cat=max_per_category, instant_schedule=instant_schedule)

        selected_clusters = []
        selected_by_cat = {}
        
        lifecycle_counts = {
            "lifecycle_new": 0,
            "lifecycle_developing": 0,
            "lifecycle_trending": 0,
            "lifecycle_resolved": 0,
            "meaningful_followups": 0,
            "rejected_followups": 0
        }

        for cl in ranked_clusters:
            st = active_lifecycle_mgr.get_story_state(cl)
            if st == "NEW":
                lifecycle_counts["lifecycle_new"] += 1
            elif st == "DEVELOPING":
                lifecycle_counts["lifecycle_developing"] += 1
            elif st == "TRENDING":
                lifecycle_counts["lifecycle_trending"] += 1
            elif st == "RESOLVED":
                lifecycle_counts["lifecycle_resolved"] += 1

            priority = cl.get("priority", "NORMAL")
            score = cl.get("final_score", 0)

            # Discard low-priority stories below threshold
            if priority == "LOW" and score < 55:
                logger.info("Skipping low-priority low-value story: '%s' (Score: %s)", cl.get("topic"), score)
                continue

            # Evaluate follow-up eligibility
            eligible, reason = active_lifecycle_mgr.is_eligible_for_followup(cl)
            if not eligible:
                lifecycle_counts["rejected_followups"] += 1
                logger.info("Skipping story duplicate update: '%s' (%s)", cl.get("topic"), reason)
                continue

            if "Follow-up" in reason or "expansion" in reason or "progression" in reason:
                cl["best_article"]["is_followup"] = True
                lifecycle_counts["meaningful_followups"] += 1

            cat = str(cl.get("category", "News")).upper()
            target_limit = category_needs.get(cat, max_per_category)

            if cat not in selected_by_cat:
                selected_by_cat[cat] = []

            # Priority exception for BREAKING or HIGH priority stories
            if len(selected_by_cat[cat]) < target_limit or priority in ("BREAKING", "HIGH"):
                selected_by_cat[cat].append(cl)
                selected_clusters.append(cl)

        source_accepted_counts = {}
        for cl in selected_clusters:
            src = cl.get("best_article", {}).get("source", "Unknown")
            source_accepted_counts[src] = source_accepted_counts.get(src, 0) + 1

        for cat_name in ["News", "Technology", "Sports", "Entertainment"]:
            cat_u = cat_name.upper()
            arts = selected_by_cat.get(cat_u, [])
            em = emoji_map.get(cat_name, "📌")
            print(f"{em} {cat_name}: {len(arts)} selected")
        d_selection = time.perf_counter() - t_start

        # STEP 10: AI Writing per selected story cluster
        print("\n[10] AI Post Generation...")
        t_start = time.perf_counter()
        generated_posts = []

        for cl in selected_clusters:
            best_art = cl.get("best_article", {})
            best_art["priority"] = cl.get("priority", "NORMAL")
            best_art["is_breaking"] = cl.get("is_breaking", False)
            best_art["final_score"] = cl.get("final_score", 60)

            post = ai_processor.generate_post(best_art)
            if post:
                generated_posts.append(post)
                # Record in story lifecycle tracking
                active_lifecycle_mgr.record_posted_story(cl)
                print(f"[OK] [{cl.get('priority')}] {post['category']} article processed: {post['title']} (Score: {cl.get('final_score')})")
        d_ai_gen = time.perf_counter() - t_start

        if dry_run:
            print("\n==================================================")
            print(" DRY RUN MODE — GENERATED TELEGRAM POSTS")
            print("==================================================")
            for idx, p in enumerate(generated_posts, 1):
                category = p.get("category", "").upper()
                em = scheduler.CATEGORY_EMOJIS.get(category, "📌")
                print(f"\n--- Post #{idx} [{em} {category}] ---")
                print(f"{em} {category}\n")
                print(f"{p['title']}\n")
                print(f"{p['content']}")
            print("\n[DRY RUN COMPLETE] No posts queued to posts.json or sent to Telegram.\n")
            if not test_mode:
                state_mgr.update_state(status="running" if state_mgr.is_locked_by_me else "idle")

        # STEP 11: Queue Management (posts.json)
        print("\n[11] Adding posts to queue...")
        t_start = time.perf_counter()
        added_count = active_queue_mgr.add_posts_to_queue(
            generated_posts,
            max_queue_size=getattr(config, "MAX_QUEUE_SIZE", 20),
            history_filepath=active_hist_path if test_mode else None,
            instant_schedule=instant_schedule
        )
        d_queue = time.perf_counter() - t_start
        print(f"[OK] Posts added to queue: {added_count}")

        d_total = time.perf_counter() - t_pipeline_start

        if not test_mode:
            interval_mins = getattr(config, "NEWS_COLLECTION_INTERVAL_MINUTES", 30)
            next_str = (datetime.now(scheduler.TIMEZONE) + timedelta(minutes=interval_mins)).strftime("%Y-%m-%d %H:%M:%S")
            state_mgr.update_state(
                status="running" if state_mgr.is_locked_by_me else "idle",
                last_successful_collection_at=now_str,
                next_collection_at=next_str,
                last_error=None
            )

        # Record Phase 10 Analytics
        try:
            from analytics_manager import AnalyticsManager
            am = AnalyticsManager()
            ai_stats = getattr(ai_processor, "stats", {})
            am.record_pipeline_run({
                "collected_count": len(raw_articles),
                "rejected_count": len(raw_articles) - len(unique_articles),
                "duplicates_count": removed_dups,
                "unique_count": len(unique_articles),
                "clusters_count": len(clusters),
                "ranked_count": len(ranked_clusters),
                "ai_processed_count": ai_stats.get("generation_requests", len(generated_posts)),
                "ai_successful_count": ai_stats.get("successful_requests", len(generated_posts)),
                "ai_failed_count": ai_stats.get("failed_requests", 0),
                "ai_filtered_before_count": len(ranked_clusters) - len(selected_clusters),
                "posts_generated_count": len(generated_posts),
                "posts_scheduled_count": added_count,
                "queue_size": len(active_queue_mgr.load_queue()),
                "durations": {
                    "collection": d_collect,
                    "deduplication": d_dedup,
                    "clustering": d_cluster,
                    "trend_detection": d_trend,
                    "ranking": d_rank,
                    "ai_ranking": d_ai_rank,
                    "selection": d_selection,
                    "ai": d_ai_gen,
                    "queue": d_queue,
                    "publishing": 0.0,
                    "total_pipeline": d_total
                },
                "lifecycle_new": lifecycle_counts["lifecycle_new"],
                "lifecycle_developing": lifecycle_counts["lifecycle_developing"],
                "lifecycle_trending": lifecycle_counts["lifecycle_trending"],
                "lifecycle_resolved": lifecycle_counts["lifecycle_resolved"],
                "meaningful_followups": lifecycle_counts["meaningful_followups"],
                "rejected_followups": lifecycle_counts["rejected_followups"],
                "category_collected": cat_counts,
                "source_collected": source_collected_counts,
                "source_accepted": source_accepted_counts,
                "top_candidates": [c.get("best_article", {}) for c in selected_clusters[:10]]
            })
            if not dry_run and not test_mode and not rank_test:
                print("\n" + am.generate_daily_report() + "\n")
        except Exception as e:
            logger.warning("Failed to record analytics: %s", e)

        if dry_run:
            return

        print("\n==================================================")
        print("PHASE 10 PIPELINE COMPLETED")
        print("Posts queued in posts.json with future scheduled times.")
        print("==================================================\n")

    except Exception as e:
        logger.error("Pipeline execution failed: %s", e)
        if not test_mode:
            state_mgr.update_state(last_error=str(e))
        if instant_schedule or not state_mgr.is_locked_by_me:
            raise e

    finally:
        _collection_in_progress = False


def heartbeat_job():
    """Periodic heartbeat logger."""
    now_str = datetime.now(scheduler.TIMEZONE).strftime("%H:%M")
    interval = getattr(config, "NEWS_COLLECTION_INTERVAL_MINUTES", 30)
    queue_counts = queue_mgr.get_queued_counts()
    total_queued = sum(queue_counts.values())

    print(f"\n[HEARTBEAT] Agent running normally.")
    print(f"Current time: {now_str}")
    print(f"Queue size: {total_queued} (Max: {getattr(config, 'MAX_QUEUE_SIZE', 20)})")
    print(f"Collection interval: Every {interval} minutes\n")


def run_daemon():
    """Runs the continuous autonomous daemon."""
    if not state_mgr.acquire_lock():
        sys.exit(1)

    # Start lightweight HTTP server for cloud platform health checks (e.g. Render / Koyeb)
    port_env = os.getenv("PORT")
    if port_env:
        try:
            import http.server
            import socketserver
            import threading

            port = int(port_env)
            class HealthHandler(http.server.SimpleHTTPRequestHandler):
                def do_GET(self):
                    self.send_response(200)
                    self.send_header("Content-type", "text/plain")
                    self.end_headers()
                    self.wfile.write(b"OK")
                def log_message(self, format, *args):
                    pass

            server = socketserver.TCPServer(("", port), HealthHandler)
            t = threading.Thread(target=server.serve_forever, daemon=True)
            t.start()
            logger.info("Health check server active on port %d", port)
        except Exception as e:
            logger.warning("Could not start health check HTTP server: %s", e)

    now_str = datetime.now(scheduler.TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")
    state_mgr.update_state(status="running", started_at=now_str)

    interval_minutes = getattr(config, "NEWS_COLLECTION_INTERVAL_MINUTES", 30)
    heartbeat_minutes = getattr(config, "HEARTBEAT_INTERVAL_MINUTES", 10)

    print("\n==================================================")
    print(" AI NEWS AUTOMATION AGENT - DAEMON MODE STARTED")
    print("==================================================")
    print(f"Collection interval: {interval_minutes} minutes")
    print(f"Max queue size: {getattr(config, 'MAX_QUEUE_SIZE', 20)}")
    print(f"Posts per category: {getattr(config, 'POSTS_PER_CATEGORY', 2)}")
    print(f"Heartbeat interval: {heartbeat_minutes} minutes")
    print(f"Intelligent Ranking: {'ENABLED' if getattr(config, 'ENABLE_INTELLIGENT_RANKING', True) else 'DISABLED'}")
    print("Press CTRL + C to stop gracefully.")
    print("--------------------------------------------------\n")

    def graceful_shutdown(signum, frame):
        print("\n\nShutting down AI News Automation Agent...")
        state_mgr.update_state(status="stopped")
        state_mgr.release_lock()
        print("Shutdown completed safely.\n")
        sys.exit(0)

    signal.signal(signal.SIGINT, graceful_shutdown)
    signal.signal(signal.SIGTERM, graceful_shutdown)

    # Initial pipeline run (queues posts with future schedule times)
    execute_pipeline()

    sched = scheduler.BlockingScheduler(timezone=scheduler.TIMEZONE)

    sched.add_job(
        scheduler.check_and_publish,
        "interval",
        seconds=scheduler.CHECK_INTERVAL_SECONDS,
        id="check_and_publish"
    )

    sched.add_job(
        execute_pipeline,
        "interval",
        minutes=interval_minutes,
        id="news_collection_pipeline"
    )

    sched.add_job(
        heartbeat_job,
        "interval",
        minutes=heartbeat_minutes,
        id="heartbeat_logger"
    )

    try:
        sched.start()
    except (KeyboardInterrupt, SystemExit):
        graceful_shutdown(None, None)


def main():
    parser = argparse.ArgumentParser(description="AI News Automation Agent - Phase 5 Master Agent")
    parser.add_argument("--daemon", action="store_true", help="Run continuous autonomous daemon")
    parser.add_argument("--cron", action="store_true", help="Run single pipeline collection and publish due posts (for cron/GitHub Actions)")
    parser.add_argument("--dry-run", action="store_true", help="Run pipeline without queueing or publishing")
    parser.add_argument("--test", action="store_true", help="Run lightweight isolated test mode")
    parser.add_argument("--rank-test", action="store_true", help="Display top ranked story clusters and explanations")
    parser.add_argument("--status", action="store_true", help="Display system status report")
    parser.add_argument("--max-per-cat", type=int, default=None, help="Override max posts per category")

    args = parser.parse_args()

    if args.status:
        state_mgr.print_status_report()
        return

    if args.daemon:
        run_daemon()
    elif args.cron:
        execute_pipeline(
            max_per_category=args.max_per_cat,
            dry_run=args.dry_run,
            test_mode=args.test,
            rank_test=args.rank_test,
            instant_schedule=True
        )
        scheduler.check_and_publish()
    else:
        execute_pipeline(
            max_per_category=args.max_per_cat,
            dry_run=args.dry_run,
            test_mode=args.test,
            rank_test=args.rank_test
        )



if __name__ == "__main__":
    main()

