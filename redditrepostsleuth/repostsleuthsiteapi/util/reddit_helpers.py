"""Reddit API helpers with caching for site API."""
import json
import logging
from typing import List

import redis
import requests

log = logging.getLogger(__name__)

# Cache TTL for moderated subreddits (10 minutes)
MOD_SUBS_CACHE_TTL = 600


def get_all_moderated_subs(token: str, user_agent: str) -> List[str]:
    """
    Get all subreddits the user moderates (paginated).

    Args:
        token: Reddit OAuth access token
        user_agent: User agent string for Reddit API

    Returns:
        List of subreddit display names
    """
    headers = {'Authorization': f'Bearer {token}', 'User-Agent': user_agent}
    all_subs = []
    after = None

    while True:
        url = 'https://oauth.reddit.com/subreddits/mine/moderator?limit=100'
        if after:
            url += f'&after={after}'

        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code != 200:
            log.warning('Failed to fetch moderated subs: status=%s', r.status_code)
            break

        data = r.json()
        subs = data.get('data', {}).get('children', [])

        for sub in subs:
            all_subs.append(sub['data']['display_name'])

        after = data.get('data', {}).get('after')
        if not after:
            break

    return all_subs


def get_moderated_subs_cached(
    token: str,
    user_agent: str,
    username: str,
    redis_client: redis.Redis,
    ttl: int = MOD_SUBS_CACHE_TTL
) -> List[str]:
    """
    Get moderated subreddits with Redis caching.

    This should be used by all endpoints that need a moderator's subreddit list.
    Cache key: mod_subs:{username}
    Default TTL: 10 minutes

    Args:
        token: Reddit OAuth access token
        user_agent: User agent string for Reddit API
        username: Reddit username (for cache key)
        redis_client: Redis client instance
        ttl: Cache TTL in seconds (default 10 minutes)

    Returns:
        List of subreddit display names the user moderates
    """
    cache_key = f"mod_subs:{username}"

    # Check cache first
    cached = redis_client.get(cache_key)
    if cached:
        return json.loads(cached)

    # Fetch from Reddit API
    subs = get_all_moderated_subs(token, user_agent)

    # Cache result (even empty list to avoid repeated API calls)
    redis_client.setex(cache_key, ttl, json.dumps(subs))

    return subs
