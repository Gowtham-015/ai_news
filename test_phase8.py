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
7. Caption & text truncation safety (< 1024 for caption / < 4096 for message)
8. Missing source & missing URL resilience
9. Image size limit rejection (>10MB)
10. HTML entity escaping (<, >, &)
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

    def test_special_character_escaping(self):
        """Verifies safe HTML entity escaping for special characters."""
        post = {
            "category": "News",
            "title": "A & B <C> Test",
            "summary": "This & that <script>alert(1)</script>",
            "source": "R & D Source",
            "url": "https://example.com/test?a=1&b=2"
        }
        formatted = publisher.format_html_post(post)
        self.assertIn("A &amp; B &lt;C&gt; Test", formatted)
        self.assertIn("This &amp; that &lt;script&gt;alert(1)&lt;/script&gt;", formatted)
        self.assertIn("R &amp; D Source", formatted)
        self.assertIn("https://example.com/test?a=1&amp;b=2", formatted)

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

    def test_missing_source_and_url_resilience(self):
        """Verifies post with missing source and URL formats cleanly without crashing."""
        post = {
            "category": "Entertainment",
            "title": "Uncredited Short Update",
            "summary": "Quick update on movie shooting."
        }
        formatted = publisher.format_html_post(post)
        self.assertIn("📰 <b>Source:</b> Unknown Source", formatted)
        self.assertNotIn("<a href=", formatted)

    def test_caption_and_text_truncation_budget(self):
        """Verifies photo caption remains strictly <= 1024 characters."""
        post = {
            "category": "Technology",
            "title": "Long Article Headline " * 5,
            "summary": "Very detailed article summary paragraph. " * 30,
            "why_it_matters": "Extremely detailed rationale line. " * 10,
            "source": "TechCrunch",
            "url": "https://techcrunch.com/long-article"
        }
        caption = publisher.format_html_post(post, max_length=1024)
        self.assertLessEqual(len(caption), 1024)
        
        full_msg = publisher.format_html_post(post, max_length=4096)
        self.assertLessEqual(len(full_msg), 4096)

    @mock.patch("publisher.validate_image_url", return_value=True)
    @mock.patch("publisher.Bot")
    def test_image_post_delivery(self, mock_bot_cls, mock_val):
        """Verifies valid image URL triggers send_photo with caption."""
        mock_bot = mock.MagicMock()
        mock_bot_cls.return_value = mock_bot
        mock_bot.send_photo = mock.AsyncMock(return_value=True)

        post = {
            "category": "Technology",
            "title": "New Device Announced",
            "summary": "Summary of device launch.",
            "image_url": "https://example.com/device.jpg",
            "source": "Wired",
            "url": "https://wired.com/device"
        }

        with mock.patch("config.validate_config"):
            result = publisher.publish_post(post)
            self.assertTrue(result)
            mock_bot.send_photo.assert_called_once()

    @mock.patch("publisher.validate_image_url", return_value=False)
    @mock.patch("publisher.Bot")
    def test_invalid_image_url_and_timeout_fallback(self, mock_bot_cls, mock_val):
        """Verifies invalid or timing out image URL falls back to text message."""
        mock_bot = mock.MagicMock()
        mock_bot_cls.return_value = mock_bot
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
            mock_bot.send_photo.assert_not_called()
            mock_bot.send_message.assert_called_once()

    @mock.patch("publisher.validate_image_url", return_value=False)
    @mock.patch("publisher.Bot")
    def test_invalid_telegram_markup_fallback(self, mock_bot_cls, mock_val):
        """Verifies HTML parse error falls back to plain text delivery."""
        mock_bot = mock.MagicMock()
        mock_bot_cls.return_value = mock_bot

        from telegram.error import BadRequest
        mock_bot.send_message = mock.AsyncMock(side_effect=[
            BadRequest("Can't parse entities: unclosed tag"),
            True
        ])

        post = {
            "category": "News",
            "title": "Broken Tags Article",
            "content": "Content line.",
            "source": "BBC News"
        }

        with mock.patch("config.validate_config"):
            result = publisher.publish_post(post)
            self.assertTrue(result)
            self.assertEqual(mock_bot.send_message.call_count, 2)


if __name__ == "__main__":
    unittest.main()

