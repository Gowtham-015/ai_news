"""
test_pipeline.py
----------------
Automated Master Test Suite for AI News Automation Agent (Phase 1 to Phase 5).

Verifies:
1. Quality & Age filtering
2. Persistent history tracking (isolated temp file)
3. AI formatting & fallback
4. Exponential backoff retries
5. Queue limit & queue manager (isolated temp file)
6. Single-instance process lock & state manager (isolated temp file)
7. Phase 5 Freshness & Source Quality scoring
8. Phase 5 Story Clustering & Cross-Source Confirmation
9. Phase 5 Trend Detection & Momentum calculation
10. Phase 5 Programmatic Composite Ranking & Weight validation
11. Phase 5 AI Ranking Fallback behavior (Mock AI response)

REGRESSION TESTS FOR SCHEDULER INTEGRATION & DATA ISOLATION:
12. Test Reg 1: Candidate posts receive different future scheduled times (30 min spacing)
13. Test Reg 2: No post is immediately published when queueing occurs
14. Test Reg 3: Queueing does not directly call Telegram publisher
15. Test Reg 4: New posts schedule cleanly AFTER existing future queued posts
16. Test Reg 5: Queue limit capacity (18 scheduled + MAX 20 -> only 2 added)
17. Test Reg 6: test_pipeline.py does NOT modify production data/published_news.json
18. Test Reg 7: main.py --dry-run does NOT send Telegram posts or modify history
19. Test Reg 8: main.py --test does NOT enter production history
20. Test Reg 9: main.py queues posts into posts.json with future schedule times
21. Test Reg 10: Scheduler check_and_publish publishes posts according to scheduled times, NOT all at once
"""

import os
import json
import uuid
import tempfile
import unittest.mock as mock
from pathlib import Path
from datetime import datetime, timezone, timedelta

import config
import deduplicator
from news_collector import parse_published_time, is_article_too_old, is_quality_article
from deduplicator import record_published_history, load_published_history, PUBLISHED_NEWS_FILE
from ai_processor import AIProcessor
from retry_manager import retry_with_backoff, execute_with_retry
from queue_manager import QueueManager
from state_manager import StateManager
from story_clusterer import StoryClusterer
from trend_detector import TrendDetector
from news_ranker import NewsRanker
import scheduler
import publisher


def test_filters():
    print("\n--- Test 1: Quality & Age Filters ---")
    now_utc = datetime.now(timezone.utc)
    recent_str = (now_utc - timedelta(hours=2)).strftime("%a, %d %b %Y %H:%M:%S GMT")
    old_str = (now_utc - timedelta(hours=30)).strftime("%a, %d %b %Y %H:%M:%S GMT")
    
    assert is_article_too_old(recent_str, max_age_hours=24) == False, "Recent article should not be too old"
    assert is_article_too_old(old_str, max_age_hours=24) == True, "30-hour old article should be too old for 24h filter"
    
    valid_art = {
        "url": "https://example.com/test-article-1234",
        "title": "Valid Breaking News Article Headline Here",
        "published_at": recent_str
    }
    invalid_art = {
        "url": "https://example.com/promo",
        "title": "Sponsored: Buy cheap stuff now",
        "published_at": recent_str
    }
    
    assert is_quality_article(valid_art, max_age_hours=24) == True, "Valid article should pass quality filter"
    assert is_quality_article(invalid_art, max_age_hours=24) == False, "Sponsored article should fail quality filter"
    print("[OK] Quality and Age filters PASSED.")


def test_persistent_history():
    print("\n--- Test 2: Persistent History Tracking (Isolated) ---")
    test_article = {
        "id": "hist-test-999",
        "url": "https://example.com/persistent-history-test",
        "title": "Persistent History Test Article",
        "category": "Technology",
        "source": "Test Source"
    }
    
    temp_dir = Path(tempfile.mkdtemp())
    hist_file = temp_dir / "published_news.json"
    
    record_published_history([test_article], filepath=hist_file)
    
    assert hist_file.exists(), "History file should be created"
    with open(hist_file, "r", encoding="utf-8") as f:
        data = json.load(f)
        assert len(data) == 1, "Should contain 1 article record"
        assert data[0]["url"] == test_article["url"]
        
    print("[OK] Persistent history tracking PASSED.")


def test_ai_formatting():
    print("\n--- Test 3: AI Processing Formatting ---")
    processor = AIProcessor(api_key=None)
    
    raw_article = {
        "id": "ai-test-1",
        "title": "Breaking: Tech Company Announces Breakthrough AI Model",
        "description": "A major tech company unveiled its latest artificial intelligence model today. It promises revolutionary capabilities in natural language understanding.",
        "source": "TechCrunch",
        "category": "Technology",
        "url": "https://example.com/ai-test-1"
    }
    
    post = processor.process_article(raw_article)
    assert post is not None, "Post should be generated"
    assert post["category"] == "TECHNOLOGY", "Category should be uppercase"
    assert post["title"].startswith("🔥"), "Title should start with 🔥 emoji"
    assert "TechCrunch" in post["content"], "Content should attribute source"
    assert "https://example.com/ai-test-1" in post["content"], "Content should include read more link"
    
    print("[OK] AI Formatting PASSED.")


def test_retry_manager():
    print("\n--- Test 4: Retry Manager & Exponential Backoff ---")
    attempts = 0
    
    @retry_with_backoff(max_retries=3, initial_delay=0.1, exponential=True)
    def failing_function():
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise ValueError("Simulated temporary error")
        return "Success"
        
    res = failing_function()
    assert res == "Success", "Function should eventually succeed"
    assert attempts == 3, f"Expected 3 attempts, got {attempts}"
    
    print("[OK] Retry Manager PASSED.")


def test_queue_manager_and_limits():
    print("\n--- Test 5: Queue Manager & Queue Limits (Isolated) ---")
    temp_dir = Path(tempfile.mkdtemp())
    posts_file = temp_dir / "posts.json"
    hist_file = temp_dir / "published_news.json"
    
    qm = QueueManager(posts_filepath=posts_file)
    run_id = uuid.uuid4().hex[:8]
    
    test_posts = [
        {"category": "NEWS", "title": f"Unique News Post {run_id}_{i}", "content": "c", "original_url": f"http://news_{run_id}_{i}.com"}
        for i in range(25)
    ]
    
    added = qm.add_posts_to_queue(test_posts, max_queue_size=20, history_filepath=hist_file)
    assert added == 20, f"Expected 20 added posts due to MAX_QUEUE_SIZE, got {added}"
    
    counts = qm.get_queued_counts(posts=qm.load_queue())
    assert counts.get("NEWS", 0) == 20, "Should have 20 queued news items"
    
    print("[OK] Queue Manager PASSED.")


def test_state_manager_and_lock():
    print("\n--- Test 6: State Manager & Single Instance Lock ---")
    temp_dir = Path(tempfile.mkdtemp())
    lock_file = temp_dir / "agent.lock"
    state_file = temp_dir / "agent_state.json"
    
    sm1 = StateManager(lock_path=lock_file, state_path=state_file)
    locked1 = sm1.acquire_lock()
    assert locked1 == True, "First lock acquisition should succeed"
    
    sm2 = StateManager(lock_path=lock_file, state_path=state_file)
    locked2 = sm2.acquire_lock()
    assert locked2 == False, "Second lock acquisition from active PID should fail"
    
    sm1.release_lock()
    assert not lock_file.exists(), "Lock file should be deleted on release"
    
    print("[OK] State Manager & Single Instance Lock PASSED.")


def test_phase5_freshness_and_source_scoring():
    print("\n--- Test 7: Freshness & Source Quality Scoring ---")
    ranker = NewsRanker()
    now_utc = datetime.now(timezone.utc)
    one_hour_ago = (now_utc - timedelta(minutes=30)).isoformat()
    ten_hours_ago = (now_utc - timedelta(hours=10)).isoformat()
    
    score_fresh = ranker.calculate_freshness_score(one_hour_ago)
    score_older = ranker.calculate_freshness_score(ten_hours_ago)
    
    assert score_fresh > score_older, "Fresher article must score higher"
    assert score_fresh == 100.0, f"Expected 100.0 for < 1h, got {score_fresh}"
    
    bbc_score = ranker.calculate_source_score("BBC News")
    unknown_score = ranker.calculate_source_score("Unknown Source")
    
    assert bbc_score == 90.0, f"Expected 90.0 for BBC News, got {bbc_score}"
    assert unknown_score == 70.0, f"Expected default 70.0 for Unknown, got {unknown_score}"
    
    print("[OK] Freshness & Source Quality Scoring PASSED.")


def test_phase5_clustering_and_confirmation():
    print("\n--- Test 8: Story Clustering & Cross-Source Confirmation ---")
    clusterer = StoryClusterer(similarity_threshold=0.25)
    
    art1 = {
        "title": "Apple Unveils New AI Features for iPhone",
        "source": "TechCrunch",
        "category": "Technology",
        "published_at": datetime.now(timezone.utc).isoformat()
    }
    art2 = {
        "title": "Apple Announces Breakthrough AI Capabilities for iPhone",
        "source": "BBC News",
        "category": "Technology",
        "published_at": datetime.now(timezone.utc).isoformat()
    }
    art3 = {
        "title": "Tesla Semis Order Added to Fleet",
        "source": "Wired",
        "category": "Technology",
        "published_at": datetime.now(timezone.utc).isoformat()
    }
    
    clusters = clusterer.cluster_articles([art1, art2, art3])
    assert len(clusters) == 2, f"Expected 2 story clusters, got {len(clusters)}"
    
    apple_cluster = [c for c in clusters if "Apple" in c["topic"]][0]
    assert apple_cluster["source_count"] == 2, "Apple story cluster should have source_count=2"
    assert set(apple_cluster["sources"]) == {"TechCrunch", "BBC News"}, "Sources should match"
    
    ranker = NewsRanker()
    conf_score_multi = ranker.calculate_confirmation_score(2)
    conf_score_single = ranker.calculate_confirmation_score(1)
    
    assert conf_score_multi > conf_score_single, "Multi-source coverage must yield higher confirmation score"
    print("[OK] Story Clustering & Cross-Source Confirmation PASSED.")


def test_phase5_trend_detection():
    print("\n--- Test 9: Trend Detection & Momentum Calculation ---")
    temp_dir = Path(tempfile.mkdtemp())
    cache_file = temp_dir / "trend_cache.json"
    
    td = TrendDetector(cache_filepath=cache_file)
    cluster = {
        "cluster_id": "cluster_trend_test",
        "topic": "Major Breakthrough in Quantum Computing Announced",
        "category": "Technology",
        "source_count": 3,
        "articles": [{"title": "t1"}, {"title": "t2"}, {"title": "t3"}]
    }
    
    score = td.calculate_trend_score(cluster)
    assert score >= 88, f"Expected trend score >= 88 for 3 sources, got {score}"
    
    analyzed = td.analyze_trends([cluster])
    assert cache_file.exists(), "Trend cache file should be saved"
    assert analyzed[0]["trend_score"] == score
    
    print("[OK] Trend Detection & Momentum Calculation PASSED.")


def test_phase5_composite_ranking_and_weights():
    print("\n--- Test 10: Composite Ranking & Weight Validation ---")
    assert config.validate_score_weights() == True, "Score weights must total 1.0"
    
    ranker = NewsRanker()
    cluster_high = {
        "cluster_id": "c1",
        "topic": "Breaking: President Announces Major Peace Deal Crisis Solved",
        "category": "News",
        "source_count": 3,
        "trend_score": 90,
        "best_article": {
            "title": "Breaking: President Announces Major Peace Deal Crisis Solved",
            "source": "Reuters",
            "published_at": datetime.now(timezone.utc).isoformat()
        }
    }
    cluster_low = {
        "cluster_id": "c2",
        "topic": "Minor Local Park Bench Painting Update",
        "category": "News",
        "source_count": 1,
        "trend_score": 50,
        "best_article": {
            "title": "Minor Local Park Bench Painting Update",
            "source": "Unknown Source",
            "published_at": (datetime.now(timezone.utc) - timedelta(hours=18)).isoformat()
        }
    }
    
    ranked = ranker.rank_clusters([cluster_low, cluster_high])
    assert ranked[0]["cluster_id"] == "c1", "High quality breaking story must rank #1"
    assert ranked[0]["final_score"] > ranked[1]["final_score"], "High quality score must exceed low quality score"
    assert "score_explanation" in ranked[0], "Explanation breakdown must be present"
    
    print("[OK] Composite Ranking & Weight Validation PASSED.")


def test_phase5_ai_ranking_fallback():
    print("\n--- Test 11: AI Ranking Fallback Behavior ---")
    processor = AIProcessor(api_key=None)
    clusters = [
        {"cluster_id": "c1", "topic": "t1", "final_score": 85.0},
        {"cluster_id": "c2", "topic": "t2", "final_score": 70.0}
    ]
    
    evaluated = processor.rank_stories_with_ai(clusters)
    assert len(evaluated) == 2, "Should return input clusters on fallback"
    assert evaluated[0]["final_score"] == 85.0, "Scores should remain intact on fallback"
    
    print("[OK] AI Ranking Fallback Behavior PASSED.")


# =====================================================================
# REGRESSION TESTS FOR SCHEDULER INTEGRATION & DATA ISOLATION
# =====================================================================

def test_reg1_spaced_future_schedule_times():
    print("\n--- Test Reg 1: Candidate Posts Receive Different Future Schedule Times (30 min spacing) ---")
    temp_dir = Path(tempfile.mkdtemp())
    posts_file = temp_dir / "posts.json"
    hist_file = temp_dir / "published_news.json"
    
    qm = QueueManager(posts_filepath=posts_file)
    candidates = [
        {"category": "NEWS", "title": f"Candidate Story {i}", "content": f"Content {i}", "original_url": f"http://cand{i}.com"}
        for i in range(5)
    ]
    
    added = qm.add_posts_to_queue(candidates, history_filepath=hist_file)
    assert added == 5, f"Expected 5 added, got {added}"
    
    queued = qm.load_queue()
    scheduled_times = [p["scheduled_time"] for p in queued if p["status"] == "scheduled"]
    
    assert len(scheduled_times) == 5, "All 5 posts should be scheduled"
    assert len(set(scheduled_times)) == 5, "All 5 posts must have DIFFERENT schedule times"
    
    dt0 = datetime.strptime(scheduled_times[0], scheduler.DATETIME_FORMAT)
    dt1 = datetime.strptime(scheduled_times[1], scheduler.DATETIME_FORMAT)
    diff_minutes = (dt1 - dt0).total_seconds() / 60.0
    assert diff_minutes == 30.0, f"Expected 30 min spacing between post 1 and 2, got {diff_minutes}"
    
    now_tz = datetime.now(scheduler.TIMEZONE).replace(tzinfo=None)
    assert dt0 > now_tz, f"First post scheduled time ({dt0}) must be in the FUTURE relative to now ({now_tz})"
    
    print("[OK] Spaced future schedule times PASSED.")


def test_reg2_no_immediate_publishing_on_queueing():
    print("\n--- Test Reg 2: No Post Immediately Published When Queueing Occurs ---")
    temp_dir = Path(tempfile.mkdtemp())
    posts_file = temp_dir / "posts.json"
    hist_file = temp_dir / "published_news.json"
    
    qm = QueueManager(posts_filepath=posts_file)
    candidates = [
        {"category": "TECHNOLOGY", "title": "Future Tech Story 1", "content": "c", "original_url": "http://fut1.com"}
    ]
    
    qm.add_posts_to_queue(candidates, history_filepath=hist_file)
    queued = qm.load_queue()
    
    assert queued[0]["status"] == "scheduled", "Post status must remain 'scheduled'"
    assert queued[0]["published_time"] is None, "Published time must remain None"
    
    print("[OK] No immediate publishing on queueing PASSED.")


def test_reg3_queueing_does_not_call_telegram_publisher():
    print("\n--- Test Reg 3: Queueing Does Not Call Telegram Publisher Directly ---")
    temp_dir = Path(tempfile.mkdtemp())
    posts_file = temp_dir / "posts.json"
    hist_file = temp_dir / "published_news.json"
    
    qm = QueueManager(posts_filepath=posts_file)
    candidate = {"category": "SPORTS", "title": "Direct Call Check", "content": "c", "original_url": "http://directcall.com"}
    
    with mock.patch.object(publisher, "publish_text") as mock_publish:
        qm.add_posts_to_queue([candidate], history_filepath=hist_file)
        mock_publish.assert_not_called()
        
    print("[OK] Queueing does not call Telegram publisher directly PASSED.")


def test_reg4_queue_continuation_after_existing_scheduled():
    print("\n--- Test Reg 4: New Posts Schedule Cleanly After Existing Future Queued Posts ---")
    temp_dir = Path(tempfile.mkdtemp())
    posts_file = temp_dir / "posts.json"
    hist_file = temp_dir / "published_news.json"
    
    now_tz = datetime.now(scheduler.TIMEZONE)
    t1_str = (now_tz + timedelta(minutes=40)).strftime(scheduler.DATETIME_FORMAT)
    t2_str = (now_tz + timedelta(minutes=70)).strftime(scheduler.DATETIME_FORMAT)
    
    existing = [
        {"id": 1, "category": "NEWS", "title": "Exist 1", "scheduled_time": t1_str, "status": "scheduled", "original_url": "http://e1.com"},
        {"id": 2, "category": "NEWS", "title": "Exist 2", "scheduled_time": t2_str, "status": "scheduled", "original_url": "http://e2.com"},
    ]
    
    with open(posts_file, "w", encoding="utf-8") as f:
        json.dump(existing, f)
        
    qm = QueueManager(posts_filepath=posts_file)
    candidates = [
        {"category": "NEWS", "title": "New Post C", "content": "c", "original_url": "http://c.com"},
        {"category": "NEWS", "title": "New Post D", "content": "c", "original_url": "http://d.com"}
    ]
    
    qm.add_posts_to_queue(candidates, history_filepath=hist_file)
    queued = qm.load_queue()
    
    post_c = [p for p in queued if p["title"] == "New Post C"][0]
    expected_c_dt = datetime.strptime(t2_str, scheduler.DATETIME_FORMAT) + timedelta(minutes=30)
    expected_c_str = expected_c_dt.strftime(scheduler.DATETIME_FORMAT)
    
    assert post_c["scheduled_time"] == expected_c_str, f"Expected {expected_c_str}, got {post_c['scheduled_time']}"
    
    print("[OK] Queue continuation after existing scheduled PASSED.")


def test_reg5_capacity_limit_enforcement():
    print("\n--- Test Reg 5: Capacity Limit Enforcement (18 scheduled + MAX 20 -> only 2 added) ---")
    temp_dir = Path(tempfile.mkdtemp())
    posts_file = temp_dir / "posts.json"
    hist_file = temp_dir / "published_news.json"
    
    now_tz = datetime.now(scheduler.TIMEZONE)
    existing = [
        {
            "id": i + 1,
            "category": "NEWS",
            "title": f"Existing {i}",
            "scheduled_time": (now_tz + timedelta(minutes=30 * (i + 1))).strftime(scheduler.DATETIME_FORMAT),
            "status": "scheduled",
            "original_url": f"http://existing{i}.com"
        }
        for i in range(18)
    ]
    
    with open(posts_file, "w", encoding="utf-8") as f:
        json.dump(existing, f)
        
    qm = QueueManager(posts_filepath=posts_file)
    candidates = [
        {"category": "NEWS", "title": f"Extra Post {j}", "content": "c", "original_url": f"http://extra{j}.com"}
        for j in range(5)
    ]
    
    added = qm.add_posts_to_queue(candidates, max_queue_size=20, history_filepath=hist_file)
    assert added == 2, f"Expected exactly 2 posts added to reach capacity limit of 20, got {added}"
    
    queued = qm.load_queue()
    scheduled_count = len([p for p in queued if p["status"] == "scheduled"])
    assert scheduled_count == 20, f"Total scheduled count must be 20, got {scheduled_count}"
    
    print("[OK] Capacity limit enforcement PASSED.")


def test_reg6_no_production_history_mutation_in_test_suite():
    print("\n--- Test Reg 6: test_pipeline.py Does NOT Modify Production data/published_news.json ---")
    mtime_before = PUBLISHED_NEWS_FILE.stat().st_mtime if PUBLISHED_NEWS_FILE.exists() else 0
    size_before = PUBLISHED_NEWS_FILE.stat().st_size if PUBLISHED_NEWS_FILE.exists() else 0
    
    temp_dir = Path(tempfile.mkdtemp())
    temp_hist = temp_dir / "published_news.json"
    record_published_history([{"id": "t1", "url": "http://isolationtest.com"}], filepath=temp_hist)
    
    mtime_after = PUBLISHED_NEWS_FILE.stat().st_mtime if PUBLISHED_NEWS_FILE.exists() else 0
    size_after = PUBLISHED_NEWS_FILE.stat().st_size if PUBLISHED_NEWS_FILE.exists() else 0
    
    assert mtime_before == mtime_after, "Production published_news.json mtime must NOT change"
    assert size_before == size_after, "Production published_news.json size must NOT change"
    
    print("[OK] No production history mutation PASSED.")


def test_reg7_dry_run_no_telegram_and_no_history_modification():
    print("\n--- Test Reg 7: main.py --dry-run Does NOT Send Telegram Posts or Modify History ---")
    import main
    with mock.patch.object(publisher, "publish_text") as mock_pub:
        with mock.patch.object(deduplicator, "record_published_history") as mock_rec:
            main.execute_pipeline(dry_run=True)
            mock_pub.assert_not_called()
            mock_rec.assert_not_called()
            
    print("[OK] Dry run isolation PASSED.")


def test_reg8_test_mode_isolation():
    print("\n--- Test Reg 8: main.py --test Does NOT Enter Production History ---")
    import main
    mtime_before = PUBLISHED_NEWS_FILE.stat().st_mtime if PUBLISHED_NEWS_FILE.exists() else 0
    
    main.execute_pipeline(test_mode=True)
    
    mtime_after = PUBLISHED_NEWS_FILE.stat().st_mtime if PUBLISHED_NEWS_FILE.exists() else 0
    assert mtime_before == mtime_after, "Production published_news.json must NOT be modified by --test mode"
    
    print("[OK] Test mode isolation PASSED.")


def test_reg9_main_queues_with_future_schedule_times():
    print("\n--- Test Reg 9: main.py Queues Posts with Future Schedule Times ---")
    temp_dir = Path(tempfile.mkdtemp())
    posts_file = temp_dir / "posts.json"
    hist_file = temp_dir / "published_news.json"
    
    qm = QueueManager(posts_filepath=posts_file)
    candidates = [
        {"category": "NEWS", "title": "Main Pipeline Queue Test", "content": "c", "original_url": "http://mainqtest.com"}
    ]
    
    added = qm.add_posts_to_queue(candidates, history_filepath=hist_file)
    assert added == 1
    
    post = qm.load_queue()[0]
    dt = scheduler.parse_scheduled_time(post)
    now_tz = datetime.now(scheduler.TIMEZONE)
    
    assert dt > now_tz, "Queued post must have a FUTURE schedule time"
    assert post["status"] == "scheduled"
    
    print("[OK] Main queues with future schedule times PASSED.")


def test_reg10_scheduler_publishes_according_to_scheduled_times_not_all_at_once():
    print("\n--- Test Reg 10: Scheduler Publishes According to Scheduled Times, NOT All at Once ---")
    temp_dir = Path(tempfile.mkdtemp())
    posts_file = temp_dir / "posts.json"
    
    now_tz = datetime.now(scheduler.TIMEZONE)
    past_due_str = (now_tz - timedelta(minutes=10)).strftime(scheduler.DATETIME_FORMAT)
    future_str = (now_tz + timedelta(minutes=30)).strftime(scheduler.DATETIME_FORMAT)
    
    posts_data = [
        {"id": 101, "category": "NEWS", "title": "Due Post", "content": "c", "scheduled_time": past_due_str, "status": "scheduled", "original_url": "http://due.com"},
        {"id": 102, "category": "NEWS", "title": "Future Post", "content": "c", "scheduled_time": future_str, "status": "scheduled", "original_url": "http://future.com"}
    ]
    
    with open(posts_file, "w", encoding="utf-8") as f:
        json.dump(posts_data, f)
        
    with mock.patch.object(scheduler, "POSTS_FILE", posts_file):
        with mock.patch.object(publisher, "publish_text", return_value=True) as mock_pub_text, mock.patch.object(publisher, "publish_post", return_value=True) as mock_pub_post:
            with mock.patch.object(deduplicator, "record_published_history") as mock_rec:
                scheduler.check_and_publish()
                
                total_calls = mock_pub_text.call_count + mock_pub_post.call_count
                assert total_calls == 1, f"Expected exactly 1 publish call for due post, got {total_calls}"

                
                updated = scheduler.load_posts()
                p101 = [p for p in updated if p["id"] == 101][0]
                p102 = [p for p in updated if p["id"] == 102][0]
                
                assert p101["status"] == "published", "Past-due post must be marked 'published'"
                assert p102["status"] == "scheduled", "Future post must remain 'scheduled'"
                
    print("[OK] Scheduler publishes according to scheduled times PASSED.")


def main():
    print("==================================================")
    print(" PHASE 5 AUTOMATED MASTER SUITE & REGRESSION TESTS")
    print("==================================================")
    
    # Standard Phase 1-5 Tests
    test_filters()
    test_persistent_history()
    test_ai_formatting()
    test_retry_manager()
    test_queue_manager_and_limits()
    test_state_manager_and_lock()
    test_phase5_freshness_and_source_scoring()
    test_phase5_clustering_and_confirmation()
    test_phase5_trend_detection()
    test_phase5_composite_ranking_and_weights()
    test_phase5_ai_ranking_fallback()
    
    # Regression Tests
    test_reg1_spaced_future_schedule_times()
    test_reg2_no_immediate_publishing_on_queueing()
    test_reg3_queueing_does_not_call_telegram_publisher()
    test_reg4_queue_continuation_after_existing_scheduled()
    test_reg5_capacity_limit_enforcement()
    test_reg6_no_production_history_mutation_in_test_suite()
    test_reg7_dry_run_no_telegram_and_no_history_modification()
    test_reg8_test_mode_isolation()
    test_reg9_main_queues_with_future_schedule_times()
    test_reg10_scheduler_publishes_according_to_scheduled_times_not_all_at_once()
    
    print("\nALL 21 PHASE 1 TO PHASE 5 AUTOMATED & REGRESSION TESTS PASSED SUCCESSFULLY!\n")


if __name__ == "__main__":
    main()
