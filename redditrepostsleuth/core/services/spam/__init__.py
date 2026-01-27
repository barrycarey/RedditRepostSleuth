"""Spam detection services for Reddit Repost Sleuth."""

from redditrepostsleuth.core.services.spam.username_patterns import (
    UsernameAnalysis,
    analyze_username,
    batch_analyze_usernames,
)
from redditrepostsleuth.core.services.spam.spam_feature_extractor import (
    SpamFeatureExtractor,
    Tier1Features,
)
from redditrepostsleuth.core.services.spam.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerOpen,
    CircuitState,
)
from redditrepostsleuth.core.services.spam.rate_limiter import (
    PerMinuteRateLimiter,
    InMemoryRateLimiter,
    RateLimitExceeded,
)
from redditrepostsleuth.core.services.spam.tier2_features import Tier2Features
from redditrepostsleuth.core.services.spam.user_data_fetcher import (
    UserDataFetcher,
    CachedUserDataFetcher,
    detect_telegram_link,
    detect_adult_platform_link,
)

__all__ = [
    # Username patterns
    'UsernameAnalysis',
    'analyze_username',
    'batch_analyze_usernames',
    # Feature extraction
    'SpamFeatureExtractor',
    'Tier1Features',
    'Tier2Features',
    # Circuit breaker
    'CircuitBreaker',
    'CircuitBreakerOpen',
    'CircuitState',
    # Rate limiter
    'PerMinuteRateLimiter',
    'InMemoryRateLimiter',
    'RateLimitExceeded',
    # User data fetcher
    'UserDataFetcher',
    'CachedUserDataFetcher',
    'detect_telegram_link',
    'detect_adult_platform_link',
]
