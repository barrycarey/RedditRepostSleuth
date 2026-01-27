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

__all__ = [
    'UsernameAnalysis',
    'analyze_username',
    'batch_analyze_usernames',
    'SpamFeatureExtractor',
    'Tier1Features',
]
