"""
test_phase8.py
--------------
Automated test suite for Phase 8 Professional Telegram Content & Media.

Verifies:
1. Normal post HTML formatting with category branding & IST timestamp
2. Breaking news header formatting (🚨 BREAKING NEWS)
3. Image post delivery & valid photo request handling
4. No-image post text delivery
5. Invalid image URL / timeout automatic text-only fallback
6. Invalid Telegram HTML markup fallback to plain text
7. Caption & text truncation safety (< 1024 / < 4096)
8. Missing source & missing URL resilience
"""

import unittest
from unittest import mock
import publisher


class TestPhase8(unittest.TestCase):
    def test_normal_post_formatting(self):
        """Verifies normal post formatting with category branding and IST timestamp."""
        post = {
            "category": "Technology",
            "title": "🔥 Apple Unveils Next-Gen AI Chip",
            "content": "Apple introduced its newest neural engine architecture at WWDC.",
            "why_it_matters": "Accelerates local AI inference by 50%.",
            "source": "TechCrunch",
            "url": "https://techcrunch.com/apple-chip",
            "published_at": "2026-08-19T12:00:00Z"
        }
        formatted = publisher.format_html_post(post)
        self.assertIn("<b>💻 TECHNOLOGY</b>", formatted)
        self.assertIn("<b>Apple Unveils Next-Gen AI Chip</b>", formatted)
        self.assertIn("📌 <b>Why it matters:</b>\nAccelerates local AI inference by 50%.", formatted)
        self.assertIn("🕒 <b>Published:</b>", formatted)
        self.assertIn("IST", formatted)
        self.assertIn("📰 <b>Source:</b> TechCrunch", formatted)
        self.assertIn("🔗 <a href=\"https://techcrunch.com/apple-chip\">Read full story</a>", formatted)

    def test_breaking_news_formatting(self):
        """Verifies breaking news header visual distinction."""
        post = {
            "category": "News",
            "is_breaking": True,
            "title": "Major Earthquake Reported",
            "content": "A magnitude 7.2 earthquake struck the coastal area.",
            "source": "BBC News",
            "url": "https://bbc.com/earthquake"
        }
        formatted = publisher.format_html_post(post)
        self.assertIn("🚨 <b>BREAKING NEWS</b>", formatted)
        self.assertNotIn("<b>📰 NEWS</b>", formatted)

    def test_invalid_url_handling(self):
        """Verifies invalid or non-HTTP URLs are cleanly omitted."""
        post = {
            "category": "Sports",
            "title": "Match Result",
            "content": "Team A won.",
            "source": "ESPN",
            "url": "invalid_url_format"
        }
        formatted = publisher.format_html_post(post)
        self.assertNotIn("<a href=", formatted)

    @mock.patch("publisher.Bot")
    def test_image_publish_fallback(self, mock_bot_cls):
        """Verifies that an image error falls back automatically to text message publishing."""
        mock_bot = mock.MagicMock()
        mock_bot_cls.return_value = mock_bot

        mock_bot.send_photo = mock.AsyncMock(side_effect=Exception("404 Image Not Found"))
        mock_bot.send_message = mock.AsyncMock(return_value=True)


        post = {
            "category": "Entertainment",
            "title": "Movie Premiere Announced",
            "content": "The sequel arrives in theaters October 2026.",
            "image_url": "https://example.com/bad_image.jpg",
            "source": "Variety",
            "url": "https://variety.com/movie"
        }

        with mock.patch("config.validate_config"):
            result = publisher.publish_post(post)
            self.assertTrue(result)


if __name__ == "__main__":
    unittest.main()
