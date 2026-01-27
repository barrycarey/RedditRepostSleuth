"""
Shared spam detection cache using Redis.

Enables cross-worker cache invalidation and distributed caching.
"""
import json
import logging
from typing import Optional, Dict, Any

log = logging.getLogger(__name__)


class SpamDetectionCache:
    """Redis-based cache for spam detection results and feature data."""

    def __init__(self, redis_client, ttl_seconds: int = 3600):
        """
        Initialize cache.

        Args:
            redis_client: Redis client instance
            ttl_seconds: Default TTL (1 hour for user spam features)
        """
        self.redis = redis_client
        self.ttl = ttl_seconds
        self.version = 1  # Increment to invalidate all cached data

    def get_user_features(self, username: str) -> Optional[Dict[str, Any]]:
        """
        Get cached spam features for a user.

        Cache key format: spam:features:v{version}:{username}

        Args:
            username: Reddit username

        Returns:
            Cached features dict or None if not found or expired
        """
        key = f"spam:features:v{self.version}:{username.lower()}"
        try:
            cached = self.redis.get(key)
            if cached:
                log.debug(f"Cache hit for {username}")
                return json.loads(cached)
        except Exception as e:
            log.warning(f"Cache read error: {e}")
        return None

    def set_user_features(
        self,
        username: str,
        features: Dict[str, Any],
        ttl_seconds: Optional[int] = None
    ) -> bool:
        """
        Cache spam features for a user.

        Args:
            username: Reddit username
            features: Feature dict to cache
            ttl_seconds: Custom TTL (uses default if None)

        Returns:
            True if successful
        """
        key = f"spam:features:v{self.version}:{username.lower()}"
        ttl = ttl_seconds or self.ttl

        try:
            self.redis.setex(
                key,
                ttl,
                json.dumps(features, default=str)  # Handle datetime
            )
            log.debug(f"Cached features for {username}")
            return True
        except Exception as e:
            log.warning(f"Cache write error: {e}")
            return False

    def get_user_score(self, username: str) -> Optional[Dict[str, Any]]:
        """
        Get cached spam score result for a user.

        Cache key format: spam:score:v{version}:{username}

        Args:
            username: Reddit username

        Returns:
            Cached score dict or None
        """
        key = f"spam:score:v{self.version}:{username.lower()}"
        try:
            cached = self.redis.get(key)
            if cached:
                return json.loads(cached)
        except Exception as e:
            log.warning(f"Cache read error: {e}")
        return None

    def set_user_score(
        self,
        username: str,
        score_result: Dict[str, Any],
        ttl_seconds: Optional[int] = None
    ) -> bool:
        """
        Cache spam score for a user.

        Args:
            username: Reddit username
            score_result: Score result dict
            ttl_seconds: Custom TTL

        Returns:
            True if successful
        """
        key = f"spam:score:v{self.version}:{username.lower()}"
        ttl = ttl_seconds or self.ttl

        try:
            self.redis.setex(
                key,
                ttl,
                json.dumps(score_result, default=str)
            )
            return True
        except Exception as e:
            log.warning(f"Cache write error: {e}")
            return False

    def invalidate_user(self, username: str) -> bool:
        """
        Invalidate all cached data for a user.

        Useful when user data changes (score threshold updated, etc).

        Args:
            username: Reddit username

        Returns:
            True if successful
        """
        try:
            # Delete both features and score caches
            self.redis.delete(
                f"spam:features:v{self.version}:{username.lower()}",
                f"spam:score:v{self.version}:{username.lower()}"
            )
            log.debug(f"Invalidated cache for {username}")
            return True
        except Exception as e:
            log.warning(f"Cache invalidation error: {e}")
            return False

    def invalidate_all(self) -> bool:
        """
        Invalidate all spam detection cached data.

        Call this when scoring weights are updated or model changes.
        Incrementing version is preferable to clearing Redis.

        Returns:
            True if successful
        """
        try:
            log.info("Incrementing cache version to invalidate all data")
            self.version += 1
            return True
        except Exception as e:
            log.warning(f"Cache invalidation error: {e}")
            return False

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics (for monitoring)."""
        try:
            info = self.redis.info('stats')
            return {
                'total_connections_received': info.get('total_connections_received'),
                'total_commands_processed': info.get('total_commands_processed'),
                'version': self.version,
            }
        except Exception as e:
            log.warning(f"Stats error: {e}")
            return {'version': self.version, 'error': str(e)}

    def get_cache_key_count(self) -> int:
        """
        Get approximate count of spam detection keys in cache.

        Returns:
            Approximate number of cached keys
        """
        try:
            # Use SCAN with pattern matching (safer than KEYS for large datasets)
            count = 0
            cursor = 0
            pattern = f"spam:*:v{self.version}:*"
            while True:
                cursor, keys = self.redis.scan(cursor, match=pattern, count=100)
                count += len(keys)
                if cursor == 0:
                    break
            return count
        except Exception as e:
            log.warning(f"Cache count error: {e}")
            return 0
