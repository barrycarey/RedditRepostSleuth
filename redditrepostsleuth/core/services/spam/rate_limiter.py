"""Per-minute rate limiting for Reddit API calls.

Uses Redis sliding window to enforce rate limits and prevent 429 errors.
"""
import logging
import time
from datetime import datetime, timedelta
from typing import Optional

log = logging.getLogger(__name__)


class RateLimitExceeded(Exception):
    """Raised when rate limit is exceeded and retry is needed."""

    def __init__(self, retry_after: int = 60, message: str = None):
        self.retry_after = retry_after
        super().__init__(message or f"Rate limit exceeded, retry after {retry_after}s")


class PerMinuteRateLimiter:
    """
    Enforces per-minute rate limiting using Redis sliding window.

    Prevents hitting Reddit's 60 requests/minute limit by enforcing a
    conservative 50 requests/minute default.
    """

    def __init__(
        self,
        redis_client,
        requests_per_minute: int = 50,
        key_prefix: str = "spam_detection:api_rate_limit"
    ):
        """
        Initialize the rate limiter.

        Args:
            redis_client: Redis client instance
            requests_per_minute: Maximum requests per minute (default 50)
            key_prefix: Redis key prefix for rate limit counters
        """
        self.redis = redis_client
        self.max_requests = requests_per_minute
        self.key_prefix = key_prefix

    def is_allowed(self) -> bool:
        """
        Check if API call is allowed within rate limits.

        Returns:
            True if request is allowed, False if rate limit exceeded
        """
        try:
            current = datetime.utcnow()
            window_key = f"{self.key_prefix}:{current.minute}"

            # Use pipeline for atomic increment and expire
            pipe = self.redis.pipeline()
            pipe.incr(window_key)
            pipe.expire(window_key, 70)  # Expire slightly after minute ends
            results = pipe.execute()

            count = results[0]

            if count <= self.max_requests:
                log.debug(f"Rate limit: {count}/{self.max_requests} requests this minute")
                return True
            else:
                log.warning(f"Rate limit exceeded: {count}/{self.max_requests}")
                return False

        except Exception as e:
            log.warning(f"Rate limiter error (failing open): {e}")
            # Fail open - allow request if Redis fails
            return True

    def wait_if_needed(self, timeout: float = 65.0) -> bool:
        """
        Wait if necessary to stay within rate limits.

        Args:
            timeout: Maximum time to wait in seconds

        Returns:
            True if wait was needed, False otherwise

        Raises:
            RateLimitExceeded: If timeout exceeded while waiting
        """
        if self.is_allowed():
            return False

        wait_time = self._calculate_wait_time()
        if wait_time > timeout:
            raise RateLimitExceeded(
                retry_after=int(wait_time),
                message=f"Rate limit exceeded, wait time {wait_time}s exceeds timeout {timeout}s"
            )

        log.info(f"Rate limit hit, waiting {wait_time:.1f}s")
        time.sleep(wait_time)
        return True

    def acquire(self) -> bool:
        """
        Acquire a rate limit slot, waiting if necessary.

        This is a blocking call that will wait until a slot is available.

        Returns:
            True when slot is acquired
        """
        while not self.is_allowed():
            wait_time = self._calculate_wait_time()
            log.info(f"Rate limit hit, waiting {wait_time:.1f}s")
            time.sleep(wait_time)
        return True

    def _calculate_wait_time(self) -> float:
        """
        Calculate time to wait until next minute window.

        Returns:
            Seconds to wait (max 60)
        """
        current = datetime.utcnow()
        next_minute = (current + timedelta(minutes=1)).replace(second=0, microsecond=0)
        backoff = (next_minute - current).total_seconds()
        # Add 1 second buffer to ensure we're in the new minute
        return min(backoff + 1, 60)

    def get_current_usage(self) -> dict:
        """
        Get current rate limit usage statistics.

        Returns:
            Dict with usage information
        """
        try:
            current = datetime.utcnow()
            window_key = f"{self.key_prefix}:{current.minute}"
            count = int(self.redis.get(window_key) or 0)
            return {
                'requests_made': count,
                'requests_remaining': max(0, self.max_requests - count),
                'max_requests': self.max_requests,
                'current_minute': current.minute,
                'reset_in_seconds': 60 - current.second,
            }
        except Exception as e:
            log.warning(f"Error getting usage stats: {e}")
            return {
                'requests_made': 0,
                'requests_remaining': self.max_requests,
                'max_requests': self.max_requests,
                'error': str(e),
            }

    def reset(self) -> None:
        """Reset the current minute's counter (for testing)."""
        try:
            current = datetime.utcnow()
            window_key = f"{self.key_prefix}:{current.minute}"
            self.redis.delete(window_key)
            log.info("Rate limiter counter reset")
        except Exception as e:
            log.warning(f"Error resetting rate limiter: {e}")


class InMemoryRateLimiter:
    """
    Simple in-memory rate limiter for when Redis is not available.

    Uses a sliding window approach with a list of timestamps.
    """

    def __init__(self, requests_per_minute: int = 50):
        """
        Initialize the in-memory rate limiter.

        Args:
            requests_per_minute: Maximum requests per minute
        """
        self.max_requests = requests_per_minute
        self._timestamps: list = []

    def is_allowed(self) -> bool:
        """Check if request is allowed."""
        now = time.time()
        window_start = now - 60

        # Remove old timestamps
        self._timestamps = [ts for ts in self._timestamps if ts > window_start]

        if len(self._timestamps) < self.max_requests:
            self._timestamps.append(now)
            return True
        return False

    def wait_if_needed(self, timeout: float = 65.0) -> bool:
        """Wait if necessary to stay within rate limits."""
        if self.is_allowed():
            return False

        # Calculate wait time based on oldest timestamp
        if self._timestamps:
            oldest = min(self._timestamps)
            wait_time = oldest + 60 - time.time() + 1
            if wait_time > 0:
                if wait_time > timeout:
                    raise RateLimitExceeded(retry_after=int(wait_time))
                log.info(f"Rate limit hit, waiting {wait_time:.1f}s")
                time.sleep(wait_time)
                return True
        return False

    def acquire(self) -> bool:
        """Acquire a rate limit slot, waiting if necessary."""
        while not self.is_allowed():
            if self._timestamps:
                oldest = min(self._timestamps)
                wait_time = oldest + 60 - time.time() + 1
                if wait_time > 0:
                    time.sleep(wait_time)
        return True

    def get_current_usage(self) -> dict:
        """Get current rate limit usage."""
        now = time.time()
        window_start = now - 60
        active = [ts for ts in self._timestamps if ts > window_start]
        return {
            'requests_made': len(active),
            'requests_remaining': max(0, self.max_requests - len(active)),
            'max_requests': self.max_requests,
        }

    def reset(self) -> None:
        """Reset the rate limiter."""
        self._timestamps = []
