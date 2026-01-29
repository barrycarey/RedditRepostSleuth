"""
User Data Fetcher Service

Fetches user data from Reddit API with rate limiting and circuit breaker protection.
Handles suspended/deleted users gracefully and scans profiles for adult/Telegram links.
"""
import logging
import re
import time
from datetime import datetime
from typing import List, Optional

from praw import Reddit
from praw.exceptions import RedditAPIException
from prawcore.exceptions import Forbidden, NotFound, TooManyRequests

from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.core.services.spam.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerOpen,
)
from redditrepostsleuth.core.services.spam.rate_limiter import (
    PerMinuteRateLimiter,
    RateLimitExceeded,
)
from redditrepostsleuth.core.services.spam.tier2_features import Tier2Features

log = logging.getLogger(__name__)


# Telegram link patterns for detection
TELEGRAM_PATTERNS = [
    r't\.me/',
    r'telegram\.me/',
    r'telegram\.org/',
]
_telegram_pattern = re.compile('|'.join(TELEGRAM_PATTERNS), re.IGNORECASE)


# Adult platform patterns (reuse from spam_detection_tasks but add profile-specific ones)
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
_adult_pattern = re.compile('|'.join(ADULT_PLATFORM_PATTERNS), re.IGNORECASE)


# Map patterns to platform names for detection
ADULT_PLATFORM_NAMES = {
    r'onlyfans\.com': 'onlyfans',
    r'fansly\.com': 'fansly',
    r'fancentro\.com': 'fancentro',
    r'manyvids\.com': 'manyvids',
    r'pornhub\.com': 'pornhub',
    r'xvideos\.com': 'xvideos',
    r'chaturbate\.com': 'chaturbate',
    r'myfreecams\.com': 'myfreecams',
    r'stripchat\.com': 'stripchat',
    r'cam4\.com': 'cam4',
    r'bongacams\.com': 'bongacams',
    r'livejasmin\.com': 'livejasmin',
    r'streamate\.com': 'streamate',
    r'camsoda\.com': 'camsoda',
    r'loyalfans\.com': 'loyalfans',
    r'admireme\.vip': 'admireme',
    r'frisk\.chat': 'frisk',
}


# Promotional platform patterns (link shorteners, e-commerce, monetization)
PROMOTIONAL_PLATFORM_PATTERNS = [
    # Link aggregators/shorteners
    r'bit\.ly/',
    r'tinyurl\.com/',
    r'linktr\.ee/',
    r'beacons\.ai/',
    r'allmylinks\.com/',
    r'linkin\.bio/',
    # E-commerce/self-promotion
    r'etsy\.com/shop/',
    r'redbubble\.com/',
    r'gumroad\.com/',
    r'ko-fi\.com/',
    r'buymeacoffee\.com/',
    r'patreon\.com/',
    r'throne\.com/',
    # Off-platform messaging
    r'discord\.gg/',
    r'discord\.com/invite/',
    # Monetization/tips
    r'cash\.app/',
    r'paypal\.me/',
    r'venmo\.com/',
]
_promotional_pattern = re.compile('|'.join(PROMOTIONAL_PLATFORM_PATTERNS), re.IGNORECASE)


def detect_telegram_link(text: Optional[str]) -> bool:
    """Check if text contains a Telegram link."""
    if not text:
        return False
    return bool(_telegram_pattern.search(text))


def detect_adult_platform_link(text: Optional[str]) -> bool:
    """Check if text contains an adult platform link."""
    if not text:
        return False
    return bool(_adult_pattern.search(text))


def detect_adult_platform_names(text: Optional[str]) -> List[str]:
    """Detect which adult platforms are linked in text.

    Returns list of unique platform names found (e.g., ['onlyfans', 'fansly'])
    """
    if not text:
        return []
    found = []
    for pattern, name in ADULT_PLATFORM_NAMES.items():
        if re.search(pattern, text, re.IGNORECASE) and name not in found:
            found.append(name)
    return found


def detect_promotional_link(text: Optional[str]) -> bool:
    """Check if text contains a promotional platform link."""
    if not text:
        return False
    return bool(_promotional_pattern.search(text))


class UserDataFetcher:
    """
    Fetches user data from Reddit API with rate limiting and circuit breaker.

    This service enforces rate limiting to avoid 429 errors and
    handles various error conditions gracefully.
    """

    # Default avatars contain these substrings
    DEFAULT_AVATAR_INDICATORS = [
        'snoomoji',
        'snoovatar_default',
        'default_icon',
        'avatar_default',
        'snoovatar-img',
    ]

    def __init__(
        self,
        reddit: Reddit,
        uowm: UnitOfWorkManager,
        circuit_breaker: Optional[CircuitBreaker] = None,
        rate_limiter: Optional[PerMinuteRateLimiter] = None,
        min_interval: float = 1.5,
        max_retries: int = 3
    ):
        """
        Initialize the user data fetcher.

        Args:
            reddit: PRAW Reddit instance
            uowm: Unit of Work Manager for database access
            circuit_breaker: Optional circuit breaker instance
            rate_limiter: Optional rate limiter instance
            min_interval: Minimum seconds between API calls (default 1.5)
            max_retries: Maximum retries on transient failures
        """
        self.reddit = reddit
        self.uowm = uowm
        self.circuit_breaker = circuit_breaker or CircuitBreaker()
        self.rate_limiter = rate_limiter
        self.min_interval = min_interval
        self.max_retries = max_retries

        self._last_fetch_time: datetime = datetime.min
        self._consecutive_errors: int = 0

    def _enforce_rate_limit(self) -> None:
        """
        Enforce minimum interval between API calls.

        Also implements exponential backoff when consecutive errors occur.
        """
        now = datetime.utcnow()
        elapsed = (now - self._last_fetch_time).total_seconds()

        # Calculate required wait time
        base_wait = self.min_interval

        # Add exponential backoff if we've had errors
        if self._consecutive_errors > 0:
            backoff = min(60, base_wait * (2 ** self._consecutive_errors))
            base_wait = backoff
            log.debug(f"Applying backoff: {backoff}s due to {self._consecutive_errors} errors")

        if elapsed < base_wait:
            sleep_time = base_wait - elapsed
            log.debug(f"Rate limiting: sleeping {sleep_time:.2f}s")
            time.sleep(sleep_time)

        self._last_fetch_time = datetime.utcnow()

        # Also check per-minute rate limiter if available
        if self.rate_limiter:
            self.rate_limiter.wait_if_needed()

    def _is_default_avatar(self, icon_url: str) -> bool:
        """
        Check if user has default avatar.

        Args:
            icon_url: URL of user's icon image

        Returns:
            True if avatar appears to be a default
        """
        if not icon_url:
            return True

        icon_lower = icon_url.lower()
        return any(indicator in icon_lower for indicator in self.DEFAULT_AVATAR_INDICATORS)

    def fetch_basic_user_data(self, username: str) -> Optional[Tier2Features]:
        """
        Fetch basic redditor data (single API call).

        This fetches the redditor object which includes account age,
        karma, verification status, etc.

        Args:
            username: Reddit username to fetch

        Returns:
            Tier2Features or None if fetch failed

        Raises:
            RateLimitExceeded: If rate limit hit, caller should retry
            CircuitBreakerOpen: If circuit breaker is open
        """
        # Check circuit breaker first
        if self.circuit_breaker.is_open:
            if not self.circuit_breaker._should_attempt_reset():
                raise CircuitBreakerOpen(
                    f"Circuit breaker is OPEN for user data fetcher",
                    retry_after=self.circuit_breaker._time_until_retry()
                )

        self._enforce_rate_limit()

        log.debug(f"Fetching user data for: {username}")

        try:
            redditor = self.reddit.redditor(username)

            # Force fetch by accessing an attribute
            # This is where the actual API call happens
            created_utc = redditor.created_utc

            # Calculate account age
            created_dt = datetime.fromtimestamp(created_utc)
            account_age_days = (datetime.utcnow() - created_dt).days

            # Build features
            features = Tier2Features(
                account_age_days=account_age_days,
                total_karma=getattr(redditor, 'total_karma', 0),
                post_karma=getattr(redditor, 'link_karma', 0),
                comment_karma=getattr(redditor, 'comment_karma', 0),
                karma_per_day=getattr(redditor, 'total_karma', 0) / max(1, account_age_days),
                has_verified_email=getattr(redditor, 'has_verified_email', False),
                is_gold=getattr(redditor, 'is_gold', False),
                has_custom_avatar=not self._is_default_avatar(
                    getattr(redditor, 'icon_img', '')
                ),
                is_mod=False,  # Checking moderated() is another API call
                account_suspended=False,
                fetched_at=datetime.utcnow(),
                fetch_success=True,
            )

            # Reset error counter on success
            self._consecutive_errors = 0
            self.circuit_breaker.record_success()

            log.debug(f"Successfully fetched data for {username}")
            return features

        except NotFound:
            # User doesn't exist or is shadowbanned
            log.info(f"User not found (deleted/shadowbanned): {username}")
            self._consecutive_errors = 0
            self.circuit_breaker.record_success()  # Not an API failure
            return Tier2Features.suspended_user(username, "User not found (deleted or shadowbanned)")

        except Forbidden:
            # User is suspended
            log.info(f"User suspended (403 Forbidden): {username}")
            self._consecutive_errors = 0
            self.circuit_breaker.record_success()  # Not an API failure
            return Tier2Features.suspended_user(username, "User suspended by Reddit")

        except TooManyRequests as e:
            # Rate limited - need to back off
            self._consecutive_errors += 1
            self.circuit_breaker.record_failure(e)
            retry_after = getattr(e, 'retry_after', 60) or 60

            log.warning(f"Rate limited fetching {username}, retry after {retry_after}s")
            raise RateLimitExceeded(retry_after=retry_after)

        except RedditAPIException as e:
            # Other Reddit API errors
            self._consecutive_errors += 1
            self.circuit_breaker.record_failure(e)
            log.error(f"Reddit API error for {username}: {e}")
            return None

        except Exception as e:
            # Unexpected errors
            self._consecutive_errors += 1
            self.circuit_breaker.record_failure(e)
            log.error(f"Unexpected error fetching {username}: {e}", exc_info=True)
            return None

    def scan_user_profile_links(self, username: str) -> dict:
        """
        Scan user's profile and recent comments for adult/Telegram links.

        This requires additional API calls beyond the basic user data.

        Args:
            username: Reddit username to scan

        Returns:
            Dict with 'has_adult_links', 'has_telegram_links', 'sources', 'detected_platforms'
        """
        self._enforce_rate_limit()

        result = {
            'has_adult_links': False,
            'has_telegram_links': False,
            'sources': {},
            'detected_platforms': [],
        }

        try:
            redditor = self.reddit.redditor(username)

            # Check profile description (subreddit description if user has one)
            try:
                subreddit = redditor.subreddit
                if subreddit:
                    public_description = getattr(subreddit, 'public_description', '') or ''
                    if detect_adult_platform_link(public_description):
                        result['has_adult_links'] = True
                        result['sources'].setdefault('profile', []).append('public_description')
                        # Extract platform names
                        platforms = detect_adult_platform_names(public_description)
                        for p in platforms:
                            if p not in result['detected_platforms']:
                                result['detected_platforms'].append(p)
                    if detect_telegram_link(public_description):
                        result['has_telegram_links'] = True
                        result['sources'].setdefault('telegram', []).append('public_description')
            except Exception as e:
                log.debug(f"Could not check profile for {username}: {e}")

            # Check recent comments (limited to 10 to conserve API calls)
            self._enforce_rate_limit()
            try:
                for i, comment in enumerate(redditor.comments.new(limit=100)):
                    if i >= 10:
                        break
                    body = getattr(comment, 'body', '')
                    if detect_adult_platform_link(body):
                        result['has_adult_links'] = True
                        result['sources'].setdefault('comments', []).append(comment.id)
                        # Extract platform names
                        platforms = detect_adult_platform_names(body)
                        for p in platforms:
                            if p not in result['detected_platforms']:
                                result['detected_platforms'].append(p)
                    if detect_telegram_link(body):
                        result['has_telegram_links'] = True
                        result['sources'].setdefault('telegram_comments', []).append(comment.id)
            except Exception as e:
                log.debug(f"Could not check comments for {username}: {e}")

            self._consecutive_errors = 0
            self.circuit_breaker.record_success()

        except (NotFound, Forbidden):
            # User suspended/deleted
            log.debug(f"User {username} not accessible for profile scan")

        except TooManyRequests as e:
            self._consecutive_errors += 1
            self.circuit_breaker.record_failure(e)
            raise RateLimitExceeded(retry_after=getattr(e, 'retry_after', 60))

        except Exception as e:
            self._consecutive_errors += 1
            self.circuit_breaker.record_failure(e)
            log.error(f"Error scanning profile for {username}: {e}")

        return result

    def scan_user_posts(self, username: str, limit: int = 100) -> dict:
        """
        Scan user's recent posts for adult/Telegram/promotional links.

        Scans post title, selftext, and url for each submission.

        Args:
            username: Reddit username to scan
            limit: Maximum number of posts to scan (default 100, PRAW max)

        Returns:
            Dict with 'has_adult_links', 'has_telegram_links',
            'has_promotional_links', 'sources', 'detected_platforms'
        """
        self._enforce_rate_limit()

        result = {
            'has_adult_links': False,
            'has_telegram_links': False,
            'has_promotional_links': False,
            'sources': {},
            'detected_platforms': [],
        }

        try:
            redditor = self.reddit.redditor(username)

            # Scan recent posts (submissions)
            for submission in redditor.submissions.new(limit=limit):
                post_id = submission.id

                # Combine title, selftext, and url for scanning
                texts_to_scan = [
                    getattr(submission, 'title', '') or '',
                    getattr(submission, 'selftext', '') or '',
                    getattr(submission, 'url', '') or '',
                ]
                combined_text = ' '.join(texts_to_scan)

                # Check for adult links
                if detect_adult_platform_link(combined_text):
                    result['has_adult_links'] = True
                    result['sources'].setdefault('adult_posts', []).append(post_id)
                    # Extract platform names
                    platforms = detect_adult_platform_names(combined_text)
                    for p in platforms:
                        if p not in result['detected_platforms']:
                            result['detected_platforms'].append(p)

                # Check for Telegram links
                if detect_telegram_link(combined_text):
                    result['has_telegram_links'] = True
                    result['sources'].setdefault('telegram_posts', []).append(post_id)

                # Check for promotional links
                if detect_promotional_link(combined_text):
                    result['has_promotional_links'] = True
                    result['sources'].setdefault('promotional_posts', []).append(post_id)

            self._consecutive_errors = 0
            self.circuit_breaker.record_success()

        except (NotFound, Forbidden):
            # User suspended/deleted
            log.debug(f"User {username} not accessible for post scan")

        except TooManyRequests as e:
            self._consecutive_errors += 1
            self.circuit_breaker.record_failure(e)
            raise RateLimitExceeded(retry_after=getattr(e, 'retry_after', 60))

        except Exception as e:
            self._consecutive_errors += 1
            self.circuit_breaker.record_failure(e)
            log.error(f"Error scanning posts for {username}: {e}")

        return result

    def check_user_suspended(self, username: str) -> bool:
        """
        Quick check if a user is suspended.

        Useful for training data collection - suspended users are
        confirmed spam.

        Args:
            username: Reddit username

        Returns:
            True if user is suspended/deleted, False otherwise
        """
        self._enforce_rate_limit()

        try:
            redditor = self.reddit.redditor(username)
            _ = redditor.created_utc  # Force fetch
            self._consecutive_errors = 0
            self.circuit_breaker.record_success()
            return False

        except (NotFound, Forbidden):
            self._consecutive_errors = 0
            self.circuit_breaker.record_success()
            return True

        except TooManyRequests as e:
            self._consecutive_errors += 1
            self.circuit_breaker.record_failure(e)
            raise RateLimitExceeded(retry_after=getattr(e, 'retry_after', 60))

        except Exception as e:
            self._consecutive_errors += 1
            self.circuit_breaker.record_failure(e)
            log.error(f"Error checking suspension for {username}: {e}")
            raise

    def fetch_and_enrich(self, username: str, scan_profile: bool = False, scan_posts: bool = False) -> Optional[Tier2Features]:
        """
        Complete Tier 2 enrichment: fetch user data and optionally scan profile/posts.

        Args:
            username: Reddit username
            scan_profile: Whether to scan profile for adult/Telegram links
            scan_posts: Whether to scan posts for adult/Telegram/promotional links

        Returns:
            Tier2Features with all available data, or None on failure
        """
        # Fetch basic data first
        features = self.fetch_basic_user_data(username)

        if not features:
            return None

        # If user is suspended, no need to scan profile or posts
        if features.account_suspended:
            return features

        # Optionally scan profile for links
        if scan_profile:
            try:
                profile_scan = self.scan_user_profile_links(username)
                features.has_adult_profile_links = profile_scan['has_adult_links']
                features.has_telegram_links = profile_scan['has_telegram_links']
                features.profile_link_sources = profile_scan['sources']
                # Collect detected platforms from profile scan
                for p in profile_scan.get('detected_platforms', []):
                    if p not in features.detected_platforms:
                        features.detected_platforms.append(p)
            except RateLimitExceeded:
                # Don't fail the whole enrichment, just skip profile scan
                log.warning(f"Rate limited during profile scan for {username}, skipping")

        # Optionally scan posts for links
        if scan_posts:
            try:
                post_scan = self.scan_user_posts(username)

                # Merge adult links from posts (OR with profile results)
                if post_scan['has_adult_links']:
                    features.has_adult_profile_links = True

                # Merge telegram links from posts (OR with profile results)
                if post_scan['has_telegram_links']:
                    features.has_telegram_links = True

                # Promotional links from posts (new field)
                features.has_promotional_post_links = post_scan['has_promotional_links']

                # Merge post sources into profile_link_sources
                if not features.profile_link_sources:
                    features.profile_link_sources = {}

                for key, value in post_scan['sources'].items():
                    features.profile_link_sources[key] = value

                # Merge detected platforms from post scan
                for p in post_scan.get('detected_platforms', []):
                    if p not in features.detected_platforms:
                        features.detected_platforms.append(p)

            except RateLimitExceeded:
                # Don't fail the whole enrichment, just skip post scan
                log.warning(f"Rate limited during post scan for {username}, skipping")

        return features

    def batch_fetch_users(
        self,
        usernames: List[str],
        on_progress: callable = None
    ) -> dict:
        """
        Fetch data for multiple users with rate limiting.

        Args:
            usernames: List of usernames to fetch
            on_progress: Optional callback(username, index, total)

        Returns:
            Dict mapping username to Tier2Features or None
        """
        results = {}
        total = len(usernames)

        for i, username in enumerate(usernames):
            try:
                if on_progress:
                    on_progress(username, i, total)

                results[username] = self.fetch_basic_user_data(username)

            except RateLimitExceeded as e:
                log.warning(f"Rate limit hit at user {i}/{total}, pausing {e.retry_after}s")
                time.sleep(e.retry_after)

                # Retry this user
                try:
                    results[username] = self.fetch_basic_user_data(username)
                except RateLimitExceeded:
                    log.error(f"Still rate limited after pause, skipping {username}")
                    results[username] = None

            except CircuitBreakerOpen as e:
                log.warning(f"Circuit breaker open, pausing {e.retry_after}s")
                time.sleep(e.retry_after)
                # Try to continue with remaining users
                results[username] = None

            except Exception as e:
                log.error(f"Failed to fetch {username}: {e}")
                results[username] = None

        return results


class CachedUserDataFetcher(UserDataFetcher):
    """
    User data fetcher with database caching layer.

    Checks database for recent data before making API calls.
    """

    def __init__(
        self,
        reddit: Reddit,
        uowm: UnitOfWorkManager,
        cache_ttl_hours: int = 24,
        **kwargs
    ):
        """
        Initialize the cached user data fetcher.

        Args:
            reddit: PRAW Reddit instance
            uowm: Unit of Work Manager
            cache_ttl_hours: Hours before cached data is considered stale
            **kwargs: Additional arguments for parent class
        """
        super().__init__(reddit, uowm, **kwargs)
        self.cache_ttl_hours = cache_ttl_hours

    def fetch_basic_user_data(self, username: str) -> Optional[Tier2Features]:
        """
        Fetch user data with caching.

        Checks database for recent data before making API call.
        """
        # Check cache (database)
        with self.uowm.start() as uow:
            cached = uow.spam_features.get_by_username(username)

            if cached and cached.account_age_days is not None:
                # Check if cache is fresh
                if cached.tier2_enriched_at:
                    cache_age_hours = (
                        datetime.utcnow() - cached.tier2_enriched_at
                    ).total_seconds() / 3600

                    if cache_age_hours < self.cache_ttl_hours:
                        log.debug(f"Using cached data for {username}")
                        return Tier2Features(
                            account_age_days=cached.account_age_days,
                            total_karma=cached.total_karma or 0,
                            post_karma=cached.post_karma or 0,
                            comment_karma=cached.comment_karma or 0,
                            karma_per_day=cached.karma_per_day or 0.0,
                            has_verified_email=cached.has_verified_email or False,
                            is_gold=cached.is_gold or False,
                            has_custom_avatar=cached.has_custom_avatar or False,
                            is_mod=False,
                            account_suspended=cached.account_suspended or False,
                            has_adult_profile_links=cached.has_adult_profile_links or False,
                            has_telegram_links=cached.has_telegram_links or False,
                            profile_link_sources=cached.profile_link_sources or {},
                            has_promotional_post_links=cached.has_promotional_post_links or False,
                            fetched_at=cached.tier2_enriched_at,
                            fetch_success=True,
                        )

        # Cache miss - fetch from API
        return super().fetch_basic_user_data(username)
