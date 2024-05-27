import json
import logging

import requests
from redis import Redis

from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.exception import RedGifsTokenException
from redditrepostsleuth.core.util.constants import GENERIC_USER_AGENT

log = logging.getLogger(__name__)

"""
Class for managing and caching RedGifs API tokens.  Currently overkill but if we need to backfill the database or 
API rate limits get tight this will support caching a token for each proxy to Redis
"""
class RedGifsTokenManager:
    def __init__(self):
        config = Config()
        self.redis = Redis(
            host=config.redis_host,
            port=config.redis_port,
            db=config.redis_database,
            password=config.redis_password,
            decode_responses=True
        )


    def _cache_token(self, key: str, token: str) -> None:
        """
        Take a given token and cache it to Redis
        :param key: key of the token
        :param token: API token
        """
        log.info('Caching token for %s', key)
        self.redis.set(f'redgifs-token:{key}', token, ex=82800)

    def remove_redgifs_token(self, key: str) -> None:
        """
        Removed a cached token from Redis with a given key
        :param key: key to remove
        """
        log.info('Removing token for %s', key)
        self.redis.delete(f'redgifs-token:{key}')


    def get_redgifs_token(self, address: str = 'localhost') -> str:
        """
        Either return an existing cached token or create a new one
        :param address: address of the proxy being used
        :return: Token
        """
        cached_token = self.redis.get(f'redgifs-token:{address}')
        if not cached_token:
            return self._request_and_cache_token(address)

        log.debug('Found cached token for %s', address)
        return cached_token


    def _request_and_cache_token(self, proxy_address: str = 'localhost') -> str:
        """
        Hit the Redgif API and request a new auth token.  Cache it to Redis
        :param proxy_address: Proxy to use, if any
        :return: Token
        """
        proxies = None
        if proxy_address != 'localhost':
            proxies = {'http': f'https://{proxy_address}', 'https': f'http://{proxy_address}'}

        token_res = requests.get(
            'https://api.redgifs.com/v2/auth/temporary',
            headers={'User-Agent': GENERIC_USER_AGENT},
            proxies=proxies
        )

        if token_res.status_code != 200:
            log.error('Failed to get RedGif token. Status Code %s', token_res.status_code)
            raise RedGifsTokenException(f'Failed to get RedGif token. Status Code {token_res.status_code}')

        token_data = json.loads(token_res.text)

        self._cache_token(proxy_address or 'localhost', token_data['token'])
        return token_data['token']