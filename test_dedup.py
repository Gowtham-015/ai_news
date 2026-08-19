"""
test_dedup.py
--------------
Test script for Phase 3A Duplicate News Filter.
Verifies URL, ID, and title normalization duplicate detection.
"""

import logging
from deduplicator import filter_duplicates, normalize_url, normalize_title

logging.basicConfig(level=logging.INFO)

def main():
    print("==================================================")
    print(" TESTING PHASE 3A - DUPLICATE NEWS FILTER")
    print("==================================================")

    sample_articles = [
        {
            "id": "art-001",
            "title": "NASA Launches New Space Telescope",
            "url": "https://news.example.com/nasa-telescope?utm_medium=rss&ref=home",
            "category": "Technology",
            "source": "Tech Source A"
        },
        {
            "id": "art-001", # Duplicate ID
            "title": "NASA Launches New Space Telescope",
            "url": "https://news.example.com/nasa-telescope-alt",
            "category": "Technology",
            "source": "Tech Source B"
        },
        {
            "id": "art-002",
            "title": "NASA Launches New Space Telescope!", # Duplicate Title
            "url": "https://different.example.com/nasa",
            "category": "Technology",
            "source": "Tech Source C"
        },
        {
            "id": "art-003",
            "title": "Scientists Discover New Species in Amazon",
            "url": "https://news.example.com/nasa-telescope?utm_medium=rss", # Duplicate URL after normalization
            "category": "News",
            "source": "Science Source"
        },
        {
            "id": "art-004",
            "title": "Scientists Discover New Species in Amazon",
            "url": "https://nature.example.com/new-species",
            "category": "News",
            "source": "Nature Daily"
        }
    ]

    print(f"Input articles: {len(sample_articles)}")
    unique = filter_duplicates(sample_articles)
    print(f"\n[OK] Remaining unique articles: {len(unique)}")
    
    assert len(unique) == 2, f"Expected 2 unique articles, got {len(unique)}"
    
    print("\nUnique articles retained:")
    for a in unique:
        print(f" - [{a['id']}] {a['title']} ({a['source']})")

    print("\nPhase 3A Deduplication test PASSED successfully!")

if __name__ == "__main__":
    main()
