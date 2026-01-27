import re
from datetime import datetime
from datetime import timedelta
from typing import Dict, List, Optional

from celery import Task

from redditrepostsleuth.core.celery import celery
from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.db.databasemodels import AuthorActivityTracking
from redditrepostsleuth.core.db.db_utils import get_db_engine
from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.core.logging import get_configured_logger

log = get_configured_logger('redditrepostsleuth')


# Adult platform URL patterns for detection
ADULT_PLATFORM_PATTERNS = [
    r'onlyfans\.com',
    r'fansly\.com',
    r'fancentro\.com',
    r'manyvids\.com',
    r'pornhub\.com/model',
    r'pornhub\.com/users',
    r'xvideos\.com/channels',
    r'chaturbate\.com',
    r'myfreecams\.com',
    r'stripchat\.com',
    r'cam4\.com',
    r'bongacams\.com',
    r'livejasmin\.com',
    r'streamate\.com',
    r'camsoda\.com',
    r'loyalfans\.com',
    r'admireme\.vip',
    r'frisk\.chat',
]

# Short link / URL shortener patterns
# Note: patterns use word boundaries or specific formats to avoid false positives
SHORT_LINK_PATTERNS = [
    r'bit\.ly/',
    r'tinyurl\.com/',
    r'goo\.gl/',
    r'(?:^|//)t\.co/',
    r'ow\.ly/',
    r'is\.gd/',
    r'buff\.ly/',
    r'adf\.ly/',
    r'j\.mp/',
    r'v\.gd/',
    r'shorte\.st/',
    r'linktr\.ee/',
    r'beacons\.ai/',
    r'allmylinks\.com/',
    r'campsite\.bio/',
    r'linkin\.bio/',
    r'lnk\.bio/',
    r'tap\.bio/',
    r'withkoji\.com/',
    r'snipfeed\.co/',
    r'hoo\.be/',
]

# Compile patterns for efficiency
_adult_pattern = re.compile('|'.join(ADULT_PLATFORM_PATTERNS), re.IGNORECASE)
_short_link_pattern = re.compile('|'.join(SHORT_LINK_PATTERNS), re.IGNORECASE)


def detect_adult_platform_link(url: Optional[str]) -> bool:
    """Check if URL contains an adult platform link."""
    if not url:
        return False
    return bool(_adult_pattern.search(url))


def detect_short_link(url: Optional[str]) -> bool:
    """Check if URL contains a URL shortener or link aggregator."""
    if not url:
        return False
    return bool(_short_link_pattern.search(url))


class SpamDetectionTask(Task):
    """Base task for spam detection with shared resources."""
    _config = None
    _uowm = None

    @property
    def config(self):
        if self._config is None:
            self._config = Config()
        return self._config

    @property
    def uowm(self):
        if self._uowm is None:
            self._uowm = UnitOfWorkManager(get_db_engine(self.config))
        return self._uowm


@celery.task(bind=True, base=SpamDetectionTask, ignore_results=True, serializer='pickle',
             autoretry_for=(Exception,), retry_kwargs={'max_retries': 3, 'countdown': 60})
def track_author_activity(self, post_id: str, author: str, subreddit: str,
                          url: Optional[str], is_nsfw: bool, post_type_id: int,
                          created_at_iso: str):
    """
    Track author activity for spam detection.

    This task is decoupled from the main ingest pipeline to:
    - Isolate failures from affecting post ingestion
    - Allow independent scaling via spam_detection queue
    - Keep the ingest pipeline performant

    Args:
        post_id: Reddit post ID
        author: Reddit username
        subreddit: Subreddit name
        url: Post URL (may be None)
        is_nsfw: Whether the post is NSFW
        post_type_id: Type of post (1=text, 2=image, 3=link)
        created_at_iso: ISO format datetime string
    """
    if not author or author == '[deleted]':
        return

    try:
        created_at = datetime.fromisoformat(created_at_iso)
    except (ValueError, TypeError):
        created_at = datetime.utcnow()

    has_adult_link = detect_adult_platform_link(url)
    has_short_link = detect_short_link(url)

    activity = AuthorActivityTracking(
        post_id=post_id,
        author=author,
        subreddit=subreddit,
        created_at=created_at,
        post_type_id=post_type_id,
        is_nsfw=is_nsfw,
        has_adult_link=has_adult_link,
        has_short_link=has_short_link
    )

    try:
        with self.uowm.start() as uow:
            # Check if already tracked (idempotent)
            existing = uow.author_activity.get_by_post_id(post_id)
            if existing:
                log.debug('Post %s already tracked for author activity', post_id)
                return

            uow.author_activity.add(activity)
            uow.commit()
            log.debug('Tracked activity for author %s on post %s', author, post_id)
    except Exception as e:
        log.warning('Failed to track author activity for post %s: %s', post_id, str(e))
        raise


@celery.task(bind=True, base=SpamDetectionTask, ignore_results=True, serializer='pickle',
             autoretry_for=(Exception,), retry_kwargs={'max_retries': 3, 'countdown': 60})
def compute_user_spam_features_tier1(self, username: str) -> Optional[dict]:
    """
    Compute and store Tier 1 spam features for a user.

    This task extracts features from existing database data with zero API calls.
    Features are stored in user_spam_features table.

    Args:
        username: Reddit username to analyze

    Returns:
        Dict of extracted features, or None if insufficient data
    """
    from redditrepostsleuth.core.services.spam.spam_feature_extractor import SpamFeatureExtractor

    if not username or username == '[deleted]':
        return None

    try:
        extractor = SpamFeatureExtractor(self.uowm)
        features = extractor.extract_and_store(username)

        if features:
            log.info('Computed Tier 1 features for user %s: %d posts, %.2f repost ratio',
                     username, features.total_posts_indexed, features.repost_ratio)
            return features.to_dict()
        else:
            log.debug('Insufficient data to compute features for user %s', username)
            return None

    except Exception as e:
        log.error('Failed to compute spam features for %s: %s', username, str(e))
        raise


@celery.task(bind=True, base=SpamDetectionTask, ignore_results=True, serializer='pickle')
def batch_compute_spam_features(self, usernames: List[str]) -> dict:
    """
    Compute Tier 1 features for multiple users.

    Args:
        usernames: List of Reddit usernames to analyze

    Returns:
        Dict with success_count, failure_count, and skipped_count
    """
    from redditrepostsleuth.core.services.spam.spam_feature_extractor import SpamFeatureExtractor

    if not usernames:
        return {'success_count': 0, 'failure_count': 0, 'skipped_count': 0}

    extractor = SpamFeatureExtractor(self.uowm)
    success_count = 0
    failure_count = 0
    skipped_count = 0

    for username in usernames:
        if not username or username == '[deleted]':
            skipped_count += 1
            continue

        try:
            features = extractor.extract_and_store(username)
            if features:
                success_count += 1
            else:
                skipped_count += 1
        except Exception as e:
            log.warning('Failed to compute features for %s: %s', username, str(e))
            failure_count += 1

    log.info('Batch feature computation complete: %d success, %d failed, %d skipped',
             success_count, failure_count, skipped_count)

    return {
        'success_count': success_count,
        'failure_count': failure_count,
        'skipped_count': skipped_count
    }


@celery.task(bind=True, base=SpamDetectionTask, ignore_results=True, serializer='pickle')
def analyze_top_reposters(self, limit: int = 100, days: int = 30) -> dict:
    """
    Analyze spam features for top reposters.

    This task finds the top reposters across the platform and computes
    their spam features for review.

    Args:
        limit: Maximum number of reposters to analyze
        days: Look back period in days

    Returns:
        Dict with analyzed_count and high_risk_count
    """
    from redditrepostsleuth.core.services.spam.spam_feature_extractor import SpamFeatureExtractor

    analyzed_count = 0
    high_risk_count = 0
    usernames_to_analyze = set()

    try:
        # Get top reposters from repost table
        with self.uowm.start() as uow:
            # Get unique authors with high repost counts
            from sqlalchemy import func
            from redditrepostsleuth.core.db.databasemodels import Repost

            cutoff = datetime.utcnow() - timedelta(days=days)
            results = uow.session.query(
                Repost.author,
                func.count(Repost.id).label('repost_count')
            ).filter(
                Repost.detected_at >= cutoff,
                Repost.author != None,
                Repost.author != '[deleted]'
            ).group_by(Repost.author).order_by(
                func.count(Repost.id).desc()
            ).limit(limit).all()

            for row in results:
                if row.author:
                    usernames_to_analyze.add(row.author)

        # Analyze each user
        extractor = SpamFeatureExtractor(self.uowm)
        for username in usernames_to_analyze:
            try:
                features = extractor.extract_and_store(username)
                if features:
                    analyzed_count += 1
                    # Consider high risk if: high repost ratio, suspicious username, or many spam sub posts
                    if (features.repost_ratio > 0.5 or
                            features.username_suspicious_pattern or
                            features.spam_subreddit_posts > 5):
                        high_risk_count += 1
            except Exception as e:
                log.warning('Failed to analyze reposter %s: %s', username, str(e))

        log.info('Analyzed %d top reposters, %d high risk', analyzed_count, high_risk_count)

    except Exception as e:
        log.error('Failed to analyze top reposters: %s', str(e))
        raise

    return {
        'analyzed_count': analyzed_count,
        'high_risk_count': high_risk_count
    }


@celery.task(bind=True, base=SpamDetectionTask, ignore_results=True, serializer='pickle')
def cleanup_old_feature_records(self, keep_per_user: int = 5) -> dict:
    """
    Clean up old feature records.

    Note: Currently UserSpamFeatures uses username as PK (one record per user),
    so this task is a no-op. Kept for future use if we switch to historical tracking.

    Args:
        keep_per_user: Number of records to keep per user

    Returns:
        Dict with deleted_count
    """
    # Currently a no-op since UserSpamFeatures has username as unique PK
    log.info('Feature cleanup task executed (no-op with current schema)')
    return {'deleted_count': 0}
