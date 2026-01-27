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

# Telegram link patterns for detection
TELEGRAM_PATTERNS = [
    r't\.me/',
    r'telegram\.me/',
    r'telegram\.org/',
]

# Compile patterns for efficiency
_adult_pattern = re.compile('|'.join(ADULT_PLATFORM_PATTERNS), re.IGNORECASE)
_short_link_pattern = re.compile('|'.join(SHORT_LINK_PATTERNS), re.IGNORECASE)
_telegram_pattern = re.compile('|'.join(TELEGRAM_PATTERNS), re.IGNORECASE)


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


def detect_telegram_link(text: Optional[str]) -> bool:
    """Check if text contains a Telegram link."""
    if not text:
        return False
    return bool(_telegram_pattern.search(text))


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


class SpamDetectionTaskWithReddit(SpamDetectionTask):
    """Base task for spam detection with Reddit API access."""
    _reddit = None
    _circuit_breaker = None
    _rate_limiter = None

    @property
    def reddit(self):
        if self._reddit is None:
            from redditrepostsleuth.core.util.reddithelpers import get_reddit_instance
            self._reddit = get_reddit_instance(self.config)
        return self._reddit

    @property
    def circuit_breaker(self):
        if self._circuit_breaker is None:
            from redditrepostsleuth.core.services.spam.circuit_breaker import CircuitBreaker
            self._circuit_breaker = CircuitBreaker(
                failure_threshold=5,
                success_threshold=2,
                recovery_timeout=60
            )
        return self._circuit_breaker

    @property
    def rate_limiter(self):
        if self._rate_limiter is None:
            try:
                import redis
                redis_client = redis.Redis(
                    host=self.config.redis_host,
                    port=self.config.redis_port,
                    password=self.config.redis_password,
                    db=self.config.redis_database
                )
                from redditrepostsleuth.core.services.spam.rate_limiter import PerMinuteRateLimiter
                self._rate_limiter = PerMinuteRateLimiter(
                    redis_client,
                    requests_per_minute=50
                )
            except Exception as e:
                log.warning('Failed to create rate limiter: %s', e)
                self._rate_limiter = None
        return self._rate_limiter


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

    # Skip posts without a valid post_type_id (required by author_activity_tracking table)
    if post_type_id is None:
        log.debug('Skipping author activity tracking for post %s: post_type_id is None', post_id)
        return

    try:
        created_at = datetime.fromisoformat(created_at_iso)
    except (ValueError, TypeError):
        created_at = datetime.utcnow()

    has_adult_link = detect_adult_platform_link(url)
    has_short_link = detect_short_link(url)
    has_telegram_link = detect_telegram_link(url)

    if has_adult_link or has_short_link or has_telegram_link:
        log.info('Detected suspicious link in %s (adult=%s, short=%s, telegram=%s)',
                 url, has_adult_link, has_short_link, has_telegram_link)

    activity = AuthorActivityTracking(
        post_id=post_id,
        author=author,
        subreddit=subreddit,
        created_at=created_at,
        post_type_id=post_type_id,
        is_nsfw=is_nsfw,
        has_adult_link=has_adult_link,
        has_short_link=has_short_link,
        has_telegram_link=has_telegram_link
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


# ============================================================================
# Tier 2 Tasks - Reddit API-based enrichment
# ============================================================================


@celery.task(
    bind=True,
    base=SpamDetectionTaskWithReddit,
    ignore_results=False,
    serializer='pickle',
    autoretry_for=(Exception,),
    retry_kwargs={'max_retries': 3, 'countdown': 60}
)
def enrich_user_features_tier2(self, username: str) -> Optional[dict]:
    """
    Fetch Tier 2 features from Reddit API.

    This task fetches additional user data from the Reddit API
    and updates the user_spam_features record.

    Args:
        username: Reddit username to enrich

    Returns:
        Dict with Tier 2 features or None on failure
    """
    from redditrepostsleuth.core.services.spam.rate_limiter import RateLimitExceeded
    from redditrepostsleuth.core.services.spam.user_data_fetcher import UserDataFetcher

    if not username or username == '[deleted]':
        return None

    log.info('Enriching Tier 2 features for: %s', username)

    try:
        fetcher = UserDataFetcher(
            self.reddit,
            self.uowm,
            circuit_breaker=self.circuit_breaker,
            rate_limiter=self.rate_limiter
        )
        tier2_features = fetcher.fetch_and_enrich(username, scan_profile=True)

        if not tier2_features:
            log.warning('Failed to fetch Tier 2 data for %s', username)
            # Mark as failed in database
            with self.uowm.start() as uow:
                uow.spam_features.mark_tier2_enrichment_failed(username, 'Fetch returned None')
                uow.commit()
            return None

        # Update stored features
        with self.uowm.start() as uow:
            uow.spam_features.update_tier2_features(
                username,
                account_age_days=tier2_features.account_age_days,
                total_karma=tier2_features.total_karma,
                post_karma=tier2_features.post_karma,
                comment_karma=tier2_features.comment_karma,
                karma_per_day=tier2_features.karma_per_day,
                has_verified_email=tier2_features.has_verified_email,
                is_gold=tier2_features.is_gold,
                has_custom_avatar=tier2_features.has_custom_avatar,
                account_suspended=tier2_features.account_suspended,
                has_adult_profile_links=tier2_features.has_adult_profile_links,
                has_telegram_links=tier2_features.has_telegram_links,
                profile_link_sources=tier2_features.profile_link_sources
            )
            uow.commit()

            log.info('Updated Tier 2 features for %s', username)

        return tier2_features.to_dict()

    except RateLimitExceeded as e:
        log.warning('Rate limited enriching %s, retry after %ds', username, e.retry_after)
        raise self.retry(countdown=e.retry_after)

    except Exception as e:
        log.error('Error enriching %s: %s', username, str(e), exc_info=True)
        # Mark as failed in database
        try:
            with self.uowm.start() as uow:
                uow.spam_features.mark_tier2_enrichment_failed(username, str(e)[:200])
                uow.commit()
        except Exception:
            pass
        raise


@celery.task(
    bind=True,
    base=SpamDetectionTaskWithReddit,
    ignore_results=False,
    serializer='pickle',
    autoretry_for=(Exception,),
    retry_kwargs={'max_retries': 3, 'countdown': 60}
)
def check_user_suspended_task(self, username: str) -> bool:
    """
    Quick check if user is suspended.

    Used for training data collection - suspended users are confirmed spam.

    Args:
        username: Reddit username to check

    Returns:
        True if user is suspended/deleted
    """
    from redditrepostsleuth.core.services.spam.rate_limiter import RateLimitExceeded
    from redditrepostsleuth.core.services.spam.user_data_fetcher import UserDataFetcher

    if not username or username == '[deleted]':
        return True

    try:
        fetcher = UserDataFetcher(
            self.reddit,
            self.uowm,
            circuit_breaker=self.circuit_breaker,
            rate_limiter=self.rate_limiter
        )
        is_suspended = fetcher.check_user_suspended(username)

        # Update database if suspended
        if is_suspended:
            with self.uowm.start() as uow:
                uow.spam_features.update_tier2_features(
                    username,
                    account_suspended=True
                )
                uow.commit()

        return is_suspended

    except RateLimitExceeded as e:
        log.warning('Rate limited checking %s, retry after %ds', username, e.retry_after)
        raise self.retry(countdown=e.retry_after)

    except Exception as e:
        log.error('Error checking suspension for %s: %s', username, str(e))
        raise


@celery.task(bind=True, base=SpamDetectionTaskWithReddit, ignore_results=False, serializer='pickle')
def enrich_high_risk_users(self, min_score: float = 0.5, limit: int = 50) -> dict:
    """
    Enrich Tier 2 features for high-risk users.

    Finds users with high spam scores but no Tier 2 data and fetches their data.

    Args:
        min_score: Minimum spam score to qualify
        limit: Maximum users to enrich

    Returns:
        Dict with enrichment results
    """
    import time
    from redditrepostsleuth.core.services.spam.rate_limiter import RateLimitExceeded

    log.info('Enriching high-risk users (score >= %.2f)', min_score)

    with self.uowm.start() as uow:
        # Find users needing enrichment
        high_risk = uow.spam_features.get_high_risk_unenriched(
            min_score=min_score,
            limit=limit
        )
        needs_enrichment = [f.username for f in high_risk]

    if not needs_enrichment:
        log.info('No users need Tier 2 enrichment')
        return {'enriched': 0, 'total': 0, 'suspended': 0, 'failed': 0}

    log.info('Enriching %d users', len(needs_enrichment))

    results = {
        'total': len(needs_enrichment),
        'enriched': 0,
        'suspended': 0,
        'failed': 0,
    }

    for username in needs_enrichment:
        try:
            # Call the enrichment task directly (not async)
            tier2 = enrich_user_features_tier2(username)

            if tier2:
                results['enriched'] += 1
                if tier2.get('account_suspended'):
                    results['suspended'] += 1
            else:
                results['failed'] += 1

            # Small delay between users (rate limit protection)
            time.sleep(1.5)

        except RateLimitExceeded as e:
            log.warning('Rate limited, pausing %ds', e.retry_after)
            time.sleep(e.retry_after)

        except Exception as e:
            log.error('Failed to enrich %s: %s', username, str(e))
            results['failed'] += 1

    log.info('Enrichment complete: %s', results)
    return results


@celery.task(bind=True, base=SpamDetectionTaskWithReddit, ignore_results=False, serializer='pickle')
def scan_user_for_telegram_links(self, username: str) -> dict:
    """
    Scan a user's profile and comments for Telegram links.

    Args:
        username: Reddit username to scan

    Returns:
        Dict with scan results
    """
    from redditrepostsleuth.core.services.spam.rate_limiter import RateLimitExceeded
    from redditrepostsleuth.core.services.spam.user_data_fetcher import UserDataFetcher

    if not username or username == '[deleted]':
        return {'has_telegram_links': False, 'error': 'Invalid username'}

    log.info('Scanning %s for Telegram links', username)

    try:
        fetcher = UserDataFetcher(
            self.reddit,
            self.uowm,
            circuit_breaker=self.circuit_breaker,
            rate_limiter=self.rate_limiter
        )
        result = fetcher.scan_user_profile_links(username)

        # Update database with results
        with self.uowm.start() as uow:
            features = uow.spam_features.get_by_username(username)
            if features:
                features.has_telegram_links = result['has_telegram_links']
                features.has_adult_profile_links = result['has_adult_links']
                features.profile_link_sources = result['sources']
                uow.commit()

        return result

    except RateLimitExceeded as e:
        log.warning('Rate limited scanning %s, retry after %ds', username, e.retry_after)
        return {'has_telegram_links': False, 'error': f'Rate limited, retry after {e.retry_after}s'}

    except Exception as e:
        log.error('Error scanning %s: %s', username, str(e))
        return {'has_telegram_links': False, 'error': str(e)}


# ============================================================================
# Phase 2: Scoring Engine Tasks
# ============================================================================


@celery.task(bind=True, base=SpamDetectionTask, ignore_results=False, serializer='pickle',
             autoretry_for=(Exception,), retry_kwargs={'max_retries': 3, 'countdown': 60})
def score_user_spam(self, username: str) -> Optional[dict]:
    """
    Score a user for spam likelihood.

    This task extracts Tier 1 features and calculates a spam score.
    Results are stored in user_spam_features table.

    Args:
        username: Reddit username to score

    Returns:
        Dict with scoring results or None if insufficient data
    """
    from redditrepostsleuth.core.services.spam.spam_feature_extractor import SpamFeatureExtractor
    from redditrepostsleuth.core.services.spam.spam_scorer import SpamScorer

    if not username or username == '[deleted]':
        return None

    log.info('Scoring user for spam: %s', username)

    try:
        # Extract features
        extractor = SpamFeatureExtractor(self.uowm)
        features = extractor.extract_tier1_features(username)

        if not features:
            log.debug('Insufficient data to score user: %s', username)
            return None

        # Score the user
        scorer = SpamScorer(self.uowm)
        result = scorer.score_user(features)

        # Update stored features with scoring results
        with self.uowm.start() as uow:
            spam_features = uow.spam_features.get_by_username(username)
            if spam_features:
                spam_features.spam_score = result.score
                spam_features.spam_score_confidence = result.confidence
                spam_features.computed_at = datetime.utcnow()
                # Store feature data with scoring info
                feature_dict = features.to_dict()
                feature_dict['rule_score'] = result.score
                feature_dict['risk_level'] = result.risk_level
                feature_dict['top_contributing_factors'] = result.reasons
                spam_features.feature_data = feature_dict
            else:
                # Create new record via extractor
                extractor.store_features(features)
                # Then update with scoring info
                spam_features = uow.spam_features.get_by_username(username)
                if spam_features:
                    spam_features.spam_score = result.score
                    spam_features.spam_score_confidence = result.confidence
            uow.commit()

        log.info(
            'Scored user %s: %.2f (%s)',
            username, result.score, result.risk_level
        )
        return result.to_dict()

    except Exception as e:
        log.error('Error scoring user %s: %s', username, str(e), exc_info=True)
        raise


@celery.task(bind=True, base=SpamDetectionTask, ignore_results=False, serializer='pickle',
             autoretry_for=(Exception,), retry_kwargs={'max_retries': 3, 'countdown': 60})
def score_and_flag_user(
    self,
    username: str,
    update_user_review: bool = True
) -> Optional[dict]:
    """
    Score a user and optionally update user_review table.

    This is the main entry point for spam detection, combining
    feature extraction, scoring, and flagging.

    Args:
        username: Reddit username to analyze
        update_user_review: Whether to update user_review table

    Returns:
        Dict with scoring results or None if insufficient data
    """
    from redditrepostsleuth.core.db.databasemodels import UserReview

    if not username or username == '[deleted]':
        return None

    # Score the user (calls the task directly, not async)
    result_dict = score_user_spam(username)

    if not result_dict:
        return None

    # Update user_review if requested
    if update_user_review:
        with self.uowm.start() as uow:
            review = uow.user_review.get_by_username(username)

            if review:
                # Update existing review
                review.spam_score = result_dict['score']
                review.spam_score_confidence = result_dict['confidence']
                review.spam_score_updated_at = datetime.utcnow()
                review.risk_level = result_dict['risk_level']
            else:
                # Create new review entry
                review = UserReview(
                    username=username,
                    spam_score=result_dict['score'],
                    spam_score_confidence=result_dict['confidence'],
                    spam_score_updated_at=datetime.utcnow(),
                    risk_level=result_dict['risk_level'],
                )
                uow.user_review.add(review)

            uow.commit()

        log.info('Updated user_review for %s', username)

    return result_dict


@celery.task(bind=True, base=SpamDetectionTask, ignore_results=False, serializer='pickle')
def batch_score_users(self, usernames: List[str]) -> dict:
    """
    Score multiple users in batch.

    Args:
        usernames: List of Reddit usernames to score

    Returns:
        Dict with results summary
    """
    log.info('Batch scoring %d users', len(usernames))

    results = {
        'total': len(usernames),
        'scored': 0,
        'skipped': 0,
        'failed': 0,
        'high_risk': 0,
        'critical_risk': 0,
    }

    for username in usernames:
        if not username or username == '[deleted]':
            results['skipped'] += 1
            continue

        try:
            result = score_and_flag_user(username, update_user_review=True)

            if result:
                results['scored'] += 1
                if result['risk_level'] == 'CRITICAL':
                    results['critical_risk'] += 1
                elif result['risk_level'] == 'HIGH':
                    results['high_risk'] += 1
            else:
                results['skipped'] += 1

        except Exception as e:
            log.error('Failed to score %s: %s', username, str(e))
            results['failed'] += 1

    log.info('Batch scoring complete: %s', results)
    return results


@celery.task(bind=True, base=SpamDetectionTask, ignore_results=False, serializer='pickle')
def score_top_reposters(
    self,
    limit: int = 100,
    days: int = 30,
    min_reposts: int = 5
) -> dict:
    """
    Score top reposters for spam detection.

    Retrieves users with most reposts and scores them.

    Args:
        limit: Maximum users to analyze
        days: Look back period
        min_reposts: Minimum reposts to qualify

    Returns:
        Dict with results summary
    """
    from sqlalchemy import func
    from redditrepostsleuth.core.db.databasemodels import Repost

    log.info('Scoring top %d reposters from past %d days', limit, days)

    usernames_to_score = []

    with self.uowm.start() as uow:
        cutoff = datetime.utcnow() - timedelta(days=days)
        results = uow.session.query(
            Repost.author,
            func.count(Repost.id).label('repost_count')
        ).filter(
            Repost.detected_at >= cutoff,
            Repost.author != None,
            Repost.author != '[deleted]'
        ).group_by(Repost.author).having(
            func.count(Repost.id) >= min_reposts
        ).order_by(
            func.count(Repost.id).desc()
        ).limit(limit).all()

        for row in results:
            if row.author:
                usernames_to_score.append(row.author)

    if not usernames_to_score:
        log.info('No top reposters found matching criteria')
        return {'analyzed': 0, 'total': 0}

    # Filter out recently analyzed users
    users_needing_scoring = []
    with self.uowm.start() as uow:
        for username in usernames_to_score:
            features = uow.spam_features.get_by_username(username)
            if not features or not features.spam_score:
                users_needing_scoring.append(username)
            elif features.computed_at:
                # Re-score if older than 7 days
                age = datetime.utcnow() - features.computed_at
                if age.days > 7:
                    users_needing_scoring.append(username)

    log.info('Found %d users needing scoring (out of %d top reposters)',
             len(users_needing_scoring), len(usernames_to_score))

    if not users_needing_scoring:
        return {'analyzed': 0, 'total': len(usernames_to_score), 'message': 'All already scored'}

    return batch_score_users(users_needing_scoring)
