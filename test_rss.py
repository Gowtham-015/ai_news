"""
test_rss.py
-----------
Test script for Phase 3A RSS News Collection.
"""

import sys
import logging
from news_collector import collect_news, save_collected_news

logging.basicConfig(level=logging.INFO)

def main():
    print("==================================================")
    print(" TESTING PHASE 3A - RSS NEWS COLLECTION")
    print("==================================================")

    articles = collect_news()
    
    print(f"\n[OK] Total collected articles: {len(articles)}")
    
    categories = {}
    for art in articles:
        cat = art["category"]
        categories[cat] = categories.get(cat, 0) + 1
        
    for cat, count in categories.items():
        print(f"[OK] {cat}: {count} articles")

    if articles:
        print("\n--- SAMPLE ARTICLE ---")
        sample = articles[0]
        print(f"Title: {sample['title']}")
        print(f"Category: {sample['category']}")
        print(f"Source: {sample['source']}")
        print(f"URL: {sample['url']}")
        print(f"Published At: {sample['published_at']}")

    save_collected_news(articles)
    print("\nPhase 3A RSS test complete.")

if __name__ == "__main__":
    main()
