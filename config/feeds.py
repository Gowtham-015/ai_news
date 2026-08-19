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
            "name": "BBC News",
            "url": "http://feeds.bbci.co.uk/news/rss.xml"
        },
        {
            "name": "NDTV News",
            "url": "https://feeds.feedburner.com/ndtvnews-top-stories"
        },
        {
            "name": "Times of India",
            "url": "https://timesofindia.indiatimes.com/rssfeedstopstories.cms"
        }
    ],
    "Technology": [
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
            "name": "BBC Sport",
            "url": "http://feeds.bbci.co.uk/sport/rss.xml"
        },
        {
            "name": "ESPN",
            "url": "https://www.espn.com/espn/rss/news"
        },
        {
            "name": "ESPN Cricinfo",
            "url": "https://www.espncricinfo.com/rss/content/story/feeds/0.xml"
        }
    ],
    "Entertainment": [
        {
            "name": "Variety",
            "url": "https://variety.com/feed/"
        },
        {
            "name": "Hollywood Reporter",
            "url": "https://www.hollywoodreporter.com/feed/"
        },
        {
            "name": "E! Online",
            "url": "https://www.eonline.com/syndication/feeds/rss2/topstories.xml"
        }
    ]
}
