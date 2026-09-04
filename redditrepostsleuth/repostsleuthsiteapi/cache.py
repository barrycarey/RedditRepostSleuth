from falcon_caching import Cache

from redditrepostsleuth.core.config import Config

config = Config()

# Configure caching with Redis backend
cache = Cache(config={
    'CACHE_TYPE': 'redis',
    'CACHE_REDIS_HOST': config.redis_host,
    'CACHE_REDIS_PORT': config.redis_port,
    'CACHE_REDIS_DB': config.redis_database,
    'CACHE_REDIS_PASSWORD': config.redis_password,
    'CACHE_DEFAULT_TIMEOUT': 3600,  # 1 hour
    'CACHE_CONTENT_TYPE_JSON_ONLY': True
})
