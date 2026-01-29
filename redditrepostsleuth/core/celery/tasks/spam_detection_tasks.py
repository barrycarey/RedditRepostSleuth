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
        log.debug('Skipping author activity for post %s: author is %s', post_id, author)
        return

    # Skip posts without a valid post_type_id (required by author_activity_tracking table)
    if post_type_id is None:
        log.debug('Skipping author activity for post %s: post_type_id is None', post_id)
        return

    log.debug('Tracking author activity: post=%s, author=%s, subreddit=%s, nsfw=%s, type=%d',
              post_id, author, subreddit, is_nsfw, post_type_id)

    try:
        created_at = datetime.fromisoformat(created_at_iso)
    except (ValueError, TypeError):
        log.debug('Invalid created_at_iso for post %s, using utcnow()', post_id)
        created_at = datetime.utcnow()

    has_adult_link = detect_adult_platform_link(url)
    has_short_link = detect_short_link(url)
    has_telegram_link = detect_telegram_link(url)

    if has_adult_link or has_short_link or has_telegram_link:
        log.info('Suspicious link detected in post %s by %s: adult=%s, short=%s, telegram=%s, url=%s',
                 post_id, author, has_adult_link, has_short_link, has_telegram_link, url)
    else:
        log.debug('Link analysis for post %s: adult=%s, short=%s, telegram=%s',
                  post_id, has_adult_link, has_short_link, has_telegram_link)

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
                log.debug('Post %s already tracked for author activity, skipping', post_id)
                return

            uow.author_activity.add(activity)
            uow.commit()
            log.debug('Successfully tracked activity for author %s on post %s in r/%s',
                      author, post_id, subreddit)
    except Exception as e:
        log.warning('Failed to track author activity for post %s by %s: %s',
                    post_id, author, str(e), exc_info=True)
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
        log.debug('Skipping Tier 1 feature computation for invalid username: %s', username)
        return None

    log.info('Starting Tier 1 feature computation for user: %s', username)

    try:
        log.debug('Initializing SpamFeatureExtractor for %s', username)
        extractor = SpamFeatureExtractor(self.uowm)
        features = extractor.extract_and_store(username)

        if features:
            log.info('Tier 1 features computed for %s: posts=%d, reposts=%d (ratio=%.2f), '
                     'nsfw_ratio=%.2f, adult_ratio=%.2f, karma_farm_posts=%d',
                     username, features.total_posts_indexed, features.total_reposts_detected,
                     features.repost_ratio, features.nsfw_post_ratio,
                     features.adult_platform_ratio, features.karma_farming_sub_posts)
            return features.to_dict()
        else:
            log.info('Insufficient data to compute Tier 1 features for user %s', username)
            return None

    except Exception as e:
        log.error('Failed to compute Tier 1 features for %s: %s', username, str(e), exc_info=True)
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
        log.debug('Skipping Tier 2 enrichment for invalid username: %s', username)
        return None

    log.info('Starting Tier 2 enrichment for user: %s', username)

    try:
        log.debug('Initializing UserDataFetcher for %s', username)
        fetcher = UserDataFetcher(
            self.reddit,
            self.uowm,
            circuit_breaker=self.circuit_breaker,
            rate_limiter=self.rate_limiter
        )

        log.debug('Fetching Tier 2 data for %s (scan_profile=True, scan_posts=True)', username)
        tier2_features = fetcher.fetch_and_enrich(username, scan_profile=True, scan_posts=True)

        if not tier2_features:
            log.warning('Failed to fetch Tier 2 data for %s (returned None)', username)
            # Mark as failed in database
            with self.uowm.start() as uow:
                uow.spam_features.mark_tier2_enrichment_failed(username, 'Fetch returned None')
                uow.commit()
            return None

        log.debug('Tier 2 data fetched for %s: age_days=%s, karma=%s, suspended=%s',
                  username, tier2_features.account_age_days, tier2_features.total_karma,
                  tier2_features.account_suspended)

        # Update stored features
        log.debug('Updating database with Tier 2 features for %s', username)
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
                profile_link_sources=tier2_features.profile_link_sources,
                has_promotional_post_links=tier2_features.has_promotional_post_links,
                detected_platforms=tier2_features.detected_platforms
            )
            uow.commit()

            log.info('Tier 2 enrichment complete for %s: age=%d days, karma=%d, suspended=%s, adult_links=%s',
                     username, tier2_features.account_age_days or 0, tier2_features.total_karma or 0,
                     tier2_features.account_suspended, tier2_features.has_adult_profile_links)

        # Queue re-scoring with Tier 2 data (non-blocking)
        log.info('Queueing Tier 2 re-scoring for %s', username)
        rescore_user_with_tier2.delay(username)

        return tier2_features.to_dict()

    except RateLimitExceeded as e:
        log.warning('Rate limited during Tier 2 enrichment for %s, will retry after %ds',
                    username, e.retry_after)
        raise self.retry(countdown=e.retry_after)

    except Exception as e:
        log.error('Error during Tier 2 enrichment for %s: %s', username, str(e), exc_info=True)
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
        log.debug('Skipping scoring for invalid username: %s', username)
        return None

    log.info('Starting spam scoring task for user: %s', username)

    try:
        # Extract features
        log.debug('Initializing SpamFeatureExtractor for %s', username)
        extractor = SpamFeatureExtractor(self.uowm)
        features = extractor.extract_tier1_features(username)

        if not features:
            log.info('Insufficient data to score user %s, skipping', username)
            return None

        log.debug('Features extracted for %s: posts=%d, reposts=%d, repost_ratio=%.3f',
                  username, features.total_posts_indexed, features.total_reposts_detected,
                  features.repost_ratio)

        # Score the user
        log.debug('Initializing SpamScorer for %s', username)
        scorer = SpamScorer(self.uowm)
        result = scorer.score_user(features)

        log.debug('Scoring complete for %s: score=%.3f, confidence=%.2f, risk=%s',
                  username, result.score, result.confidence, result.risk_level)

        # Update stored features with scoring results
        log.debug('Updating database with scoring results for %s', username)
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
                log.debug('Updated existing spam_features record for %s', username)
            else:
                # Create new record via extractor
                log.debug('Creating new spam_features record for %s', username)
                extractor.store_features(features)
                # Then update with scoring info
                spam_features = uow.spam_features.get_by_username(username)
                if spam_features:
                    spam_features.spam_score = result.score
                    spam_features.spam_score_confidence = result.confidence
            uow.commit()

        log.info('Spam scoring complete for %s: score=%.3f, risk=%s, confidence=%.2f, reasons=%d',
                 username, result.score, result.risk_level, result.confidence, len(result.reasons))

        if result.risk_level in ('HIGH', 'CRITICAL'):
            log.info('High-risk user detected: %s (score=%.3f, risk=%s) - reasons: %s',
                     username, result.score, result.risk_level, ', '.join(result.reasons[:3]))

        return result.to_dict()

    except Exception as e:
        log.error('Error scoring user %s: %s', username, str(e), exc_info=True)
        raise


@celery.task(bind=True, base=SpamDetectionTask, ignore_results=False, serializer='pickle')
def rescore_user_with_tier2(self, username: str) -> Optional[dict]:
    """
    Re-score a user using both Tier 1 and Tier 2 features.

    This should be called after Tier 2 enrichment to produce
    an enhanced spam score incorporating API-sourced data.

    Args:
        username: Reddit username to re-score

    Returns:
        Dict with enhanced scoring results or None if insufficient data
    """
    from redditrepostsleuth.core.services.spam.spam_feature_extractor import SpamFeatureExtractor
    from redditrepostsleuth.core.services.spam.spam_scorer import SpamScorerWithTier2
    from redditrepostsleuth.core.db.databasemodels import UserReview

    if not username or username == '[deleted]':
        log.debug('Skipping Tier 2 re-scoring for invalid username: %s', username)
        return None

    log.info('Starting Tier 2 re-scoring for user: %s', username)

    try:
        # Extract Tier 1 features
        extractor = SpamFeatureExtractor(self.uowm)
        tier1_features = extractor.extract_tier1_features(username)

        if not tier1_features:
            log.warning('No Tier 1 features for %s, cannot re-score', username)
            return None

        # Get Tier 2 features from database
        with self.uowm.start() as uow:
            spam_features = uow.spam_features.get_by_username(username)

            if not spam_features or not spam_features.tier2_enriched_at:
                log.warning('No Tier 2 data for %s, cannot re-score', username)
                return None

            # Build Tier 2 dict from stored features
            tier2_data = {
                'account_age_days': spam_features.account_age_days,
                'total_karma': spam_features.total_karma,
                'post_karma': spam_features.post_karma,
                'comment_karma': spam_features.comment_karma,
                'karma_per_day': spam_features.karma_per_day,
                'has_verified_email': spam_features.has_verified_email,
                'is_gold': spam_features.is_gold,
                'has_custom_avatar': spam_features.has_custom_avatar,
                'account_suspended': spam_features.account_suspended,
                'has_adult_profile_links': spam_features.has_adult_profile_links,
                'has_telegram_links': spam_features.has_telegram_links,
                'profile_link_sources': spam_features.profile_link_sources,
                'has_promotional_post_links': spam_features.has_promotional_post_links,
            }

        # Score with both tiers
        scorer = SpamScorerWithTier2(self.uowm)
        result = scorer.score_with_tier2(tier1_features, tier2_data)

        log.info('Tier 2 re-scoring complete for %s: score=%.3f (was Tier1 only), risk=%s',
                 username, result.score, result.risk_level)

        # Update user_review table with enhanced score
        with self.uowm.start() as uow:
            review = uow.user_review.get_by_username(username)

            if review:
                review.spam_score = result.score
                review.spam_score_confidence = result.confidence
                review.spam_score_updated_at = datetime.utcnow()
                review.risk_level = result.risk_level
            else:
                review = UserReview(
                    username=username,
                    spam_score=result.score,
                    spam_score_confidence=result.confidence,
                    spam_score_updated_at=datetime.utcnow(),
                    risk_level=result.risk_level,
                )
                uow.user_review.add(review)

            uow.commit()

        # Also update spam_features table
        with self.uowm.start() as uow:
            spam_features = uow.spam_features.get_by_username(username)
            if spam_features:
                spam_features.spam_score = result.score
                spam_features.spam_score_confidence = result.confidence
                spam_features.computed_at = datetime.utcnow()
                # Update feature_data with Tier 2 scoring info
                feature_dict = tier1_features.to_dict()
                feature_dict['rule_score'] = result.score
                feature_dict['risk_level'] = result.risk_level
                feature_dict['top_contributing_factors'] = result.reasons
                feature_dict['tier2_enhanced'] = True
                spam_features.feature_data = feature_dict
            uow.commit()

        return result.to_dict()

    except Exception as e:
        log.error('Error re-scoring user %s with Tier 2: %s', username, str(e), exc_info=True)
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
        log.debug('Skipping score_and_flag for invalid username: %s', username)
        return None

    log.info('Starting score_and_flag task for user: %s (update_review=%s)',
             username, update_user_review)

    # Score the user (calls the task directly, not async)
    result_dict = score_user_spam(username)

    if not result_dict:
        log.info('No scoring result for %s (insufficient data)', username)
        return None

    reasons = result_dict.get('reasons', [])
    log.debug('Scoring result for %s: score=%.3f, risk=%s, reasons=%s',
              username, result_dict['score'], result_dict['risk_level'],
              ', '.join(reasons) if reasons else 'none')

    # Update user_review if requested
    if update_user_review:
        log.debug('Updating user_review table for %s', username)
        with self.uowm.start() as uow:
            review = uow.user_review.get_by_username(username)

            if review:
                # Update existing review
                log.debug('Updating existing user_review record for %s', username)
                review.spam_score = result_dict['score']
                review.spam_score_confidence = result_dict['confidence']
                review.spam_score_updated_at = datetime.utcnow()
                review.risk_level = result_dict['risk_level']
            else:
                # Create new review entry
                log.debug('Creating new user_review record for %s', username)
                review = UserReview(
                    username=username,
                    spam_score=result_dict['score'],
                    spam_score_confidence=result_dict['confidence'],
                    spam_score_updated_at=datetime.utcnow(),
                    risk_level=result_dict['risk_level'],
                )
                uow.user_review.add(review)

            uow.commit()

        log.info('Updated user_review for %s: score=%.3f, risk=%s',
                 username, result_dict['score'], result_dict['risk_level'])
    else:
        log.debug('Skipping user_review update for %s (disabled)', username)

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
    log.info('Starting batch scoring for %d users', len(usernames))

    results = {
        'total': len(usernames),
        'scored': 0,
        'skipped': 0,
        'failed': 0,
        'high_risk': 0,
        'critical_risk': 0,
    }

    for i, username in enumerate(usernames):
        if not username or username == '[deleted]':
            log.debug('Skipping invalid username at index %d: %s', i, username)
            results['skipped'] += 1
            continue

        try:
            log.debug('Scoring user %d/%d: %s', i + 1, len(usernames), username)
            result = score_and_flag_user(username, update_user_review=True)

            if result:
                results['scored'] += 1
                if result['risk_level'] == 'CRITICAL':
                    results['critical_risk'] += 1
                    log.info('CRITICAL risk user found: %s (score=%.2f)', username, result['score'])
                elif result['risk_level'] == 'HIGH':
                    results['high_risk'] += 1
                    log.info('HIGH risk user found: %s (score=%.2f)', username, result['score'])
                else:
                    log.debug('Scored user %s: score=%.2f, risk=%s',
                              username, result['score'], result['risk_level'])
            else:
                results['skipped'] += 1
                log.debug('Skipped user %s (insufficient data)', username)

        except Exception as e:
            log.error('Failed to score user %s: %s', username, str(e), exc_info=True)
            results['failed'] += 1

        # Log progress every 10 users
        if (i + 1) % 10 == 0:
            log.info('Batch scoring progress: %d/%d users processed (scored=%d, skipped=%d, failed=%d)',
                     i + 1, len(usernames), results['scored'], results['skipped'], results['failed'])

    log.info('Batch scoring complete: total=%d, scored=%d, skipped=%d, failed=%d, high_risk=%d, critical=%d',
             results['total'], results['scored'], results['skipped'], results['failed'],
             results['high_risk'], results['critical_risk'])
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

    log.info('Starting score_top_reposters: limit=%d, days=%d, min_reposts=%d',
             limit, days, min_reposts)

    usernames_to_score = []

    log.debug('Querying top reposters from database')
    with self.uowm.start() as uow:
        cutoff = datetime.utcnow() - timedelta(days=days)
        log.debug('Cutoff date for repost query: %s', cutoff)

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
                log.debug('Top reposter: %s (%d reposts)', row.author, row.repost_count)

    log.info('Found %d top reposters with >= %d reposts in last %d days',
             len(usernames_to_score), min_reposts, days)

    if not usernames_to_score:
        log.info('No top reposters found matching criteria')
        return {'analyzed': 0, 'total': 0}

    # Filter out recently analyzed users
    log.debug('Filtering out recently scored users')
    users_needing_scoring = []
    with self.uowm.start() as uow:
        for username in usernames_to_score:
            features = uow.spam_features.get_by_username(username)
            if not features or not features.spam_score:
                log.debug('User %s has no score, will be scored', username)
                users_needing_scoring.append(username)
            elif features.computed_at:
                # Re-score if older than 7 days
                age = datetime.utcnow() - features.computed_at
                if age.days > 7:
                    log.debug('User %s has stale score (%d days old), will be re-scored',
                              username, age.days)
                    users_needing_scoring.append(username)
                else:
                    log.debug('User %s already scored recently (%d days ago), skipping',
                              username, age.days)

    log.info('Filtered to %d users needing scoring (out of %d top reposters)',
             len(users_needing_scoring), len(usernames_to_score))

    if not users_needing_scoring:
        log.info('All top reposters already have recent scores')
        return {'analyzed': 0, 'total': len(usernames_to_score), 'message': 'All already scored'}

    log.info('Starting batch scoring for %d top reposters', len(users_needing_scoring))
    return batch_score_users(users_needing_scoring)


# ============================================================================
# Scheduled Task Wrappers (for Celery Beat)
# ============================================================================


@celery.task(bind=True, base=SpamDetectionTask, ignore_results=True, serializer='pickle')
def scheduled_analyze_top_reposters(self) -> dict:
    """
    Scheduled task wrapper for analyzing top reposters.

    Runs daily to score users with high repost activity.
    Default: limit=100, days=7, min_reposts=3

    Returns:
        Dict with analysis results
    """
    log.info('Starting scheduled_analyze_top_reposters task')
    try:
        result = score_top_reposters(limit=100, days=7, min_reposts=3)
        log.info('scheduled_analyze_top_reposters completed: %s', result)
        return result
    except Exception as e:
        log.error('scheduled_analyze_top_reposters failed: %s', str(e), exc_info=True)
        raise


@celery.task(bind=True, base=SpamDetectionTaskWithReddit, ignore_results=True, serializer='pickle')
def scheduled_enrich_high_risk(self) -> dict:
    """
    Scheduled task wrapper for enriching high-risk users with Tier 2 data.

    Runs daily to fetch Reddit API data for high-risk users.
    Default: min_score=0.5, limit=50

    Returns:
        Dict with enrichment results
    """
    log.info('Starting scheduled_enrich_high_risk task')
    try:
        result = enrich_high_risk_users(min_score=0.5, limit=50)
        log.info('scheduled_enrich_high_risk completed: %s', result)
        return result
    except Exception as e:
        log.error('scheduled_enrich_high_risk failed: %s', str(e), exc_info=True)
        raise


@celery.task(bind=True, base=SpamDetectionTask, ignore_results=True, serializer='pickle')
def scheduled_cleanup_features(self) -> dict:
    """
    Scheduled task wrapper for cleaning up old feature records.

    Runs weekly to remove stale feature records.
    Default: keep_per_user=5

    Returns:
        Dict with cleanup results
    """
    log.info('Starting scheduled_cleanup_features task')
    try:
        result = cleanup_old_feature_records(keep_per_user=5)
        log.info('scheduled_cleanup_features completed: %s', result)
        return result
    except Exception as e:
        log.error('scheduled_cleanup_features failed: %s', str(e), exc_info=True)
        raise


@celery.task(bind=True, base=SpamDetectionTask, ignore_results=True, serializer='pickle')
def scheduled_purge_activity_tracking(self) -> dict:
    """
    Scheduled task wrapper for purging old author activity tracking records.

    Runs weekly to delete activity records older than 180 days.
    This helps manage database size while retaining recent data.

    Returns:
        Dict with purge results
    """
    log.info('Starting scheduled_purge_activity_tracking task')
    try:
        cutoff = datetime.utcnow() - timedelta(days=180)

        with self.uowm.start() as uow:
            deleted_count = uow.author_activity.delete_older_than(cutoff)
            uow.commit()

        result = {'deleted_count': deleted_count, 'cutoff_date': cutoff.isoformat()}
        log.info('scheduled_purge_activity_tracking completed: deleted %d records older than %s',
                 deleted_count, cutoff.isoformat())
        return result
    except Exception as e:
        log.error('scheduled_purge_activity_tracking failed: %s', str(e), exc_info=True)
        raise


# ============================================================================
# Moderator API Support Tasks
# ============================================================================


@celery.task(
    bind=True,
    base=SpamDetectionTaskWithReddit,
    ignore_results=False,
    serializer='pickle',
    autoretry_for=(Exception,),
    retry_kwargs={'max_retries': 3, 'countdown': 60}
)
def scan_user_full(self, username: str) -> Optional[dict]:
    """
    Perform full user scan (Tier 1 + Tier 2) synchronously.

    Used by moderator API to trigger a complete scan when a user
    has incomplete data. Returns the final features for the frontend.

    Args:
        username: Reddit username to scan

    Returns:
        Dict with spam features via to_dict_for_moderator(), or None on failure
    """
    if not username or username == '[deleted]':
        log.debug('Skipping full scan for invalid username: %s', username)
        return None

    log.info('Starting full user scan for moderator API: %s', username)

    try:
        # Step 1: Run Tier 1 feature extraction synchronously
        log.info('Running Tier 1 feature extraction for %s', username)
        tier1_result = compute_user_spam_features_tier1(username)

        if not tier1_result:
            log.warning('Tier 1 extraction failed for %s (insufficient data)', username)
            return None

        # Step 2: Run Tier 2 enrichment synchronously
        log.info('Running Tier 2 enrichment for %s', username)
        tier2_result = enrich_user_features_tier2(username)

        if not tier2_result:
            log.warning('Tier 2 enrichment failed for %s', username)
            # Continue anyway - Tier 1 data is still available

        # Step 3: Fetch final features and return via to_dict_for_moderator()
        with self.uowm.start() as uow:
            features = uow.spam_features.get_by_username(username)
            if features:
                log.info('Full scan complete for %s: score=%.3f, tier2_enriched=%s',
                         username, features.spam_score or 0,
                         features.tier2_enriched_at is not None)
                return features.to_dict_for_moderator()
            else:
                log.warning('No features found after full scan for %s', username)
                return None

    except Exception as e:
        log.error('Error during full scan for %s: %s', username, str(e), exc_info=True)
        raise
