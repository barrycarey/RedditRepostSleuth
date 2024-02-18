import json
import logging

import requests
from redis import Redis

from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.exception import RedGifsTokenException
from redditrepostsleuth.core.util.constants import GENERIC_USER_AGENT

log = logging.getLogger(__name__)

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


    def _cache_token(self, key: str, token: str):
        log.info('Caching token for %s', key)
        self.redis.set(f'redgifs-token:{key}', token, ex=82800)

    def remove_redgifs_token(self, key: str):
        log.info('Removing token for %s', key)
        self.redis.delete(f'redgifs-token:{key}')


    def get_redgifs_token(self, address: str = 'localhost') -> str:
        cached_token = self.redis.get(f'redgifs-token:{address}')
        if not cached_token:
            return self._request_and_cache_token(address)

        log.debug('Found cached token for %s', address)
        return cached_token


    def _request_and_cache_token(self, proxy_address):
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