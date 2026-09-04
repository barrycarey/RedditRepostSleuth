import logging

import requests
from redis import Redis

from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.exception import PatreonTokenException

log = logging.getLogger(__name__)


class PatreonTokenManager:
    """
    Manages Patreon OAuth2 tokens with automatic refresh.

    Access tokens are cached in Redis with a 28-day TTL.
    Refresh tokens are stored in Redis without TTL to persist across deploys.
    Falls back to config's patreon_refresh_token for initial setup.
    """

    REDIS_ACCESS_TOKEN_KEY = 'patreon:access_token'
    REDIS_REFRESH_TOKEN_KEY = 'patreon:refresh_token'
    ACCESS_TOKEN_TTL = 60 * 60 * 24 * 28  # 28 days in seconds

    def __init__(self, config: Config = None, redis_client: Redis = None):
        self.config = config or Config()
        self.redis = redis_client or Redis(
            host=self.config.redis_host,
            port=self.config.redis_port,
            db=self.config.redis_database,
            password=self.config.redis_password,
            decode_responses=True
        )

    def get_access_token(self) -> str:
        """
        Get a valid access token, refreshing if necessary.

        Returns:
            A valid Patreon access token

        Raises:
            PatreonTokenException: If unable to obtain a valid token
        """
        cached_token = self.redis.get(self.REDIS_ACCESS_TOKEN_KEY)
        if cached_token:
            log.debug('Using cached Patreon access token')
            return cached_token

        log.info('No cached Patreon access token, refreshing')
        return self._refresh_access_token()

    def clear_access_token(self) -> None:
        """Clear the cached access token, forcing a refresh on next request."""
        log.info('Clearing cached Patreon access token')
        self.redis.delete(self.REDIS_ACCESS_TOKEN_KEY)

    def _refresh_access_token(self) -> str:
        """
        Refresh the access token using the refresh token.

        Returns:
            A new access token

        Raises:
            PatreonTokenException: If refresh fails
        """
        refresh_token = self._get_refresh_token()
        if not refresh_token:
            raise PatreonTokenException('No refresh token available')

        if not self.config.patreon_client_id or not self.config.patreon_client_secret:
            raise PatreonTokenException('Patreon client credentials not configured')

        try:
            response = requests.post(
                'https://www.patreon.com/api/oauth2/token',
                data={
                    'grant_type': 'refresh_token',
                    'refresh_token': refresh_token,
                    'client_id': self.config.patreon_client_id,
                    'client_secret': self.config.patreon_client_secret,
                },
                timeout=10
            )

            if response.status_code != 200:
                log.error('Patreon token refresh failed: %s %s', response.status_code, response.text)
                raise PatreonTokenException(f'Token refresh failed: {response.status_code}')

            data = response.json()
            access_token = data['access_token']
            new_refresh_token = data.get('refresh_token')

            self._cache_tokens(access_token, new_refresh_token)
            return access_token

        except requests.RequestException as e:
            log.error('Network error during Patreon token refresh: %s', e)
            raise PatreonTokenException(f'Network error during token refresh: {e}')

    def _get_refresh_token(self) -> str | None:
        """
        Get the refresh token from Redis or fall back to config.

        Returns:
            The refresh token or None if not available
        """
        cached_refresh = self.redis.get(self.REDIS_REFRESH_TOKEN_KEY)
        if cached_refresh:
            return cached_refresh

        # Fall back to config for initial setup
        if self.config.patreon_refresh_token:
            log.info('Using refresh token from config (initial setup)')
            return self.config.patreon_refresh_token

        return None

    def _cache_tokens(self, access_token: str, refresh_token: str = None) -> None:
        """
        Cache tokens to Redis.

        Args:
            access_token: The access token to cache
            refresh_token: The refresh token to cache (if provided)
        """
        log.info('Caching Patreon access token')
        self.redis.set(self.REDIS_ACCESS_TOKEN_KEY, access_token, ex=self.ACCESS_TOKEN_TTL)

        if refresh_token:
            log.info('Caching new Patreon refresh token')
            self.redis.set(self.REDIS_REFRESH_TOKEN_KEY, refresh_token)
