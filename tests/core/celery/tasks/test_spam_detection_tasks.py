from unittest import TestCase

from redditrepostsleuth.core.celery.tasks.spam_detection_tasks import (
    detect_adult_platform_link,
    detect_short_link,
    ADULT_PLATFORM_PATTERNS,
    SHORT_LINK_PATTERNS
)


class TestDetectAdultPlatformLink(TestCase):
    """Tests for adult platform link detection."""

    def test_detect_onlyfans_link(self):
        self.assertTrue(detect_adult_platform_link('https://onlyfans.com/username'))

    def test_detect_fansly_link(self):
        self.assertTrue(detect_adult_platform_link('https://fansly.com/username'))

    def test_detect_fancentro_link(self):
        self.assertTrue(detect_adult_platform_link('https://fancentro.com/username'))

    def test_detect_manyvids_link(self):
        self.assertTrue(detect_adult_platform_link('https://manyvids.com/Profile/12345'))

    def test_detect_chaturbate_link(self):
        self.assertTrue(detect_adult_platform_link('https://chaturbate.com/username'))

    def test_detect_pornhub_model_link(self):
        self.assertTrue(detect_adult_platform_link('https://pornhub.com/model/username'))

    def test_detect_pornhub_users_link(self):
        self.assertTrue(detect_adult_platform_link('https://pornhub.com/users/username'))

    def test_detect_linktr_ee_with_onlyfans_in_bio(self):
        # linktr.ee itself is a short link, not an adult platform
        # The URL text doesn't contain adult platform - we're checking the domain
        self.assertFalse(detect_adult_platform_link('https://linktr.ee/someone'))

    def test_detect_case_insensitive(self):
        self.assertTrue(detect_adult_platform_link('https://ONLYFANS.COM/username'))
        self.assertTrue(detect_adult_platform_link('https://Fansly.Com/username'))

    def test_detect_embedded_in_text(self):
        self.assertTrue(detect_adult_platform_link('Check out my onlyfans.com/user page!'))

    def test_regular_url_returns_false(self):
        self.assertFalse(detect_adult_platform_link('https://reddit.com/r/test'))

    def test_none_url_returns_false(self):
        self.assertFalse(detect_adult_platform_link(None))

    def test_empty_url_returns_false(self):
        self.assertFalse(detect_adult_platform_link(''))

    def test_imgur_url_returns_false(self):
        self.assertFalse(detect_adult_platform_link('https://i.imgur.com/abc123.jpg'))

    def test_youtube_url_returns_false(self):
        self.assertFalse(detect_adult_platform_link('https://youtube.com/watch?v=abc123'))


class TestDetectShortLink(TestCase):
    """Tests for URL shortener/link aggregator detection."""

    def test_detect_bitly(self):
        self.assertTrue(detect_short_link('https://bit.ly/abc123'))

    def test_detect_tinyurl(self):
        self.assertTrue(detect_short_link('https://tinyurl.com/abc123'))

    def test_detect_linktree(self):
        self.assertTrue(detect_short_link('https://linktr.ee/username'))

    def test_detect_beacons(self):
        self.assertTrue(detect_short_link('https://beacons.ai/username'))

    def test_detect_allmylinks(self):
        self.assertTrue(detect_short_link('https://allmylinks.com/username'))

    def test_detect_case_insensitive(self):
        self.assertTrue(detect_short_link('https://BIT.LY/abc123'))
        self.assertTrue(detect_short_link('https://LinkTr.ee/username'))

    def test_detect_goo_gl(self):
        self.assertTrue(detect_short_link('https://goo.gl/abc123'))

    def test_detect_twitter_short_link(self):
        self.assertTrue(detect_short_link('https://t.co/abc123'))

    def test_regular_url_returns_false(self):
        self.assertFalse(detect_short_link('https://reddit.com/r/test'))

    def test_none_url_returns_false(self):
        self.assertFalse(detect_short_link(None))

    def test_empty_url_returns_false(self):
        self.assertFalse(detect_short_link(''))

    def test_imgur_url_returns_false(self):
        self.assertFalse(detect_short_link('https://i.imgur.com/abc123.jpg'))

    def test_full_reddit_url_returns_false(self):
        self.assertFalse(detect_short_link('https://www.reddit.com/r/memes/comments/abc123/test'))


class TestPatternLists(TestCase):
    """Tests for pattern list completeness."""

    def test_adult_patterns_not_empty(self):
        self.assertGreater(len(ADULT_PLATFORM_PATTERNS), 0)

    def test_short_link_patterns_not_empty(self):
        self.assertGreater(len(SHORT_LINK_PATTERNS), 0)

    def test_adult_patterns_count(self):
        # Verify we have all 18 patterns as specified
        self.assertEqual(18, len(ADULT_PLATFORM_PATTERNS))

    def test_short_link_patterns_count(self):
        # Verify we have all 21 patterns as specified
        self.assertEqual(21, len(SHORT_LINK_PATTERNS))
