"""
config/feeds.py
---------------
Configuration file for RSS News Feeds.
Defines reliable RSS feed URLs categorized into:
- News
- Technology
- Sports
- Entertainment
"""

FEEDS = {
    "News": [
        {
            "name": "NDTV News",
            "url": "https://feeds.feedburner.com/ndtvnews-top-stories"
        },
        {
            "name": "Times of India",
            "url": "https://timesofindia.indiatimes.com/rssfeedstopstories.cms"
        },
        {
            "name": "The Hindu",
            "url": "https://www.thehindu.com/news/national/feeder/default.rss"
        },
        {
            "name": "BBC News",
            "url": "http://feeds.bbci.co.uk/news/rss.xml"
        }
    ],
    "Technology": [
        {
            "name": "Economic Times Tech",
            "url": "https://economictimes.indiatimes.com/tech/rssfeeds/13357270.cms"
        },
        {
            "name": "TechCrunch",
            "url": "https://techcrunch.com/feed/"
        },
        {
            "name": "Wired",
            "url": "https://www.wired.com/feed/rss"
        },
        {
            "name": "The Verge",
            "url": "https://www.theverge.com/rss/index.xml"
        }
    ],
    "Sports": [
        {
            "name": "TOI Sports",
            "url": "https://timesofindia.indiatimes.com/rssfeeds/4719148.cms"
        },
        {
            "name": "NDTV Sports",
            "url": "https://feeds.feedburner.com/ndtvsports-latest"
        },
        {
            "name": "ESPN Cricinfo",
            "url": "https://www.espncricinfo.com/rss/content/story/feeds/0.xml"
        },
        {
            "name": "BBC Sport",
            "url": "http://feeds.bbci.co.uk/sport/rss.xml"
        }
    ],
    "Entertainment": [
        {
            "name": "Times of India Entertainment",
            "url": "https://timesofindia.indiatimes.com/rssfeeds/1081479906.cms"
        },
        {
            "name": "Variety",
            "url": "https://variety.com/feed/"
        },
        {
            "name": "Hollywood Reporter",
            "url": "https://www.hollywoodreporter.com/feed/"
        }
    ]
}

