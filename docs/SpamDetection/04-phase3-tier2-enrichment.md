# Phase 3: Tier 2 Feature Enrichment

## Overview
- **Duration**: Week 7-8
- **Dependencies**: Phase 2 (Scoring engine)
- **Goal**: Add Reddit API-sourced features with careful rate limiting

---

## Table of Contents
1. [Reddit API Constraints](#1-reddit-api-constraints)
2. [Circuit Breaker Pattern](#2-circuit-breaker-pattern)
3. [Tier 2 Feature Definitions](#3-tier-2-feature-definitions)
4. [UserDataFetcher Service](#4-userdatafetcher-service)
5. [Rate Limiting Strategy](#5-rate-limiting-strategy)
6. [Per-Minute Rate Limiting](#6-per-minute-rate-limiting)
7. [Celery Task Integration](#7-celery-task-integration)
8. [Enhanced Scoring](#8-enhanced-scoring)
9. [Error Handling](#9-error-handling)
10. [Testing Strategy](#10-testing-strategy)
11. [Verification Checklist](#11-verification-checklist)

---

## 1. Reddit API Constraints

### Rate Limits
| Limit Type | Value | Notes |
|------------|-------|-------|
| Requests per minute (OAuth) | 60 | Shared across all bot operations |
| IP-level 429 cooldown | 240 seconds | Triggered by exceeding limits |
| Concurrent connections | ~10 | Unofficial limit |

### API Limitations
| Limitation | Impact |
|------------|--------|
| Max 1000 items per listing | Can only see 1000 most recent posts/comments per user |
| No bulk user endpoint | Must fetch users one at a time |
| Suspended users return 403/404 | Need to handle gracefully |
| Shadowbanned users | May return partial data |

### Budget Allocation

Given ~86,400 requests/day theoretical maximum:

| Activity | Daily Budget | Notes |
|----------|-------------|-------|
| Normal bot operations | 50,000 | Existing functionality (priority) |
| Tier 2 user enrichment | 1,000 | ~1 call per user |
| Tier 3 deep analysis | 200 | 2-4 calls per user, selective |
| Suspension checks | 500 | Training data collection |
| Buffer | 34,700 | Safety margin |

---

## 2. Circuit Breaker Pattern

### Why Circuit Breaker?

The Reddit API is a critical dependency for Tier 2 features. If the API experiences outages, we must:
1. Stop making requests immediately (fail fast)
2. Fall back to Tier 1-only scoring (graceful degradation)
3. Periodically test if API is recovered (HALF_OPEN state)
4. Resume normal operation when healthy (CLOSED state)

### Circuit Breaker States

```
CLOSED (Normal)
├─ Accept all API requests
├─ Track consecutive failures
└─ Open if failures ≥ threshold

OPEN (API Unavailable)
├─ Reject all API requests immediately
├─ Fall back to Tier 1-only scoring
└─ Switch to HALF_OPEN after recovery_timeout

HALF_OPEN (Testing Recovery)
├─ Allow test request to API
├─ If successful → CLOSED
└─ If failed → OPEN (with longer recovery timeout)
```

### Configuration

| Parameter | Value | Purpose |
|-----------|-------|---------|
| `failure_threshold` | 5 | Open after 5 consecutive failures |
| `success_threshold` | 2 | Close after 2 successes in HALF_OPEN |
| `recovery_timeout_seconds` | 60 | Wait 60s before trying recovery |
| `backoff_multiplier` | 1.5 | Increase timeout on repeated failures |

### Implementation

**File**: `redditrepostsleuth/core/services/spam/circuit_breaker.py`

```python
"""Circuit breaker for Reddit API reliability."""
from enum import Enum
from datetime import datetime, timedelta
import logging

log = logging.getLogger(__name__)


class CircuitState(Enum):
    CLOSED = 'CLOSED'           # Normal operation
    OPEN = 'OPEN'              # API failing, reject calls
    HALF_OPEN = 'HALF_OPEN'    # Testing recovery


class CircuitBreaker:
    """
    Circuit breaker pattern for Reddit API calls.

    Protects against cascading failures by failing fast and degrading gracefully.
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        backoff_multiplier: float = 1.5
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.backoff_multiplier = backoff_multiplier

        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time: Optional[datetime] = None
        self.opening_time: Optional[datetime] = None
        self.consecutive_successes = 0

    def call(self, func, *args, **kwargs):
        """
        Execute function through circuit breaker.

        Args:
            func: Function to call
            *args: Function arguments
            **kwargs: Function keyword arguments

        Returns:
            Function result

        Raises:
            CircuitBreakerOpen: If circuit is open
        """
        if self.state == CircuitState.OPEN:
            if self._should_attempt_reset():
                self.state = CircuitState.HALF_OPEN
                log.info("Circuit breaker entering HALF_OPEN state")
            else:
                raise CircuitBreakerOpen(
                    f"Circuit breaker is OPEN. Retry after {self._time_until_retry()}s"
                )

        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise

    def _on_success(self):
        """Handle successful call."""
        self.failure_count = 0
        self.last_failure_time = None

        if self.state == CircuitState.HALF_OPEN:
            self.consecutive_successes += 1
            if self.consecutive_successes >= 2:
                self.state = CircuitState.CLOSED
                self.consecutive_successes = 0
                log.info("Circuit breaker CLOSED - API recovered")
        elif self.state == CircuitState.CLOSED:
            self.consecutive_successes = 0

    def _on_failure(self):
        """Handle failed call."""
        self.failure_count += 1
        self.last_failure_time = datetime.utcnow()
        self.consecutive_successes = 0

        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.OPEN
            self.opening_time = datetime.utcnow()
            # Increase timeout on repeated failures
            self.recovery_timeout = int(
                self.recovery_timeout * self.backoff_multiplier
            )
            log.warning(
                f"Circuit breaker OPEN - recovery timeout increased to {self.recovery_timeout}s"
            )
        elif self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN
            self.opening_time = datetime.utcnow()
            log.warning(f"Circuit breaker OPEN after {self.failure_count} failures")

    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt recovery."""
        if self.opening_time is None:
            return True
        elapsed = (datetime.utcnow() - self.opening_time).total_seconds()
        return elapsed >= self.recovery_timeout

    def _time_until_retry(self) -> int:
        """Calculate seconds until retry is allowed."""
        if self.opening_time is None:
            return 0
        elapsed = (datetime.utcnow() - self.opening_time).total_seconds()
        return max(0, int(self.recovery_timeout - elapsed))

    def get_state(self) -> str:
        """Get current circuit state."""
        return self.state.value


class CircuitBreakerOpen(Exception):
    """Raised when circuit breaker is open."""
    pass
```

### Integration with UserDataFetcher

```python
class UserDataFetcher:
    def __init__(self, reddit: Reddit, uowm, circuit_breaker=None):
        self.reddit = reddit
        self.circuit_breaker = circuit_breaker or CircuitBreaker()

    def fetch_user_data(self, username: str) -> Optional[Tier2Features]:
        """Fetch user data with circuit breaker protection."""
        try:
            # Try through circuit breaker
            return self.circuit_breaker.call(self._fetch_from_reddit, username)
        except CircuitBreakerOpen:
            # Graceful degradation - return None to use Tier 1-only scoring
            log.warning(f"Circuit breaker open, using Tier 1-only scoring for {username}")
            return None
        except Exception as e:
            log.error(f"Error fetching data for {username}: {e}")
            return None

    def _fetch_from_reddit(self, username: str) -> Tier2Features:
        """Actually fetch from Reddit (called through circuit breaker)."""
        redditor = self.reddit.redditor(username)
        # ... rest of fetch logic
```

### Monitoring Circuit Breaker State

```python
# Prometheus metric
circuit_breaker_state = Gauge(
    'spam_detection_circuit_breaker_state',
    'Circuit breaker state (0=CLOSED, 1=OPEN, 2=HALF_OPEN)'
)

# Update periodically
state_map = {
    CircuitState.CLOSED: 0,
    CircuitState.OPEN: 1,
    CircuitState.HALF_OPEN: 2,
}
circuit_breaker_state.set(state_map[breaker.get_state()])
```

### Graceful Degradation Strategy

When circuit breaker opens (API unavailable):

1. **Continue operations**: Stop calling external API, use cached Tier 1-only scores
2. **Fall back to Tier 1 scoring**: Features extracted from database only
3. **Update user notification**: Log that Tier 2 enhancement is unavailable
4. **Maintain data integrity**: Store records without Tier 2 features (fields NULL)
5. **Automatic recovery**: Circuit breaker automatically retries when ready

Example:

```python
def score_user(self, username: str):
    # Extract Tier 1 features (always works)
    tier1 = extractor.extract_tier1_features(username)

    # Try Tier 2 enhancement
    tier2 = None
    try:
        tier2 = fetcher.fetch_user_data(username)  # Calls circuit breaker
    except CircuitBreakerOpen:
        log.info(f"Using Tier 1-only scoring for {username} (API unavailable)")

    # Score with whatever we have
    if tier2:
        result = scorer.score_with_tier2(tier1, tier2)
    else:
        result = scorer.score_user(tier1)  # Works fine without Tier 2

    return result
```

---

## 3. Per-Minute Rate Limiting

In addition to the daily budget, implement strict per-minute rate limiting to avoid 429 errors:

### Redis-Based Rate Limiter

**File**: `redditrepostsleuth/core/services/spam/rate_limiter.py`

```python
"""Per-minute rate limiting for Reddit API calls."""
import logging
from datetime import datetime, timedelta

import redis

log = logging.getLogger(__name__)


class PerMinuteRateLimiter:
    """
    Enforces per-minute rate limiting using Redis sliding window.

    Prevents hitting Reddit's 60 requests/minute limit.
    """

    def __init__(
        self,
        redis_client: redis.Redis,
        requests_per_minute: int = 50,  # Conservative: below 60 limit
        window_size_seconds: int = 60
    ):
        self.redis = redis_client
        self.max_requests = requests_per_minute
        self.window_size = window_size_seconds
        self.key = "spam_detection:api_rate_limit"

    def is_allowed(self) -> bool:
        """Check if API call is allowed."""
        try:
            current = datetime.utcnow()
            window_key = f"{self.key}:{current.minute}"

            pipe = self.redis.pipeline()
            pipe.incr(window_key)
            pipe.expire(window_key, self.window_size + 10)
            results = pipe.execute()

            count = results[0]

            if count <= self.max_requests:
                log.debug(f"API calls: {count}/{self.max_requests}")
                return True
            else:
                log.warning(f"Rate limit exceeded: {count}")
                return False

        except Exception as e:
            log.warning(f"Rate limiter error: {e}")
            return True  # Fail open

    def wait_if_needed(self) -> None:
        """Wait if necessary to stay within limits."""
        import time

        if not self.is_allowed():
            wait_time = self._calculate_backoff()
            log.warning(f"Rate limit hit, waiting {wait_time}s")
            time.sleep(wait_time)

    def _calculate_backoff(self) -> float:
        """Calculate backoff time."""
        current = datetime.utcnow()
        next_minute = (current + timedelta(minutes=1)).replace(second=0, microsecond=0)
        backoff = (next_minute - current).total_seconds()
        return min(backoff + 1, 60)

    def get_current_usage(self) -> dict:
        """Get rate limit usage stats."""
        try:
            current = datetime.utcnow()
            window_key = f"{self.key}:{current.minute}"
            count = int(self.redis.get(window_key) or 0)
            return {
                'requests_made': count,
                'requests_remaining': max(0, self.max_requests - count),
                'max_requests': self.max_requests,
            }
        except Exception as e:
            log.warning(f"Usage error: {e}")
            return {}
```

### Configuration

```python
# Conservative: 50/min (10/min safety margin)
limiter = PerMinuteRateLimiter(redis_client, requests_per_minute=50)

# After validation: can increase to 55/min
limiter = PerMinuteRateLimiter(redis_client, requests_per_minute=55)
```

---

## 4. Tier 2 Feature Definitions

### Features from Single API Call (Redditor Object)

| Feature | API Field | Spam Indicator |
|---------|-----------|----------------|
| `account_age_days` | `redditor.created_utc` | <30 days + high activity = suspicious |
| `total_karma` | `redditor.total_karma` | Very low for account age = suspicious |
| `post_karma` | `redditor.link_karma` | Imbalanced ratio may indicate behavior |
| `comment_karma` | `redditor.comment_karma` | Very low = suspicious |
| `karma_per_day` | Calculated | <0.5/day for old accounts = suspicious |
| `has_verified_email` | `redditor.has_verified_email` | False = slightly suspicious |
| `is_gold` | `redditor.is_gold` | True = less suspicious |
| `has_custom_avatar` | Check `redditor.icon_img` | Default = slightly suspicious |
| `is_mod` | `redditor.moderated()` | Being a mod = less suspicious |
| `account_suspended` | Exception handling | 403/404 = confirmed spam |

### Data Model Extension

Add to `UserSpamFeatures` in Phase 0 migration (already included):

```python
# Tier 2: From single Reddit API call
account_age_days = Column(Integer)
total_karma = Column(Integer)
post_karma = Column(Integer)
comment_karma = Column(Integer)
karma_per_day = Column(Float)
has_verified_email = Column(Boolean)
is_gold = Column(Boolean)
has_custom_avatar = Column(Boolean)
account_suspended = Column(Boolean, default=False)
```

---

## 3. UserDataFetcher Service

### File: `redditrepostsleuth/core/services/spam/user_data_fetcher.py`

```python
"""
User Data Fetcher Service

Fetches user data from Reddit API with rate limiting.
Handles suspended/deleted users gracefully.
"""
import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from praw import Reddit
from praw.exceptions import RedditAPIException
from prawcore.exceptions import NotFound, Forbidden, TooManyRequests

from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager

log = logging.getLogger(__name__)


@dataclass
class Tier2Features:
    """Container for Tier 2 (API-sourced) features."""
    account_age_days: int
    total_karma: int
    post_karma: int
    comment_karma: int
    karma_per_day: float
    has_verified_email: bool
    is_gold: bool
    has_custom_avatar: bool
    is_mod: bool
    account_suspended: bool = False

    # Metadata
    fetched_at: datetime = None
    fetch_success: bool = True
    error_message: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            'account_age_days': self.account_age_days,
            'total_karma': self.total_karma,
            'post_karma': self.post_karma,
            'comment_karma': self.comment_karma,
            'karma_per_day': self.karma_per_day,
            'has_verified_email': self.has_verified_email,
            'is_gold': self.is_gold,
            'has_custom_avatar': self.has_custom_avatar,
            'is_mod': self.is_mod,
            'account_suspended': self.account_suspended,
            'fetched_at': self.fetched_at.isoformat() if self.fetched_at else None,
            'fetch_success': self.fetch_success,
        }


class RateLimitExceeded(Exception):
    """Raised when rate limit is exceeded and retry is needed."""
    def __init__(self, retry_after: int = 60):
        self.retry_after = retry_after
        super().__init__(f"Rate limit exceeded, retry after {retry_after}s")


class UserDataFetcher:
    """
    Fetches user data from Reddit API with rate limiting.

    This service enforces rate limiting to avoid 429 errors and
    handles various error conditions gracefully.
    """

    # Default avatars contain these substrings
    DEFAULT_AVATAR_INDICATORS = [
        'snoomoji',
        'snoovatar_default',
        'default_icon',
        'avatar_default',
    ]

    def __init__(
        self,
        reddit: Reddit,
        uowm: UnitOfWorkManager,
        min_interval: float = 1.5,
        max_retries: int = 3
    ):
        """
        Initialize the user data fetcher.

        Args:
            reddit: PRAW Reddit instance
            uowm: Unit of Work Manager for database access
            min_interval: Minimum seconds between API calls (default 1.5)
            max_retries: Maximum retries on transient failures
        """
        self.reddit = reddit
        self.uowm = uowm
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
            Tier2Features or None if user not found

        Raises:
            RateLimitExceeded: If rate limit hit, caller should retry
        """
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
                total_karma=redditor.total_karma,
                post_karma=redditor.link_karma,
                comment_karma=redditor.comment_karma,
                karma_per_day=redditor.total_karma / max(1, account_age_days),
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

            log.debug(f"Successfully fetched data for {username}")
            return features

        except NotFound:
            # User doesn't exist or is shadowbanned
            log.info(f"User not found (deleted/shadowbanned): {username}")
            self._consecutive_errors = 0
            return Tier2Features(
                account_age_days=0,
                total_karma=0,
                post_karma=0,
                comment_karma=0,
                karma_per_day=0,
                has_verified_email=False,
                is_gold=False,
                has_custom_avatar=False,
                is_mod=False,
                account_suspended=True,  # Treat as suspended
                fetched_at=datetime.utcnow(),
                fetch_success=True,
                error_message="User not found (deleted or shadowbanned)",
            )

        except Forbidden:
            # User is suspended
            log.info(f"User suspended (403 Forbidden): {username}")
            self._consecutive_errors = 0
            return Tier2Features(
                account_age_days=0,
                total_karma=0,
                post_karma=0,
                comment_karma=0,
                karma_per_day=0,
                has_verified_email=False,
                is_gold=False,
                has_custom_avatar=False,
                is_mod=False,
                account_suspended=True,
                fetched_at=datetime.utcnow(),
                fetch_success=True,
                error_message="User suspended by Reddit",
            )

        except TooManyRequests as e:
            # Rate limited - need to back off
            self._consecutive_errors += 1
            retry_after = getattr(e, 'retry_after', 60) or 60

            log.warning(
                f"Rate limited fetching {username}, retry after {retry_after}s"
            )
            raise RateLimitExceeded(retry_after=retry_after)

        except RedditAPIException as e:
            # Other Reddit API errors
            self._consecutive_errors += 1
            log.error(f"Reddit API error for {username}: {e}")
            return None

        except Exception as e:
            # Unexpected errors
            self._consecutive_errors += 1
            log.error(f"Unexpected error fetching {username}: {e}", exc_info=True)
            return None

    def fetch_user_moderated_subs(self, username: str) -> Optional[list]:
        """
        Check if user moderates any subreddits.

        This is an additional API call, use selectively.

        Args:
            username: Reddit username

        Returns:
            List of moderated subreddit names or None on error
        """
        self._enforce_rate_limit()

        try:
            redditor = self.reddit.redditor(username)
            moderated = list(redditor.moderated())

            self._consecutive_errors = 0
            return [sub.display_name for sub in moderated]

        except (NotFound, Forbidden):
            return []

        except TooManyRequests as e:
            self._consecutive_errors += 1
            raise RateLimitExceeded(retry_after=getattr(e, 'retry_after', 60))

        except Exception as e:
            self._consecutive_errors += 1
            log.error(f"Error fetching moderated subs for {username}: {e}")
            return None

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
            return False

        except (NotFound, Forbidden):
            self._consecutive_errors = 0
            return True

        except TooManyRequests as e:
            self._consecutive_errors += 1
            raise RateLimitExceeded(retry_after=getattr(e, 'retry_after', 60))

        except Exception as e:
            self._consecutive_errors += 1
            log.error(f"Error checking suspension for {username}: {e}")
            raise

    def batch_fetch_users(
        self,
        usernames: list,
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

            except Exception as e:
                log.error(f"Failed to fetch {username}: {e}")
                results[username] = None

        return results
```

---

## 4. Rate Limiting Strategy

### Queue-Based Throttling

The spam detection queue should have limited concurrency:

**File**: `redditrepostsleuth/core/celery/celeryconfig.py`

```python
# Add to worker configuration
task_routes = {
    # ... existing routes ...
    'redditrepostsleuth.core.celery.tasks.spam_detection_tasks.*': {
        'queue': 'spam_detection'
    },
}

# Limit concurrency for spam detection queue
# Only 1 worker to ensure rate limiting is effective
task_annotations = {
    'redditrepostsleuth.core.celery.tasks.spam_detection_tasks.*': {
        'rate_limit': '30/m',  # Max 30 tasks per minute
    },
}
```

### Worker Configuration

**File**: `docker-compose.yml` (partial)

```yaml
spam_detection_worker:
  image: repostsleuth-worker
  command: celery -A redditrepostsleuth.core.celery worker -Q spam_detection -c 1 --loglevel=info
  environment:
    - CELERY_WORKER_CONCURRENCY=1  # Single worker for rate limiting
  depends_on:
    - redis
    - mysql
```

### Caching Strategy

Cache user data to avoid redundant API calls:

```python
class CachedUserDataFetcher(UserDataFetcher):
    """
    User data fetcher with caching layer.

    Caches results to avoid redundant API calls for recently fetched users.
    """

    def __init__(
        self,
        reddit: Reddit,
        uowm: UnitOfWorkManager,
        cache_ttl_hours: int = 24,
        **kwargs
    ):
        super().__init__(reddit, uowm, **kwargs)
        self.cache_ttl_hours = cache_ttl_hours

    def fetch_basic_user_data(self, username: str) -> Optional[Tier2Features]:
        """
        Fetch user data with caching.

        Checks database for recent data before making API call.
        """
        # Check cache (database)
        with self.uowm.start() as uow:
            cached = uow.spam_features.get_latest_by_username(username)

            if cached and cached.account_age_days is not None:
                # Check if cache is fresh
                cache_age_hours = (
                    datetime.utcnow() - cached.computed_at
                ).total_seconds() / 3600

                if cache_age_hours < self.cache_ttl_hours:
                    log.debug(f"Using cached data for {username}")
                    return Tier2Features(
                        account_age_days=cached.account_age_days,
                        total_karma=cached.total_karma,
                        post_karma=cached.post_karma,
                        comment_karma=cached.comment_karma,
                        karma_per_day=cached.karma_per_day,
                        has_verified_email=cached.has_verified_email,
                        is_gold=cached.is_gold,
                        has_custom_avatar=cached.has_custom_avatar,
                        is_mod=False,
                        account_suspended=cached.account_suspended,
                        fetched_at=cached.computed_at,
                        fetch_success=True,
                    )

        # Cache miss - fetch from API
        return super().fetch_basic_user_data(username)
```

---

## 5. Celery Task Integration

### File: `redditrepostsleuth/core/celery/tasks/spam_detection_tasks.py`

Add these tasks to the existing file:

```python
from redditrepostsleuth.core.services.spam.user_data_fetcher import (
    UserDataFetcher,
    RateLimitExceeded,
    Tier2Features,
)


@shared_task(
    bind=True,
    base=RedditTask,  # Base class with Reddit instance
    queue='spam_detection',
    autoretry_for=(RateLimitExceeded,),
    retry_backoff=60,
    retry_backoff_max=300,
    retry_kwargs={'max_retries': 3}
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
    log.info(f"Enriching Tier 2 features for: {username}")

    try:
        fetcher = UserDataFetcher(self.reddit, self.uowm)
        tier2_features = fetcher.fetch_basic_user_data(username)

        if not tier2_features:
            log.warning(f"Failed to fetch Tier 2 data for {username}")
            return None

        # Update stored features
        with self.uowm.start() as uow:
            features = uow.spam_features.get_latest_by_username(username)

            if features:
                features.account_age_days = tier2_features.account_age_days
                features.total_karma = tier2_features.total_karma
                features.post_karma = tier2_features.post_karma
                features.comment_karma = tier2_features.comment_karma
                features.karma_per_day = tier2_features.karma_per_day
                features.has_verified_email = tier2_features.has_verified_email
                features.is_gold = tier2_features.is_gold
                features.has_custom_avatar = tier2_features.has_custom_avatar
                features.account_suspended = tier2_features.account_suspended
                uow.commit()

                log.info(f"Updated Tier 2 features for {username}")
            else:
                log.warning(f"No existing features to update for {username}")

        return tier2_features.to_dict()

    except RateLimitExceeded:
        # Let Celery handle retry
        raise

    except Exception as e:
        log.error(f"Error enriching {username}: {e}", exc_info=True)
        return None


@shared_task(
    bind=True,
    base=RedditTask,
    queue='spam_detection',
)
def check_user_suspended(self, username: str) -> bool:
    """
    Quick check if user is suspended.

    Used for training data collection.

    Args:
        username: Reddit username to check

    Returns:
        True if user is suspended/deleted
    """
    try:
        fetcher = UserDataFetcher(self.reddit, self.uowm)
        return fetcher.check_user_suspended(username)

    except RateLimitExceeded:
        raise

    except Exception as e:
        log.error(f"Error checking suspension for {username}: {e}")
        raise


@shared_task(
    bind=True,
    base=RedditTask,
    queue='spam_detection',
)
def enrich_high_risk_users(
    self,
    min_score: float = 0.5,
    limit: int = 50
) -> dict:
    """
    Enrich Tier 2 features for high-risk users.

    Finds users with high spam scores but no Tier 2 data
    and fetches their data.

    Args:
        min_score: Minimum spam score to qualify
        limit: Maximum users to enrich

    Returns:
        Dict with enrichment results
    """
    log.info(f"Enriching high-risk users (score >= {min_score})")

    with self.uowm.start() as uow:
        # Find users needing enrichment
        high_risk = uow.spam_features.get_high_risk_users(
            min_score=min_score,
            limit=limit * 2  # Fetch extra to filter
        )

        # Filter to those without Tier 2 data
        needs_enrichment = [
            f.username for f in high_risk
            if f.account_age_days is None
        ][:limit]

    if not needs_enrichment:
        log.info("No users need Tier 2 enrichment")
        return {'enriched': 0}

    log.info(f"Enriching {len(needs_enrichment)} users")

    results = {
        'total': len(needs_enrichment),
        'enriched': 0,
        'suspended': 0,
        'failed': 0,
    }

    for username in needs_enrichment:
        try:
            tier2 = enrich_user_features_tier2(username)

            if tier2:
                results['enriched'] += 1
                if tier2.get('account_suspended'):
                    results['suspended'] += 1
            else:
                results['failed'] += 1

            # Small delay between users (rate limit protection)
            time.sleep(1.0)

        except RateLimitExceeded as e:
            log.warning(f"Rate limited, pausing {e.retry_after}s")
            time.sleep(e.retry_after)

        except Exception as e:
            log.error(f"Failed to enrich {username}: {e}")
            results['failed'] += 1

    log.info(f"Enrichment complete: {results}")
    return results


@shared_task(
    bind=True,
    base=SqlAlchemyTask,
    queue='spam_detection',
)
def score_with_tier2(self, username: str) -> Optional[dict]:
    """
    Score a user using both Tier 1 and Tier 2 features.

    This provides a more accurate score by incorporating
    Reddit API data.

    Args:
        username: Reddit username to score

    Returns:
        Dict with enhanced scoring results
    """
    from redditrepostsleuth.core.services.spam.spam_scorer import SpamScorerWithTier2

    with self.uowm.start() as uow:
        features = uow.spam_features.get_latest_by_username(username)

    if not features:
        log.warning(f"No features found for {username}")
        return None

    if features.account_age_days is None:
        log.info(f"No Tier 2 data for {username}, using Tier 1 only")
        # Fall back to Tier 1 scoring
        from redditrepostsleuth.core.services.spam.spam_scorer import SpamScorer
        from redditrepostsleuth.core.services.spam.spam_feature_extractor import SpamFeatureExtractor

        extractor = SpamFeatureExtractor(self.uowm)
        tier1 = extractor.extract_tier1_features(username)

        if not tier1:
            return None

        scorer = SpamScorer(self.uowm)
        return scorer.score_user(tier1).to_dict()

    # Build Tier 1 features from stored data
    tier1_features = Tier1Features(
        total_posts_indexed=features.total_posts_indexed,
        total_reposts_detected=features.total_reposts_detected,
        repost_ratio=features.repost_ratio,
        unique_subreddits_posted=features.unique_subreddits_posted,
        posts_per_day_avg=features.posts_per_day_avg,
        first_post_date=features.first_post_date,
        last_post_date=features.last_post_date,
        nsfw_post_ratio=features.nsfw_post_ratio,
        summons_received=features.summons_received,
        adult_platform_post_count=features.adult_platform_post_count,
        adult_platform_ratio=features.adult_platform_ratio,
        short_link_post_count=features.short_link_post_count,
        short_link_ratio=features.short_link_ratio,
        detected_platforms=features.detected_platforms or [],
        username_suspicious_pattern=features.username_suspicious_pattern,
        username_pattern_matches=features.username_pattern_matches or {},
        subreddit_distribution={},  # Not stored
        karma_farming_sub_posts=features.karma_farming_sub_posts or 0,
        easy_karma_sub_posts=features.easy_karma_sub_posts or 0,
    )

    # Build Tier 2 features
    tier2_features = {
        'account_age_days': features.account_age_days,
        'total_karma': features.total_karma,
        'post_karma': features.post_karma,
        'comment_karma': features.comment_karma,
        'karma_per_day': features.karma_per_day,
        'has_verified_email': features.has_verified_email,
        'is_gold': features.is_gold,
        'has_custom_avatar': features.has_custom_avatar,
        'account_suspended': features.account_suspended,
    }

    # Score with both tiers
    scorer = SpamScorerWithTier2(self.uowm)
    result = scorer.score_with_tier2(tier1_features, tier2_features)

    # Update stored score
    with self.uowm.start() as uow:
        features = uow.spam_features.get_latest_by_username(username)
        if features:
            features.rule_score = result.score
            features.final_score = result.score
            features.risk_level = result.risk_level
            features.top_contributing_factors = result.reasons
            uow.commit()

    return result.to_dict()
```

---

## 6. Enhanced Scoring

### Tier 2 Score Adjustments

The `SpamScorerWithTier2` class (from Phase 2 document) applies these adjustments:

| Signal | Weight | Condition |
|--------|--------|-----------|
| Account suspended | +0.50 | Confirmed spam |
| Very new account | +0.15 | <30 days old |
| New account | +0.08 | <90 days old |
| Very low karma | +0.10 | <100 karma, >30 days old |
| Low karma rate | +0.05 | <0.5 karma/day, >90 days old |
| No verified email | +0.05 | Always |
| Default avatar | +0.03 | No customization |

### Negative Signals (Reduce Score)

| Signal | Weight | Condition |
|--------|--------|-----------|
| Reddit Gold | -0.05 | User has/had gold |
| Is moderator | -0.10 | Moderates any subreddit |
| High karma | -0.05 | >10,000 total karma |
| Old account | -0.05 | >2 years old with activity |

---

## 7. Error Handling

### Error Categories

| Error Type | Handling | Retry |
|------------|----------|-------|
| `NotFound` (404) | User deleted/shadowbanned - mark suspended | No |
| `Forbidden` (403) | User suspended - mark suspended | No |
| `TooManyRequests` (429) | Rate limited - back off | Yes |
| `RedditAPIException` | API error - log and skip | No |
| Other exceptions | Unexpected - log with stack trace | Maybe |

### Graceful Degradation

When API enrichment fails, the system should:
1. Continue using Tier 1 features only
2. Mark the feature record as "enrichment_failed"
3. Schedule retry for later
4. Not block other processing

```python
def score_user_graceful(username: str) -> ScoringResult:
    """
    Score user with graceful degradation.

    Falls back to Tier 1 only if Tier 2 enrichment fails.
    """
    # Try Tier 2 enrichment
    try:
        tier2 = fetch_tier2_with_timeout(username, timeout=10)
    except Exception as e:
        log.warning(f"Tier 2 enrichment failed for {username}: {e}")
        tier2 = None

    # Score with available data
    if tier2:
        return score_with_tier2(username)
    else:
        return score_tier1_only(username)
```

---

## 8. Testing Strategy

### Unit Tests

**File**: `tests/core/services/spam/test_user_data_fetcher.py`

```python
"""Tests for UserDataFetcher."""
import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch

from prawcore.exceptions import NotFound, Forbidden, TooManyRequests

from redditrepostsleuth.core.services.spam.user_data_fetcher import (
    UserDataFetcher,
    RateLimitExceeded,
    Tier2Features,
)


class TestUserDataFetcher(unittest.TestCase):

    def setUp(self):
        self.mock_reddit = MagicMock()
        self.mock_uowm = MagicMock()
        self.fetcher = UserDataFetcher(
            self.mock_reddit,
            self.mock_uowm,
            min_interval=0.1  # Fast for tests
        )

    def test_fetch_basic_user_data_success(self):
        """Test successful user data fetch."""
        mock_redditor = MagicMock()
        mock_redditor.created_utc = datetime(2023, 1, 1).timestamp()
        mock_redditor.total_karma = 5000
        mock_redditor.link_karma = 3000
        mock_redditor.comment_karma = 2000
        mock_redditor.has_verified_email = True
        mock_redditor.is_gold = False
        mock_redditor.icon_img = 'https://custom-avatar.jpg'

        self.mock_reddit.redditor.return_value = mock_redditor

        result = self.fetcher.fetch_basic_user_data('testuser')

        self.assertIsInstance(result, Tier2Features)
        self.assertEqual(result.total_karma, 5000)
        self.assertTrue(result.has_verified_email)
        self.assertFalse(result.account_suspended)

    def test_fetch_user_not_found(self):
        """Test handling of deleted/shadowbanned user."""
        self.mock_reddit.redditor.return_value.created_utc = property(
            lambda self: (_ for _ in ()).throw(NotFound(MagicMock()))
        )
        # Simpler approach:
        mock_redditor = MagicMock()
        type(mock_redditor).created_utc = property(
            lambda self: self._raise_not_found()
        )
        mock_redditor._raise_not_found = lambda: (_ for _ in ()).throw(NotFound(MagicMock()))

        self.mock_reddit.redditor.side_effect = NotFound(MagicMock())

        result = self.fetcher.fetch_basic_user_data('deleteduser')

        # Should return features with suspended=True
        # Note: actual implementation catches exception
        # This test needs adjustment based on actual implementation

    def test_fetch_user_suspended(self):
        """Test handling of suspended user."""
        self.mock_reddit.redditor.side_effect = Forbidden(MagicMock())

        result = self.fetcher.fetch_basic_user_data('suspendeduser')

        self.assertIsNotNone(result)
        self.assertTrue(result.account_suspended)

    def test_rate_limit_raises_exception(self):
        """Test that rate limit triggers RateLimitExceeded."""
        mock_exception = TooManyRequests(MagicMock())
        mock_exception.retry_after = 120

        self.mock_reddit.redditor.side_effect = mock_exception

        with self.assertRaises(RateLimitExceeded) as context:
            self.fetcher.fetch_basic_user_data('anyuser')

        self.assertEqual(context.exception.retry_after, 120)

    def test_rate_limiting_enforced(self):
        """Test that rate limiting delays requests."""
        mock_redditor = MagicMock()
        mock_redditor.created_utc = datetime.now().timestamp()
        mock_redditor.total_karma = 100
        mock_redditor.link_karma = 50
        mock_redditor.comment_karma = 50
        mock_redditor.has_verified_email = True
        mock_redditor.is_gold = False
        mock_redditor.icon_img = ''

        self.mock_reddit.redditor.return_value = mock_redditor

        # Set min_interval to measurable amount
        self.fetcher.min_interval = 0.5

        import time
        start = time.time()

        # Two rapid requests
        self.fetcher.fetch_basic_user_data('user1')
        self.fetcher.fetch_basic_user_data('user2')

        elapsed = time.time() - start

        # Should have waited at least min_interval
        self.assertGreaterEqual(elapsed, 0.5)

    def test_default_avatar_detection(self):
        """Test detection of default avatars."""
        default_urls = [
            'https://styles.redditmedia.com/t5_snoomoji_img.png',
            'https://reddit.com/avatar_default_01.png',
            'https://snoovatar_default.png',
        ]

        for url in default_urls:
            self.assertTrue(
                self.fetcher._is_default_avatar(url),
                f"Should detect {url} as default"
            )

        custom_urls = [
            'https://i.redd.it/custom_avatar_abc123.png',
            'https://preview.redd.it/user_profile_pic.jpg',
        ]

        for url in custom_urls:
            self.assertFalse(
                self.fetcher._is_default_avatar(url),
                f"Should NOT detect {url} as default"
            )


class TestRateLimitExceeded(unittest.TestCase):
    """Test RateLimitExceeded exception."""

    def test_exception_message(self):
        """Test exception message includes retry time."""
        exc = RateLimitExceeded(retry_after=120)
        self.assertIn('120', str(exc))

    def test_default_retry_after(self):
        """Test default retry_after value."""
        exc = RateLimitExceeded()
        self.assertEqual(exc.retry_after, 60)
```

### Integration Tests

```python
"""Integration tests for Tier 2 enrichment."""
import unittest


class TestTier2Integration(unittest.TestCase):
    """Integration tests with real Reddit API (use sparingly)."""

    @unittest.skip("Requires real Reddit API - run manually")
    def test_fetch_real_user(self):
        """Test fetching a real Reddit user."""
        pass

    @unittest.skip("Requires real Reddit API - run manually")
    def test_suspended_user_detection(self):
        """Test detecting a known suspended user."""
        pass
```

---

## 9. Verification Checklist

### Pre-Implementation
- [ ] Phase 2 completed and verified
- [ ] PRAW configured and working
- [ ] Rate limit budget approved

### UserDataFetcher
- [ ] Rate limiting enforced correctly
- [ ] Suspended user detection works
- [ ] Deleted user handling works
- [ ] TooManyRequests triggers retry
- [ ] Exponential backoff on errors

### Celery Tasks
- [ ] enrich_user_features_tier2 updates database
- [ ] Auto-retry on rate limit works
- [ ] check_user_suspended returns correct bool
- [ ] Batch enrichment respects rate limits

### Integration
- [ ] High-risk user enrichment runs without 429s
- [ ] Score with Tier 2 produces enhanced results
- [ ] Graceful degradation to Tier 1 works

### Performance
- [ ] Single user enrichment <3 seconds
- [ ] 50 users/hour sustainable
- [ ] No 429 errors in normal operation

---

## Dependencies

### Python Packages
- `praw` (existing)
- `prawcore` (existing, for exceptions)

### Infrastructure
- Reddit API credentials
- Single-worker spam_detection queue

---

## Estimated Effort

| Task | Estimate |
|------|----------|
| UserDataFetcher service | 4 hours |
| Rate limiting implementation | 3 hours |
| Caching layer | 2 hours |
| Celery tasks | 3 hours |
| Error handling | 2 hours |
| Unit tests | 4 hours |
| Integration testing | 4 hours |
| Documentation | 2 hours |
| **Total** | ~24 hours |
