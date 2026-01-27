"""
Spam Feature Extractor Service.

This service extracts Tier 1 spam detection features from existing database data
with zero API calls. Features are computed from:
- Author activity tracking
- Repost records
- Summons records
- Username pattern analysis
"""

import math
from collections import Counter
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from functools import lru_cache
from typing import Dict, List, Optional, Tuple

from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.core.logging import get_configured_logger
from redditrepostsleuth.core.services.spam.username_patterns import analyze_username

log = get_configured_logger('redditrepostsleuth')

# Minimum posts required for meaningful analysis
MIN_POSTS_FOR_ANALYSIS = 3

# Cache TTL for spam subreddits (1 hour in seconds)
SPAM_SUBREDDIT_CACHE_TTL = 3600


@dataclass
class Tier1Features:
    """Tier 1 spam detection features extracted from database data."""

    # Basic activity metrics
    username: str
    total_posts_indexed: int = 0
    total_reposts_detected: int = 0
    repost_ratio: float = 0.0
    unique_subreddits_posted: int = 0
    posts_per_day_avg: float = 0.0
    first_post_date: Optional[datetime] = None
    last_post_date: Optional[datetime] = None
    account_age_days: int = 0
    nsfw_post_count: int = 0
    nsfw_post_ratio: float = 0.0
    summons_received: int = 0

    # Adult platform / promotional link metrics
    adult_platform_post_count: int = 0
    adult_platform_ratio: float = 0.0
    short_link_post_count: int = 0
    short_link_ratio: float = 0.0
    detected_platforms: List[str] = field(default_factory=list)

    # Username pattern metrics
    username_suspicious_pattern: bool = False
    username_pattern_confidence: float = 0.0
    username_pattern_matches: List[str] = field(default_factory=list)

    # Subreddit behavior metrics
    subreddit_distribution: Dict[str, int] = field(default_factory=dict)
    subreddit_concentration_hhi: float = 0.0
    karma_farming_sub_posts: int = 0
    easy_karma_sub_posts: int = 0
    spam_subreddit_posts: int = 0

    # Posting pattern metrics
    max_posts_per_day: int = 0
    posting_entropy: float = 0.0
    burst_posting_detected: bool = False
    avg_time_between_posts_minutes: float = 0.0

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON storage."""
        data = asdict(self)
        # Convert datetimes to ISO format strings
        if data['first_post_date']:
            data['first_post_date'] = data['first_post_date'].isoformat()
        if data['last_post_date']:
            data['last_post_date'] = data['last_post_date'].isoformat()
        return data

    @classmethod
    def from_dict(cls, data: dict) -> 'Tier1Features':
        """Create from dictionary."""
        # Convert ISO strings back to datetimes
        if data.get('first_post_date') and isinstance(data['first_post_date'], str):
            data['first_post_date'] = datetime.fromisoformat(data['first_post_date'])
        if data.get('last_post_date') and isinstance(data['last_post_date'], str):
            data['last_post_date'] = datetime.fromisoformat(data['last_post_date'])
        return cls(**data)


class SpamFeatureExtractor:
    """
    Extracts Tier 1 spam detection features for users.

    Features are computed from existing database data without any API calls.
    This enables batch processing and low-latency feature extraction.
    """

    def __init__(self, uowm: UnitOfWorkManager):
        """
        Initialize the feature extractor.

        Args:
            uowm: Unit of Work Manager for database access
        """
        self.uowm = uowm
        self._spam_subreddits_cache: Optional[Tuple[datetime, dict]] = None

    def _get_spam_subreddits(self) -> dict:
        """
        Get spam subreddits with caching (1 hour TTL).

        Returns:
            Dict mapping lowercase subreddit name to (category, weight) tuple
        """
        now = datetime.utcnow()

        # Check cache
        if self._spam_subreddits_cache:
            cache_time, cache_data = self._spam_subreddits_cache
            if (now - cache_time).total_seconds() < SPAM_SUBREDDIT_CACHE_TTL:
                return cache_data

        # Refresh cache
        with self.uowm.start() as uow:
            spam_subs = uow.spam_subreddit.get_as_dict()

        self._spam_subreddits_cache = (now, spam_subs)
        return spam_subs

    def is_user_worth_analyzing(self, username: str) -> bool:
        """
        Quick check if a user has enough data for meaningful analysis.

        Args:
            username: Reddit username

        Returns:
            True if user has enough posts for analysis
        """
        if not username or username == '[deleted]':
            return False

        with self.uowm.start() as uow:
            post_count = uow.author_activity.count_by_author(username)
            return post_count >= MIN_POSTS_FOR_ANALYSIS

    def check_username_pattern(self, username: str) -> Tuple[bool, float, List[str]]:
        """
        Analyze username for suspicious patterns.

        Args:
            username: Reddit username to analyze

        Returns:
            Tuple of (is_suspicious, confidence, matched_patterns)
        """
        analysis = analyze_username(username)
        return (
            analysis.is_suspicious,
            analysis.confidence,
            analysis.matched_patterns
        )

    def extract_subreddit_behavior(self, username: str) -> dict:
        """
        Extract subreddit posting behavior metrics.

        Args:
            username: Reddit username

        Returns:
            Dict with subreddit behavior metrics
        """
        with self.uowm.start() as uow:
            distribution = uow.author_activity.get_author_subreddit_distribution(username)

        if not distribution:
            return {
                'distribution': {},
                'concentration_hhi': 0.0,
                'unique_count': 0,
            }

        # Calculate Herfindahl-Hirschman Index (HHI) for concentration
        total_posts = sum(distribution.values())
        hhi = 0.0
        if total_posts > 0:
            for count in distribution.values():
                share = count / total_posts
                hhi += share * share

        return {
            'distribution': distribution,
            'concentration_hhi': hhi,
            'unique_count': len(distribution),
        }

    def get_activity_timeline(self, username: str) -> dict:
        """
        Analyze posting timeline for patterns.

        Args:
            username: Reddit username

        Returns:
            Dict with timeline metrics (posting intervals, entropy, burst detection)
        """
        with self.uowm.start() as uow:
            activities = uow.author_activity.get_by_author(username, limit=500)

        if not activities:
            return {
                'first_post_date': None,
                'last_post_date': None,
                'account_age_days': 0,
                'posts_per_day_avg': 0.0,
                'max_posts_per_day': 0,
                'posting_entropy': 0.0,
                'burst_posting_detected': False,
                'avg_time_between_posts_minutes': 0.0,
            }

        # Sort by created_at
        activities = sorted(activities, key=lambda a: a.created_at)

        first_post = activities[0].created_at
        last_post = activities[-1].created_at
        account_age_days = max(1, (last_post - first_post).days)
        posts_per_day = len(activities) / account_age_days

        # Calculate daily post counts
        daily_counts = Counter()
        for activity in activities:
            day_key = activity.created_at.date()
            daily_counts[day_key] += 1

        max_posts_per_day = max(daily_counts.values()) if daily_counts else 0

        # Calculate posting entropy (measures randomness of posting times)
        # Higher entropy = more random/natural posting
        # Lower entropy = more regular/automated posting
        hour_counts = Counter()
        for activity in activities:
            hour_counts[activity.created_at.hour] += 1

        posting_entropy = 0.0
        total = sum(hour_counts.values())
        if total > 0:
            for count in hour_counts.values():
                if count > 0:
                    p = count / total
                    posting_entropy -= p * math.log2(p)
            # Normalize by max entropy (log2(24) for 24 hours)
            posting_entropy = posting_entropy / math.log2(24)

        # Calculate average time between posts
        intervals = []
        for i in range(1, len(activities)):
            interval = (activities[i].created_at - activities[i - 1].created_at).total_seconds() / 60
            intervals.append(interval)

        avg_interval = sum(intervals) / len(intervals) if intervals else 0.0

        # Detect burst posting (>10 posts in an hour)
        hourly_counts = Counter()
        for activity in activities:
            hour_key = activity.created_at.replace(minute=0, second=0, microsecond=0)
            hourly_counts[hour_key] += 1

        burst_detected = any(count > 10 for count in hourly_counts.values())

        return {
            'first_post_date': first_post,
            'last_post_date': last_post,
            'account_age_days': account_age_days,
            'posts_per_day_avg': posts_per_day,
            'max_posts_per_day': max_posts_per_day,
            'posting_entropy': posting_entropy,
            'burst_posting_detected': burst_detected,
            'avg_time_between_posts_minutes': avg_interval,
        }

    def extract_tier1_features(self, username: str) -> Optional[Tier1Features]:
        """
        Extract all Tier 1 features for a user.

        This is the main extraction method that computes all features
        from database data with zero API calls.

        Args:
            username: Reddit username

        Returns:
            Tier1Features object, or None if insufficient data
        """
        if not self.is_user_worth_analyzing(username):
            log.debug('User %s has insufficient data for analysis', username)
            return None

        features = Tier1Features(username=username)

        # Get basic author stats
        with self.uowm.start() as uow:
            stats = uow.author_activity.get_author_stats(username)

            features.total_posts_indexed = stats.get('total_posts', 0)
            features.nsfw_post_count = stats.get('nsfw_count', 0)
            features.adult_platform_post_count = stats.get('adult_link_count', 0)
            features.short_link_post_count = stats.get('short_link_count', 0)
            features.unique_subreddits_posted = stats.get('unique_subreddits', 0)

            # Calculate ratios
            if features.total_posts_indexed > 0:
                features.nsfw_post_ratio = features.nsfw_post_count / features.total_posts_indexed
                features.adult_platform_ratio = features.adult_platform_post_count / features.total_posts_indexed
                features.short_link_ratio = features.short_link_post_count / features.total_posts_indexed

            # Get repost count
            features.total_reposts_detected = uow.repost.count_reposts_by_author(username)
            if features.total_posts_indexed > 0:
                features.repost_ratio = features.total_reposts_detected / features.total_posts_indexed

            # Get summons count
            features.summons_received = uow.summons.count_by_post_author(username)

        # Username pattern analysis
        is_suspicious, confidence, patterns = self.check_username_pattern(username)
        features.username_suspicious_pattern = is_suspicious
        features.username_pattern_confidence = confidence
        features.username_pattern_matches = patterns

        # Subreddit behavior
        sub_behavior = self.extract_subreddit_behavior(username)
        features.subreddit_distribution = sub_behavior['distribution']
        features.subreddit_concentration_hhi = sub_behavior['concentration_hhi']

        # Check for spam subreddits
        spam_subs = self._get_spam_subreddits()
        for sub, count in features.subreddit_distribution.items():
            sub_lower = sub.lower()
            if sub_lower in spam_subs:
                category, weight = spam_subs[sub_lower]
                features.spam_subreddit_posts += count
                if category == 'karma_farming':
                    features.karma_farming_sub_posts += count
                elif category == 'easy_karma':
                    features.easy_karma_sub_posts += count

        # Activity timeline
        timeline = self.get_activity_timeline(username)
        features.first_post_date = timeline['first_post_date']
        features.last_post_date = timeline['last_post_date']
        features.account_age_days = timeline['account_age_days']
        features.posts_per_day_avg = timeline['posts_per_day_avg']
        features.max_posts_per_day = timeline['max_posts_per_day']
        features.posting_entropy = timeline['posting_entropy']
        features.burst_posting_detected = timeline['burst_posting_detected']
        features.avg_time_between_posts_minutes = timeline['avg_time_between_posts_minutes']

        return features

    def store_features(self, features: Tier1Features) -> bool:
        """
        Store extracted features to the database.

        Args:
            features: Tier1Features to store

        Returns:
            True if stored successfully
        """
        try:
            with self.uowm.start() as uow:
                uow.spam_features.update_or_create(
                    username=features.username,
                    total_posts=features.total_posts_indexed,
                    nsfw_post_count=features.nsfw_post_count,
                    nsfw_post_ratio=features.nsfw_post_ratio,
                    unique_subreddit_count=features.unique_subreddits_posted,
                    adult_link_count=features.adult_platform_post_count,
                    short_link_count=features.short_link_post_count,
                    spam_subreddit_count=features.spam_subreddit_posts,
                    avg_posts_per_day=features.posts_per_day_avg,
                    max_posts_per_day=features.max_posts_per_day,
                    feature_data=features.to_dict(),
                )
                uow.commit()
            return True
        except Exception as e:
            log.error('Failed to store features for %s: %s', features.username, str(e))
            return False

    def extract_and_store(self, username: str) -> Optional[Tier1Features]:
        """
        Extract Tier 1 features and store them in the database.

        Args:
            username: Reddit username

        Returns:
            Tier1Features if successful, None otherwise
        """
        features = self.extract_tier1_features(username)
        if features:
            self.store_features(features)
        return features
