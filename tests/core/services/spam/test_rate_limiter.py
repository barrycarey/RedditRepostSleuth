"""Tests for PerMinuteRateLimiter."""
import time
import unittest
from unittest.mock import MagicMock, patch

from redditrepostsleuth.core.services.spam.rate_limiter import (
    InMemoryRateLimiter,
    PerMinuteRateLimiter,
    RateLimitExceeded,
)


class TestPerMinuteRateLimiter(unittest.TestCase):
    """Test cases for PerMinuteRateLimiter class."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_redis = MagicMock()
        self.limiter = PerMinuteRateLimiter(
            self.mock_redis,
            requests_per_minute=5,  # Low limit for testing
            key_prefix="test:rate_limit"
        )

    def test_is_allowed_under_limit(self):
        """Test is_allowed returns True when under limit."""
        # Mock Redis pipeline to return count under limit
        mock_pipe = MagicMock()
        mock_pipe.execute.return_value = [3, True]  # 3 requests < 5 limit
        self.mock_redis.pipeline.return_value = mock_pipe

        self.assertTrue(self.limiter.is_allowed())

    def test_is_allowed_at_limit(self):
        """Test is_allowed returns True when exactly at limit."""
        mock_pipe = MagicMock()
        mock_pipe.execute.return_value = [5, True]  # Exactly at limit
        self.mock_redis.pipeline.return_value = mock_pipe

        self.assertTrue(self.limiter.is_allowed())

    def test_is_allowed_over_limit(self):
        """Test is_allowed returns False when over limit."""
        mock_pipe = MagicMock()
        mock_pipe.execute.return_value = [6, True]  # Over limit
        self.mock_redis.pipeline.return_value = mock_pipe

        self.assertFalse(self.limiter.is_allowed())

    def test_is_allowed_fails_open_on_redis_error(self):
        """Test is_allowed returns True (fails open) on Redis error."""
        self.mock_redis.pipeline.side_effect = Exception("Redis error")

        # Should fail open (allow request)
        self.assertTrue(self.limiter.is_allowed())

    def test_get_current_usage(self):
        """Test get_current_usage returns correct stats."""
        self.mock_redis.get.return_value = b'3'

        usage = self.limiter.get_current_usage()

        self.assertEqual(usage['requests_made'], 3)
        self.assertEqual(usage['requests_remaining'], 2)
        self.assertEqual(usage['max_requests'], 5)

    def test_get_current_usage_handles_missing_key(self):
        """Test get_current_usage handles missing Redis key."""
        self.mock_redis.get.return_value = None

        usage = self.limiter.get_current_usage()

        self.assertEqual(usage['requests_made'], 0)
        self.assertEqual(usage['requests_remaining'], 5)

    def test_get_current_usage_handles_redis_error(self):
        """Test get_current_usage handles Redis error gracefully."""
        self.mock_redis.get.side_effect = Exception("Redis error")

        usage = self.limiter.get_current_usage()

        self.assertIn('error', usage)
        self.assertEqual(usage['requests_made'], 0)

    def test_reset_deletes_current_key(self):
        """Test reset deletes the current minute's key."""
        self.limiter.reset()

        self.mock_redis.delete.assert_called_once()


class TestInMemoryRateLimiter(unittest.TestCase):
    """Test cases for InMemoryRateLimiter class."""

    def test_is_allowed_under_limit(self):
        """Test is_allowed returns True when under limit."""
        limiter = InMemoryRateLimiter(requests_per_minute=5)

        for _ in range(5):
            self.assertTrue(limiter.is_allowed())

    def test_is_allowed_blocks_at_limit(self):
        """Test is_allowed returns False when at limit."""
        limiter = InMemoryRateLimiter(requests_per_minute=3)

        # Use up the limit
        for _ in range(3):
            self.assertTrue(limiter.is_allowed())

        # Next should be blocked
        self.assertFalse(limiter.is_allowed())

    def test_get_current_usage(self):
        """Test get_current_usage returns correct stats."""
        limiter = InMemoryRateLimiter(requests_per_minute=5)

        # Make 3 requests
        for _ in range(3):
            limiter.is_allowed()

        usage = limiter.get_current_usage()

        self.assertEqual(usage['requests_made'], 3)
        self.assertEqual(usage['requests_remaining'], 2)
        self.assertEqual(usage['max_requests'], 5)

    def test_reset_clears_timestamps(self):
        """Test reset clears all timestamps."""
        limiter = InMemoryRateLimiter(requests_per_minute=5)

        # Make some requests
        for _ in range(3):
            limiter.is_allowed()

        limiter.reset()

        usage = limiter.get_current_usage()
        self.assertEqual(usage['requests_made'], 0)


class TestRateLimitExceeded(unittest.TestCase):
    """Test cases for RateLimitExceeded exception."""

    def test_exception_message(self):
        """Test exception includes retry time."""
        exc = RateLimitExceeded(retry_after=120)
        self.assertEqual(exc.retry_after, 120)
        self.assertIn('120', str(exc))

    def test_custom_message(self):
        """Test custom message is used."""
        exc = RateLimitExceeded(retry_after=60, message="Custom error")
        self.assertIn("Custom error", str(exc))

    def test_default_retry_after(self):
        """Test default retry_after value."""
        exc = RateLimitExceeded()
        self.assertEqual(exc.retry_after, 60)


if __name__ == '__main__':
    unittest.main()
