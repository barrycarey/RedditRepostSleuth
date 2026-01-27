"""Tests for UserDataFetcher."""
import time
import unittest
from datetime import datetime
from unittest.mock import MagicMock, PropertyMock, patch

from prawcore.exceptions import Forbidden, NotFound, TooManyRequests

from redditrepostsleuth.core.services.spam.circuit_breaker import CircuitBreaker
from redditrepostsleuth.core.services.spam.rate_limiter import RateLimitExceeded
from redditrepostsleuth.core.services.spam.tier2_features import Tier2Features
from redditrepostsleuth.core.services.spam.user_data_fetcher import (
    CachedUserDataFetcher,
    UserDataFetcher,
    detect_adult_platform_link,
    detect_telegram_link,
)


class TestDetectTelegramLink(unittest.TestCase):
    """Test cases for detect_telegram_link function."""

    def test_detects_tme_links(self):
        """Test detection of t.me links."""
        self.assertTrue(detect_telegram_link("Join us at t.me/mygroup"))
        self.assertTrue(detect_telegram_link("https://t.me/username"))
        self.assertTrue(detect_telegram_link("Check T.ME/channel"))  # Case insensitive

    def test_detects_telegram_me_links(self):
        """Test detection of telegram.me links."""
        self.assertTrue(detect_telegram_link("telegram.me/mygroup"))
        self.assertTrue(detect_telegram_link("https://telegram.me/user"))

    def test_detects_telegram_org_links(self):
        """Test detection of telegram.org links."""
        self.assertTrue(detect_telegram_link("telegram.org/channel"))

    def test_does_not_detect_unrelated_text(self):
        """Test that unrelated text is not detected."""
        self.assertFalse(detect_telegram_link("Check my profile"))
        self.assertFalse(detect_telegram_link("telegram is great"))  # No slash
        self.assertFalse(detect_telegram_link(None))
        self.assertFalse(detect_telegram_link(""))

    def test_does_not_match_partial_patterns(self):
        """Test that partial patterns don't match."""
        self.assertFalse(detect_telegram_link("something.me/channel"))
        self.assertFalse(detect_telegram_link("mysite.telegram.me"))


class TestDetectAdultPlatformLink(unittest.TestCase):
    """Test cases for detect_adult_platform_link function."""

    def test_detects_onlyfans(self):
        """Test detection of OnlyFans links."""
        self.assertTrue(detect_adult_platform_link("onlyfans.com/username"))
        self.assertTrue(detect_adult_platform_link("https://onlyfans.com/user"))

    def test_detects_fansly(self):
        """Test detection of Fansly links."""
        self.assertTrue(detect_adult_platform_link("fansly.com/creator"))

    def test_detects_chaturbate(self):
        """Test detection of Chaturbate links."""
        self.assertTrue(detect_adult_platform_link("chaturbate.com/room"))

    def test_does_not_detect_unrelated_text(self):
        """Test that unrelated text is not detected."""
        self.assertFalse(detect_adult_platform_link("Check my instagram"))
        self.assertFalse(detect_adult_platform_link(None))
        self.assertFalse(detect_adult_platform_link(""))


class TestUserDataFetcher(unittest.TestCase):
    """Test cases for UserDataFetcher class."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_reddit = MagicMock()
        self.mock_uowm = MagicMock()
        self.fetcher = UserDataFetcher(
            self.mock_reddit,
            self.mock_uowm,
            min_interval=0.01  # Fast for tests
        )

    def test_fetch_basic_user_data_success(self):
        """Test successful user data fetch."""
        mock_redditor = MagicMock()
        mock_redditor.created_utc = datetime(2023, 1, 1).timestamp()
        mock_redditor.total_karma = 5000
        mock_redditor.link_karma = 3000
        mock_redditor.comment_karma = 2000
        mock_redditor.has_verified_email = True
        mock_redditor.is_gold = False
        mock_redditor.icon_img = 'https://custom-avatar.jpg'

        self.mock_reddit.redditor.return_value = mock_redditor

        result = self.fetcher.fetch_basic_user_data('testuser')

        self.assertIsInstance(result, Tier2Features)
        self.assertEqual(result.total_karma, 5000)
        self.assertEqual(result.post_karma, 3000)
        self.assertEqual(result.comment_karma, 2000)
        self.assertTrue(result.has_verified_email)
        self.assertFalse(result.account_suspended)
        self.assertTrue(result.fetch_success)

    def test_fetch_user_not_found(self):
        """Test handling of deleted/shadowbanned user."""
        mock_redditor = MagicMock()
        type(mock_redditor).created_utc = PropertyMock(
            side_effect=NotFound(MagicMock())
        )
        self.mock_reddit.redditor.return_value = mock_redditor

        result = self.fetcher.fetch_basic_user_data('deleteduser')

        self.assertIsNotNone(result)
        self.assertTrue(result.account_suspended)
        self.assertTrue(result.fetch_success)

    def test_fetch_user_forbidden(self):
        """Test handling of suspended user (403 Forbidden)."""
        mock_redditor = MagicMock()
        type(mock_redditor).created_utc = PropertyMock(
            side_effect=Forbidden(MagicMock())
        )
        self.mock_reddit.redditor.return_value = mock_redditor

        result = self.fetcher.fetch_basic_user_data('suspendeduser')

        self.assertIsNotNone(result)
        self.assertTrue(result.account_suspended)

    def test_fetch_rate_limited_raises_exception(self):
        """Test that rate limit triggers RateLimitExceeded."""
        mock_exception = TooManyRequests(MagicMock())
        mock_exception.retry_after = 120

        mock_redditor = MagicMock()
        type(mock_redditor).created_utc = PropertyMock(
            side_effect=mock_exception
        )
        self.mock_reddit.redditor.return_value = mock_redditor

        with self.assertRaises(RateLimitExceeded) as context:
            self.fetcher.fetch_basic_user_data('anyuser')

        self.assertEqual(context.exception.retry_after, 120)

    def test_default_avatar_detection(self):
        """Test detection of default avatars."""
        default_urls = [
            'https://styles.redditmedia.com/t5_snoomoji_img.png',
            'https://reddit.com/avatar_default_01.png',
            'https://www.redditstatic.com/snoovatar_default.png',
        ]

        for url in default_urls:
            self.assertTrue(
                self.fetcher._is_default_avatar(url),
                f"Should detect {url} as default"
            )

        custom_urls = [
            'https://i.redd.it/custom_avatar_abc123.png',
            'https://preview.redd.it/user_profile_pic.jpg',
        ]

        for url in custom_urls:
            self.assertFalse(
                self.fetcher._is_default_avatar(url),
                f"Should NOT detect {url} as default"
            )

    def test_is_default_avatar_with_empty_url(self):
        """Test default avatar detection with empty/None URL."""
        self.assertTrue(self.fetcher._is_default_avatar(''))
        self.assertTrue(self.fetcher._is_default_avatar(None))

    def test_rate_limiting_enforced(self):
        """Test that rate limiting delays requests."""
        mock_redditor = MagicMock()
        mock_redditor.created_utc = datetime.now().timestamp()
        mock_redditor.total_karma = 100
        mock_redditor.link_karma = 50
        mock_redditor.comment_karma = 50
        mock_redditor.has_verified_email = True
        mock_redditor.is_gold = False
        mock_redditor.icon_img = ''

        self.mock_reddit.redditor.return_value = mock_redditor

        # Set min_interval to measurable amount
        self.fetcher.min_interval = 0.2

        start = time.time()

        # Two rapid requests
        self.fetcher.fetch_basic_user_data('user1')
        self.fetcher.fetch_basic_user_data('user2')

        elapsed = time.time() - start

        # Should have waited at least min_interval
        self.assertGreaterEqual(elapsed, 0.2)

    def test_check_user_suspended_true(self):
        """Test check_user_suspended returns True for suspended user."""
        mock_redditor = MagicMock()
        type(mock_redditor).created_utc = PropertyMock(
            side_effect=NotFound(MagicMock())
        )
        self.mock_reddit.redditor.return_value = mock_redditor

        result = self.fetcher.check_user_suspended('suspendeduser')

        self.assertTrue(result)

    def test_check_user_suspended_false(self):
        """Test check_user_suspended returns False for active user."""
        mock_redditor = MagicMock()
        mock_redditor.created_utc = datetime.now().timestamp()
        self.mock_reddit.redditor.return_value = mock_redditor

        result = self.fetcher.check_user_suspended('activeuser')

        self.assertFalse(result)


class TestUserDataFetcherWithCircuitBreaker(unittest.TestCase):
    """Test UserDataFetcher with circuit breaker integration."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_reddit = MagicMock()
        self.mock_uowm = MagicMock()
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=3,
            recovery_timeout=1
        )
        self.fetcher = UserDataFetcher(
            self.mock_reddit,
            self.mock_uowm,
            circuit_breaker=self.circuit_breaker,
            min_interval=0.01
        )

    def test_circuit_breaker_tracks_successes(self):
        """Test that successful calls are tracked by circuit breaker."""
        mock_redditor = MagicMock()
        mock_redditor.created_utc = datetime.now().timestamp()
        mock_redditor.total_karma = 100
        mock_redditor.link_karma = 50
        mock_redditor.comment_karma = 50
        mock_redditor.has_verified_email = True
        mock_redditor.is_gold = False
        mock_redditor.icon_img = ''

        self.mock_reddit.redditor.return_value = mock_redditor

        self.fetcher.fetch_basic_user_data('user')

        # Circuit should still be closed
        self.assertTrue(self.circuit_breaker.is_closed)
        self.assertEqual(self.circuit_breaker._failure_count, 0)

    def test_circuit_breaker_tracks_failures(self):
        """Test that API failures are tracked by circuit breaker."""
        mock_exception = TooManyRequests(MagicMock())
        mock_exception.retry_after = 60

        mock_redditor = MagicMock()
        type(mock_redditor).created_utc = PropertyMock(
            side_effect=mock_exception
        )
        self.mock_reddit.redditor.return_value = mock_redditor

        with self.assertRaises(RateLimitExceeded):
            self.fetcher.fetch_basic_user_data('user')

        # Failure should be recorded
        self.assertEqual(self.circuit_breaker._failure_count, 1)


class TestCachedUserDataFetcher(unittest.TestCase):
    """Test cases for CachedUserDataFetcher class."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_reddit = MagicMock()
        self.mock_uowm = MagicMock()
        self.fetcher = CachedUserDataFetcher(
            self.mock_reddit,
            self.mock_uowm,
            cache_ttl_hours=24,
            min_interval=0.01
        )

    def test_returns_cached_data_when_fresh(self):
        """Test that fresh cached data is returned without API call."""
        # Set up mock cached data
        mock_uow = MagicMock()
        mock_cached = MagicMock()
        mock_cached.account_age_days = 100
        mock_cached.total_karma = 5000
        mock_cached.post_karma = 3000
        mock_cached.comment_karma = 2000
        mock_cached.karma_per_day = 50.0
        mock_cached.has_verified_email = True
        mock_cached.is_gold = False
        mock_cached.has_custom_avatar = True
        mock_cached.account_suspended = False
        mock_cached.has_adult_profile_links = False
        mock_cached.has_telegram_links = False
        mock_cached.profile_link_sources = {}
        mock_cached.tier2_enriched_at = datetime.utcnow()

        mock_uow.spam_features.get_by_username.return_value = mock_cached
        self.mock_uowm.start.return_value.__enter__.return_value = mock_uow

        result = self.fetcher.fetch_basic_user_data('cacheduser')

        # Should return cached data without calling Reddit API
        self.mock_reddit.redditor.assert_not_called()
        self.assertIsNotNone(result)
        self.assertEqual(result.account_age_days, 100)
        self.assertEqual(result.total_karma, 5000)


if __name__ == '__main__':
    unittest.main()
