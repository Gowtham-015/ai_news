"""
test_ai.py
----------
Test script for Phase 3B AI Processor.
Tests transforming a sample article into a Telegram-ready post structure with headline, summary, source, and link.
"""

import sys
import json
import logging
from ai_processor import AIProcessor

# Ensure UTF-8 output encoding for Windows terminal printing
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

logging.basicConfig(level=logging.INFO)

def main():
    print("==================================================")
    print(" TESTING PHASE 3B - AI PROCESSOR")
    print("==================================================")

    sample_article = {
        "id": "sample-101",
        "title": "SpaceX Successfully Launches Next-Gen Starlink Satellites",
        "description": "SpaceX launched 23 Starlink satellites to low-Earth orbit from Cape Canaveral Space Force Station on Tuesday. The mission marks the 15th flight for the Falcon 9 first stage booster.",
        "url": "https://example.com/spacex-starlink-launch",
        "source": "Space News Daily",
        "category": "Technology",
        "published_at": "2026-08-18T12:00:00Z"
    }

    processor = AIProcessor()
    post = processor.generate_post(sample_article)

    print("\n[OK] Generated Post Structure:")
    print(f"Category: {post['category']}")
    print(f"Title: {post['title']}")
    print("Content:\n" + post['content'])

    # Verification of required fields
    assert "category" in post and post["category"]
    assert "title" in post and "🔥" in post["title"]
    assert "📰 Source:" in post["content"]
    assert "🔗 Read More:" in post["content"]

    print("\nPhase 3B AI Processor test PASSED successfully!")

if __name__ == "__main__":
    main()
