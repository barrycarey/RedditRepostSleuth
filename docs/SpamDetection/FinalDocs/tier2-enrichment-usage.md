# Tier 2 Enrichment Usage Guide

## Overview

**Phase 3: Tier 2 Feature Enrichment** extends the spam detection system with Reddit API-sourced features. Unlike Tier 1 (which uses only database data), Tier 2 fetches live user data from Reddit to enhance detection accuracy.

### What Tier 2 Does

1. **Fetches user account information** via Reddit API (single `redditor` object call per user)
2. **Scans user profiles and comments** for adult platform and Telegram links
3. **Detects suspended accounts** (confirmed spam indicators)
4. **Protects against API failures** with circuit breaker pattern
5. **Rate-limits API calls** to stay within Reddit's 60 requests/minute quota
6. **Gracefully degrades** to Tier 1-only scoring if API unavailable

### Key Design Principles

- **Single-worker queue**: Rate limiting via Celery concurrency control (1 worker)
- **Circuit breaker**: Fail-fast when API unavailable, automatic recovery testing
- **Conservative rate limiting**: 50 req/min (10/min safety margin from Reddit's 60)
- **Caching**: Database caching for 24 hours to reduce API calls
- **Non-blocking**: Tasks retry on rate limits; system continues with Tier 1 scoring

---

## Architecture Components

### 1. CircuitBreaker Service

**Location**: `redditrepostsleuth/core/services/spam/circuit_breaker.py`

Protects against cascading failures when Reddit API is unavailable.

#### States

```
CLOSED (Normal)
├─ Accept all API requests
├─ Track consecutive failures
└─ Open if failures ≥ 5

OPEN (API Unavailable)
├─ Reject all API requests immediately
├─ Return error without calling API
└─ Switch to HALF_OPEN after 60 second timeout

HALF_OPEN (Testing Recovery)
├─ Allow test request to API
├─ Success → CLOSED (full recovery)
├─ Failure → OPEN with doubled timeout
└─ Recovery timeout: 60s * 1.5^N (max 600s)
```

#### Configuration

| Parameter | Value | Purpose |
|-----------|-------|---------|
| `failure_threshold` | 5 | Open after 5 consecutive failures |
| `success_threshold` | 2 | Close after 2 successes in HALF_OPEN |
| `recovery_timeout` | 60s | Initial wait before recovery test |
| `backoff_multiplier` | 1.5 | Increase timeout on repeated failures |
| `max_recovery_timeout` | 600s | Cap recovery timeout at 10 minutes |

#### Usage

```python
from redditrepostsleuth.core.services.spam.circuit_breaker import CircuitBreaker

breaker = CircuitBreaker()

try:
    result = breaker.call(fetch_user_data, username)
except CircuitBreakerOpen as e:
    # API unavailable, use Tier 1-only scoring
    log.info(f"Falling back to Tier 1: {e}")
```

#### Monitoring

```python
status = breaker.get_status()
# {
#     'state': 'CLOSED',
#     'failure_count': 0,
#     'success_count': 0,
#     'recovery_timeout': 60,
#     'time_until_retry': 0,
#     'last_failure_time': None
# }
```

---

### 2. PerMinuteRateLimiter Service

**Location**: `redditrepostsleuth/core/services/spam/rate_limiter.py`

Redis-based sliding window rate limiter to enforce per-minute limits.

#### Configuration

- **Default**: 50 requests/minute (conservative)
- **Can increase to**: 55 requests/minute after validation
- **Safety margin**: 10 requests below Reddit's 60 req/min limit

#### Usage

```python
from redditrepostsleuth.core.services.spam.rate_limiter import PerMinuteRateLimiter
import redis

redis_client = redis.Redis(host='localhost', port=6379, db=0)
limiter = PerMinuteRateLimiter(redis_client, requests_per_minute=50)

# Check if request is allowed
if limiter.is_allowed():
    # Make API call
    pass
else:
    # Wait until next minute
    limiter.wait_if_needed()  # Blocks until allowed

# Get current usage
usage = limiter.get_current_usage()
# {
#     'requests_made': 32,
#     'requests_remaining': 18,
#     'max_requests': 50,
#     'current_minute': 42,
#     'reset_in_seconds': 18
# }
```

#### Fallback

If Redis unavailable, `InMemoryRateLimiter` provides in-memory sliding window:

```python
from redditrepostsleuth.core.services.spam.rate_limiter import InMemoryRateLimiter

limiter = InMemoryRateLimiter(requests_per_minute=50)
```

---

### 3. Tier2Features Dataclass

**Location**: `redditrepostsleuth/core/services/spam/tier2_features.py`

Container for Tier 2 features fetched from Reddit API.

```python
@dataclass
class Tier2Features:
    # Account info from single Reddit API call
    account_age_days: int = 0
    total_karma: int = 0
    post_karma: int = 0
    comment_karma: int = 0
    karma_per_day: float = 0.0
    has_verified_email: bool = False
    is_gold: bool = False
    has_custom_avatar: bool = False
    is_mod: bool = False
    account_suspended: bool = False

    # Profile/comment scanning results
    has_adult_profile_links: bool = False
    has_telegram_links: bool = False
    profile_link_sources: Dict[str, List[str]] = {}

    # Metadata
    fetched_at: Optional[datetime] = None
    fetch_success: bool = True
    error_message: Optional[str] = None
```

#### Factory Methods

```python
# Suspended user
features = Tier2Features.suspended_user(username, "Reason")

# Failed fetch
features = Tier2Features.failed_fetch("Error message")

# Check if suspicious
is_suspicious = features.is_suspicious()  # 3+ suspicious indicators

# Get reasons
reasons = features.get_suspicion_reasons()
# ['Account is suspended', 'New account (25 days old)', 'Has Telegram links']
```

---

### 4. UserDataFetcher Service

**Location**: `redditrepostsleuth/core/services/spam/user_data_fetcher.py`

Main service for fetching user data from Reddit API with protection mechanisms.

#### Initialization

```python
from redditrepostsleuth.core.services.spam.user_data_fetcher import UserDataFetcher

fetcher = UserDataFetcher(
    reddit=reddit_instance,
    uowm=uow_manager,
    circuit_breaker=breaker,  # Optional
    rate_limiter=limiter,      # Optional
    min_interval=1.5,          # Minimum seconds between API calls
    max_retries=3              # Max retries on transient errors
)
```

#### Methods

**fetch_basic_user_data(username)**

Fetches account info with single API call.

```python
features = fetcher.fetch_basic_user_data('SomeUser')
# Returns Tier2Features or None on error

if features and features.account_suspended:
    print(f"Confirmed spam: {features.error_message}")
```

**scan_user_profile_links(username)**

Scans profile description and recent comments for adult/Telegram links.

```python
result = fetcher.scan_user_profile_links('SomeUser')
# {
#     'has_adult_links': True,
#     'has_telegram_links': True,
#     'sources': {
#         'profile': ['public_description'],
#         'comments': ['abc123def', 'xyz789'],
#         'telegram': ['public_description']
#     }
# }
```

**check_user_suspended(username)**

Quick check if user is suspended (single API call).

```python
is_suspended = fetcher.check_user_suspended('SomeUser')
# True if user is deleted, shadowbanned, or suspended
# False if user exists and is active
```

**fetch_and_enrich(username, scan_profile=False)**

Complete enrichment: fetch data + optionally scan profile.

```python
features = fetcher.fetch_and_enrich('SomeUser', scan_profile=True)
# Includes all data: account info + profile/comment links
```

**batch_fetch_users(usernames, on_progress=None)**

Fetch data for multiple users with rate limiting and error handling.

```python
usernames = ['User1', 'User2', 'User3', ...]

def progress(username, index, total):
    print(f"[{index}/{total}] Fetching {username}")

results = fetcher.batch_fetch_users(usernames, on_progress=progress)
# {
#     'User1': Tier2Features(...),
#     'User2': Tier2Features(...),
#     'User3': None,  # Error
# }
```

#### Error Handling

| Exception | Handling | Example |
|-----------|----------|---------|
| `NotFound` (404) | Returns suspended features | Deleted/shadowbanned user |
| `Forbidden` (403) | Returns suspended features | Account suspended by Reddit |
| `TooManyRequests` (429) | Raises `RateLimitExceeded` | Task auto-retries |
| `RedditAPIException` | Logs error, returns None | Other API errors |
| Other exceptions | Logs error, returns None | Network, parsing errors |

---

### 5. CachedUserDataFetcher

**Location**: `redditrepostsleuth/core/services/spam/user_data_fetcher.py`

Extends `UserDataFetcher` with database caching (24-hour TTL).

```python
from redditrepostsleuth.core.services.spam.user_data_fetcher import CachedUserDataFetcher

fetcher = CachedUserDataFetcher(
    reddit=reddit_instance,
    uowm=uow_manager,
    cache_ttl_hours=24  # Cache for 24 hours
)

# First call: fetches from API
features = fetcher.fetch_basic_user_data('User1')

# Second call (within 24 hours): returns from cache
features = fetcher.fetch_basic_user_data('User1')  # No API call made

# After 24 hours: fetches from API again
```

---

## Celery Tasks

### Task 1: enrich_user_features_tier2(username)

Fetches Tier 2 features and updates user_spam_features table.

**Location**: `redditrepostsleuth/core/celery/tasks/spam_detection_tasks.py`

**Queue**: `spam_detection`

**Configuration**
```python
@celery.task(
    bind=True,
    base=SpamDetectionTaskWithReddit,
    ignore_results=False,
    autoretry_for=(RateLimitExceeded,),
    retry_kwargs={'max_retries': 3, 'countdown': 60}
)
```

**Parameters**
- `username` (str): Reddit username to enrich

**Returns**
- Dict with Tier 2 features, or None on failure
- Retries automatically on rate limits (up to 3 times)

**Usage**

```python
# Enqueue for async processing
enrich_user_features_tier2.delay('SomeUser')

# Wait for result
result = enrich_user_features_tier2.delay('SomeUser').get(timeout=10)

# Returns:
# {
#     'account_age_days': 365,
#     'total_karma': 5000,
#     'post_karma': 3000,
#     'comment_karma': 2000,
#     'karma_per_day': 13.7,
#     'has_verified_email': True,
#     'is_gold': False,
#     'has_custom_avatar': True,
#     'is_mod': False,
#     'account_suspended': False,
#     'has_adult_profile_links': False,
#     'has_telegram_links': False,
#     'profile_link_sources': {},
#     'fetched_at': '2024-01-25T12:34:56',
#     'fetch_success': True
# }
```

**Behavior**

1. Creates `UserDataFetcher` with circuit breaker & rate limiter
2. Fetches basic user data + scans profile for links
3. Updates `user_spam_features` table with new columns
4. Returns features dict
5. On rate limit: auto-retries with exponential backoff
6. On circuit breaker open: logs warning and retries

---

### Task 2: check_user_suspended_task(username)

Quick suspension check for training data collection.

**Location**: `redditrepostsleuth/core/celery/tasks/spam_detection_tasks.py`

**Queue**: `spam_detection`

**Parameters**
- `username` (str): Reddit username to check

**Returns**
- Boolean: True if suspended/deleted, False otherwise

**Usage**

```python
# Check if user is suspended
is_suspended = check_user_suspended_task.delay('SomeUser').get()

if is_suspended:
    print("Confirmed spam - account was suspended")
else:
    print("Account is still active")
```

**Notes**

- Very fast: single API call
- Useful for building confirmed spam training data
- Suspended users marked in database

---

### Task 3: enrich_high_risk_users(min_score=0.5, limit=50)

Batch enrichment of high-risk users (those without Tier 2 data yet).

**Location**: `redditrepostsleuth/core/celery/tasks/spam_detection_tasks.py`

**Queue**: `spam_detection`

**Parameters**
- `min_score` (float): Minimum spam score to qualify (0.0-1.0)
- `limit` (int): Maximum users to enrich

**Returns**

```python
{
    'total': 45,        # Total users needing enrichment
    'enriched': 42,     # Successfully enriched
    'suspended': 8,     # Found to be suspended
    'failed': 3         # Failed to enrich
}
```

**Usage**

```python
# Enrich top 50 high-risk users
result = enrich_high_risk_users.delay(min_score=0.7, limit=50).get()

print(f"Enriched {result['enriched']}/{result['total']} users")
print(f"Found {result['suspended']} suspended accounts")

# Typical production schedule:
# - Run daily to keep Tier 2 data fresh
# - Processes ~40-50 users per run
# - Takes ~2-3 minutes per user (rate-limited at 50/min)
```

**Algorithm**

1. Query `user_spam_features` for high-risk users without Tier 2 data
2. For each user:
   - Call `enrich_user_features_tier2(username)` directly
   - Track results (success/suspended/failed)
   - Sleep 1.5s between users (rate limit protection)
3. Return summary

**Notes**

- Runs synchronously within task (calls other tasks directly)
- Rate-limiting built-in (1.5s sleep between users = ~40/min)
- Respects circuit breaker state (pauses if API unavailable)

---

### Task 4: scan_user_for_telegram_links(username)

Focused Telegram link detection in profile and comments.

**Location**: `redditrepostsleuth/core/celery/tasks/spam_detection_tasks.py`

**Queue**: `spam_detection`

**Parameters**
- `username` (str): Reddit username to scan

**Returns**

```python
{
    'has_adult_links': True,
    'has_telegram_links': True,
    'sources': {
        'profile': ['public_description'],
        'comments': ['abc123def'],
        'telegram': ['public_description']
    }
}
```

**Usage**

```python
# Scan single user
result = scan_user_for_telegram_links.delay('SomeUser').get()

if result.get('has_telegram_links'):
    print("Found Telegram links - confirmed promotional account")
    print(f"Sources: {result['sources']}")
```

**Detected Patterns**

```
Telegram: t.me/, telegram.me/, telegram.org/
Adult platforms: onlyfans.com, fansly.com, chaturbate.com, ...
```

**Notes**

- Scans profile description + last 10 comments only
- Updates database with findings
- Used for training data collection

---

## Database Changes

### New Columns Added to user_spam_features Table

Tier 2 enrichment adds 15 new columns:

#### Account Info (from single API call)
| Column | Type | Purpose |
|--------|------|---------|
| `account_age_days` | INT | Days since account created |
| `total_karma` | INT | Total karma across posts+comments |
| `post_karma` | INT | Karma from posts (link_karma) |
| `comment_karma` | INT | Karma from comments |
| `karma_per_day` | FLOAT | Average karma per day since account creation |
| `has_verified_email` | BOOL | Account has verified email |
| `is_gold` | BOOL | Account has/had Reddit Gold |
| `has_custom_avatar` | BOOL | Account has custom avatar (not default) |
| `account_suspended` | BOOL | Account is suspended/deleted by Reddit |
| `is_mod` | BOOL | Account moderates any subreddit |

#### Profile Link Scanning
| Column | Type | Purpose |
|--------|------|---------|
| `has_adult_profile_links` | BOOL | Found adult platform links in profile/comments |
| `has_telegram_links` | BOOL | Found Telegram links (t.me, telegram.me, etc.) |
| `profile_link_sources` | JSON | Map of where links were found (profile, comments, etc.) |

#### Enrichment Metadata
| Column | Type | Purpose |
|--------|------|---------|
| `tier2_enriched_at` | DATETIME | When Tier 2 enrichment was last run |
| `tier2_enrichment_failed` | BOOL | Flag if enrichment failed last time |

---

## Configuration

### Environment Variables

```bash
# Rate limiting
SPAM_DETECTION_RATE_LIMIT=50          # Requests per minute (default: 50)

# Circuit breaker
SPAM_DETECTION_CB_FAILURE_THRESHOLD=5 # Open after N failures (default: 5)
SPAM_DETECTION_CB_RECOVERY_TIMEOUT=60 # Seconds before recovery attempt (default: 60)

# Caching
SPAM_DETECTION_CACHE_TTL_HOURS=24     # Cache freshness (default: 24)
```

### Docker-Compose Configuration

Single-worker spam detection queue for effective rate limiting:

```yaml
spam_detection_worker:
  image: repostsleuth-worker
  command: >
    celery -A redditrepostsleuth.core.celery worker
    -Q spam_detection
    -c 1
    --loglevel=info
  environment:
    - CELERY_WORKER_CONCURRENCY=1
  depends_on:
    - redis
    - mysql
```

**Key Points**
- `-Q spam_detection`: Only handles spam_detection queue tasks
- `-c 1`: Single concurrency (one task at a time)
- This ensures rate limiting is effective

### Celery Configuration

`redditrepostsleuth/core/celery/celeryconfig.py`:

```python
task_annotations = {
    'redditrepostsleuth.core.celery.tasks.spam_detection_tasks.*': {
        'rate_limit': '30/m',  # 30 tasks per minute
    },
}
```

---

## Rate Limiting Strategy

### Hierarchy

1. **Circuit Breaker**: Prevents cascading failures (API unavailable)
2. **Per-Minute Rate Limiter**: Redis-based sliding window (50 req/min)
3. **Per-Request Interval**: 1.5 second minimum between API calls
4. **Celery Task Rate Limit**: 30 tasks/minute (configured in celeryconfig)
5. **Worker Concurrency**: Single worker prevents parallelism

### Example Flow

```
Task 1 starts at 12:00:00
  ├─ Check rate limit: OK (count: 1/50)
  ├─ Call UserDataFetcher.fetch_basic_user_data()
  └─ Sleep until 12:00:01.5 (min_interval)

Task 2 starts at 12:00:01.5
  ├─ Check rate limit: OK (count: 2/50)
  ├─ Call UserDataFetcher.fetch_basic_user_data()
  └─ Sleep until 12:00:03.0 (min_interval)

... continues at 1.5 second intervals ...

At 12:01:00, minute counter resets to 0
```

### Performance

- **Sustained rate**: 40 API calls/minute (safe margin)
- **Maximum rate**: 50 API calls/minute (configured limit)
- **Daily capacity**: 40-50 calls/min × 60 min × 24 hours = ~57,600-72,000/day
- **Used daily**: ~1,000 for enrichment, leaving 71,000+ for other operations

---

## Triggering Enrichment

### Manual Enrichment

```python
from redditrepostsleuth.core.celery.tasks.spam_detection_tasks import (
    enrich_user_features_tier2,
    check_user_suspended_task,
    enrich_high_risk_users,
    scan_user_for_telegram_links
)

# Enrich single user
enrich_user_features_tier2.delay('SomeUser')

# Check if suspended
result = check_user_suspended_task.delay('SomeUser').get()

# Batch enrich high-risk users
result = enrich_high_risk_users.delay(min_score=0.6, limit=50).get()

# Scan for Telegram links
result = scan_user_for_telegram_links.delay('SomeUser').get()
```

### Scheduled Enrichment

`redditrepostsleuth/core/celery/celerybeat_config.py`:

```python
from celery.schedules import crontab

schedule = {
    'enrich-high-risk-users-daily': {
        'task': 'redditrepostsleuth.core.celery.tasks.spam_detection_tasks.enrich_high_risk_users',
        'schedule': crontab(hour=2, minute=0),  # 2 AM daily
        'args': (0.7, 50),  # min_score=0.7, limit=50
    },
    'check-top-reposters-suspension': {
        'task': 'redditrepostsleuth.core.celery.tasks.spam_detection_tasks.check_user_suspended_task',
        'schedule': crontab(hour=3, minute=0),  # 3 AM daily
        # Run for top 100 reposters from yesterday
    },
}
```

### Web API Endpoint

```python
from flask import request, jsonify

@app.route('/api/admin/spam/enrich-tier2', methods=['POST'])
def enrich_tier2():
    """Trigger Tier 2 enrichment for a user."""
    data = request.json
    username = data.get('username')

    if not username:
        return {'error': 'username required'}, 400

    from redditrepostsleuth.core.celery.tasks.spam_detection_tasks import (
        enrich_user_features_tier2
    )

    task = enrich_user_features_tier2.delay(username)

    return {
        'task_id': task.id,
        'username': username,
        'status': 'queued'
    }, 202
```

---

## Tier 2 Features Collected

### Basic Account Info (1 API call)

| Feature | Spam Indicator | Example Values |
|---------|----------------|-----------------|
| `account_age_days` | < 30 days = suspicious | 5, 30, 365 |
| `total_karma` | Very low = suspicious | 10, 5000, 100000 |
| `post_karma` | Imbalanced = suspicious | 0, 3000 |
| `comment_karma` | Very low = suspicious | 5, 2000 |
| `karma_per_day` | < 0.5/day (old account) = suspicious | 0.1, 13.7, 50.0 |
| `has_verified_email` | False = slightly suspicious | true, false |
| `is_gold` | True = less suspicious | true, false |
| `has_custom_avatar` | False = slightly suspicious | true, false |
| `is_mod` | True = less suspicious | true, false |
| `account_suspended` | True = confirmed spam | true, false |

### Profile & Comment Links (additional API calls)

| Feature | Spam Indicator | Example Values |
|---------|----------------|-----------------|
| `has_adult_profile_links` | True = promotional | true, false |
| `has_telegram_links` | True = off-platform redirect | true, false |
| `profile_link_sources` | Tracks where found | {profile: [...], comments: [...]} |

---

## Usage Examples

### Example 1: Full User Enrichment

```python
from redditrepostsleuth.core.celery.tasks.spam_detection_tasks import enrich_user_features_tier2

# Enrich a single user completely
result = enrich_user_features_tier2.delay('SuspiciousUser123').get(timeout=10)

if result:
    features = result

    # Check for spam indicators
    if features['account_suspended']:
        print("SPAM: Account is suspended")

    if features['account_age_days'] < 30 and features['total_karma'] < 100:
        print("SPAM: New account with very low karma")

    if features['has_telegram_links']:
        print("SPAM: Telegram links detected")

    if features['has_adult_profile_links']:
        print("SPAM: Adult platform links in profile")
else:
    print("ERROR: Failed to enrich user")
```

### Example 2: Batch High-Risk Enrichment

```python
from redditrepostsleuth.core.celery.tasks.spam_detection_tasks import enrich_high_risk_users

# Enrich high-risk users from last week
result = enrich_high_risk_users.delay(min_score=0.65, limit=50).get()

print(f"""
Enrichment Results:
- Total users needing enrichment: {result['total']}
- Successfully enriched: {result['enriched']}
- Found suspended: {result['suspended']}
- Failed: {result['failed']}

Estimate: {result['enriched']} users added to high-risk pool
""")
```

### Example 3: Periodic Automation

```python
# In your scheduler or cron job
def daily_enrichment():
    """Run daily at 2 AM"""
    from redditrepostsleuth.core.celery.tasks.spam_detection_tasks import enrich_high_risk_users

    # First pass: high-risk users (score > 0.7)
    result1 = enrich_high_risk_users.delay(min_score=0.7, limit=100).get()

    # Second pass: medium-risk users (score > 0.5) if API quota allows
    if result1['enriched'] < 80:  # If we have room
        result2 = enrich_high_risk_users.delay(min_score=0.5, limit=50).get()
        total_enriched = result1['enriched'] + result2['enriched']
    else:
        total_enriched = result1['enriched']

    log_stats(f"Daily enrichment: {total_enriched} users")
```

---

## Telegram Link Detection

### Patterns Detected

```
t.me/          - Direct Telegram handles
telegram.me/   - Telegram redirects
telegram.org/  - Official Telegram domain
```

### Why Telegram Matters

- **Off-platform monetization**: Telegram groups charge subscription fees
- **Content redirection**: Adult content moved off-platform to avoid moderation
- **Account linking**: Multiple accounts coordinated via Telegram
- **Spam automation**: Bots coordinated through Telegram channels

### Detection Locations

1. **Profile Description** - Public user bio/description
2. **Recent Comments** - Last 10 comments (API limit)
3. **Profile Links** - URL links from user profile

### Usage Example

```python
from redditrepostsleuth.core.celery.tasks.spam_detection_tasks import scan_user_for_telegram_links

result = scan_user_for_telegram_links.delay('PromoBot123').get()

if result['has_telegram_links']:
    print("Telegram links found:")
    for source, links in result['sources'].items():
        print(f"  {source}: {links}")

    # Add to high-risk pool or flag for manual review
```

---

## Circuit Breaker Behavior

### Normal Operation (CLOSED)

```
Request arrives
  ├─ Circuit is CLOSED
  ├─ Make API call
  ├─ Success → reset failure counter
  └─ Return result
```

### API Outage (OPEN)

```
Request arrives
  ├─ Circuit is OPEN
  ├─ Check timeout: not ready yet
  ├─ Raise CircuitBreakerOpen (fail-fast)
  └─ Task retries, falls back to Tier 1
```

### Recovery Test (HALF_OPEN)

```
Request arrives
  ├─ Circuit is OPEN
  ├─ Check timeout: ready!
  ├─ Transition to HALF_OPEN
  ├─ Make test API call
  ├─ Success → close circuit, reset counters
  ├─ Failure → open again, increase timeout by 1.5x
  └─ Return result
```

### State Transitions

```
CLOSED
  │
  └─ 5 consecutive failures
     └─ OPEN
        │
        ├─ 60 seconds pass
        └─ HALF_OPEN
           │
           ├─ 2 successes → CLOSED
           └─ 1 failure → OPEN (timeout becomes 90s)
```

---

## Performance Characteristics

### Single User Enrichment

| Operation | Time | Notes |
|-----------|------|-------|
| Rate limit check | 5ms | Redis lookup |
| API call (fetch user) | 200-500ms | Network latency |
| Profile scan (10 comments) | 500-1000ms | Multiple API calls |
| Database update | 20-50ms | SQL INSERT/UPDATE |
| **Total** | **700-1600ms** | Per-user enrichment |

### Batch Enrichment (50 users)

- **Total time**: ~50 users × 1.5 seconds (rate limit) = 75 seconds
- **Throughput**: ~40 users/minute sustained
- **Daily capacity**: 57,600 API calls (at 50/min × 1440 min/day)

### Resource Usage

- **Memory**: ~10MB per worker (Python + PRAW + DB pool)
- **Database**: ~2KB per enriched user (stored in user_spam_features)
- **Redis**: ~100 bytes for rate limit counter

---

## Troubleshooting

### Circuit Breaker Open

**Symptom**: Tasks fail with `CircuitBreakerOpen` exception

**Causes**
- Reddit API is down or rate-limiting aggressively
- Network connectivity issues
- PRAW authentication expired

**Solution**
```python
# Check breaker status
breaker.get_status()
# {'state': 'OPEN', 'time_until_retry': 45, ...}

# Wait for recovery timeout
# Or manually reset if API is confirmed working
breaker.reset()
```

### Rate Limit Exceeded

**Symptom**: Tasks retry with `RateLimitExceeded`

**Causes**
- Too many concurrent requests from other processes
- Concurrency > 1 on spam_detection worker
- Manual API calls outside task system

**Solution**
```bash
# Verify worker concurrency
docker logs spam_detection_worker | grep "concurrency"
# Should show: concurrency=1

# Check rate limiter usage
redis-cli GET "spam_detection:api_rate_limit:*"

# Reduce other API activity
# Stop manual testing or competing services
```

### Task Timeouts

**Symptom**: Tasks timeout after 10 seconds

**Causes**
- API is slow (>5s per call)
- Rate limiter waiting (can be 60s)
- Database slow on updates

**Solution**
```python
# Increase Celery timeout
CELERY_TASK_TIME_LIMIT = 300  # 5 minutes
CELERY_TASK_SOFT_TIME_LIMIT = 240  # 4 minutes warning

# Or increase task-specific timeout
result = enrich_user_features_tier2.delay('User').get(timeout=30)
```

### Database Updates Failing

**Symptom**: Enrichment returns success but database not updated

**Causes**
- `update_tier2_features()` method not on repository
- Database connection closed
- Transaction rolled back

**Solution**
```python
# Verify repository method exists
with uow.start() as uow:
    hasattr(uow.spam_features, 'update_tier2_features')

# Check database logs
mysql -u root < check_errors.sql

# Manually verify features stored
SELECT username, account_age_days FROM user_spam_features WHERE username='TestUser';
```

---

## Integration Points

### With Existing Systems

1. **Ingest Pipeline**: Tier 2 enrichment runs after Tier 1 features computed
2. **Scoring Engine**: Enhanced scores use Tier 2 data when available
3. **Monitoring**: Circuit breaker state exposed via metrics
4. **Admin API**: Manual enrichment endpoint for testing

### Data Flow

```
New Post Ingested
  ├─ track_author_activity (Tier 1 data collection)
  ├─ compute_user_spam_features_tier1 (basic analysis)
  ├─ score_user (Tier 1 score)
  │
  └─ On daily schedule:
     ├─ analyze_top_reposters
     ├─ enrich_high_risk_users (Tier 2 enrichment)
     └─ score_user_with_tier2 (enhanced score)
```

---

## Testing

### Unit Tests

```bash
cd /home/barry/PycharmProjects/RedditRepostSleuth
pytest tests/core/services/spam/test_circuit_breaker.py
pytest tests/core/services/spam/test_rate_limiter.py
pytest tests/core/services/spam/test_user_data_fetcher.py
```

### Integration Tests (requires Reddit API)

```python
import pytest

@pytest.mark.integration
@pytest.mark.skip(reason="Requires real Reddit API")
def test_fetch_real_user():
    from redditrepostsleuth.core.services.spam.user_data_fetcher import UserDataFetcher

    fetcher = UserDataFetcher(reddit, uowm)
    features = fetcher.fetch_basic_user_data('reddit')  # Public test account

    assert features is not None
    assert features.account_suspended is False
    assert features.account_age_days > 365
```

### Manual Testing

```python
from redditrepostsleuth.core.celery.tasks.spam_detection_tasks import enrich_user_features_tier2

# Test with public account
result = enrich_user_features_tier2.delay('reddit').get(timeout=10)

print("Features:", result)
assert result['account_suspended'] is False
assert result['account_age_days'] > 365
```

---

## Monitoring & Metrics

### Prometheus Metrics (if enabled)

```python
spam_detection_circuit_breaker_state = Gauge(
    'spam_detection_circuit_breaker_state',
    'Circuit breaker state (0=CLOSED, 1=OPEN, 2=HALF_OPEN)'
)

spam_detection_rate_limit_used = Gauge(
    'spam_detection_rate_limit_used',
    'API calls used this minute'
)

spam_detection_enrichment_duration = Histogram(
    'spam_detection_enrichment_duration_seconds',
    'Time to enrich single user'
)
```

### Log Patterns to Watch

```
# Normal operation
[INFO] Enriching Tier 2 features for: User123
[DEBUG] Successfully fetched data for User123
[INFO] Updated Tier 2 features for User123

# Rate limiting
[WARNING] Rate limit exceeded: 51/50
[INFO] Rate limit hit, waiting 45.3s

# Circuit breaker open
[WARNING] Circuit breaker OPEN after 5 consecutive failures
[INFO] Circuit breaker entering HALF_OPEN state
[INFO] Circuit breaker CLOSED - API recovered
```

---

## FAQ

**Q: How many API calls per user?**

A: 1-11 calls depending on profile scanning:
- Basic data: 1 call (required)
- Profile description: 1 call (included in basic)
- Recent comments: 1 call per iteration (up to 10 comments)
- Total: ~2-3 calls per user typically

**Q: Can I run multiple workers for faster enrichment?**

A: Not recommended. Single worker enforces rate limiting effectively. Multiple workers would require distributed rate limiter or hit 429s.

**Q: What happens if Reddit API goes down?**

A: Circuit breaker opens after 5 failures. System falls back to Tier 1-only scoring automatically. Recovery is attempted every 60 seconds.

**Q: Can I increase the rate limit to 60 requests/min?**

A: Conservative approach is 50/min. Only increase after monitoring for 2 weeks shows no 429 errors, and only to 55/min max.

**Q: How long does caching last?**

A: 24 hours by default (configurable). After 24 hours, next enrichment triggers fresh API fetch.

**Q: Can I enrich all users at once?**

A: No, use `enrich_high_risk_users` in batches (limit=50-100). Daily enrichment handles priority users.

---

## References

### Code Locations

| Component | Path |
|-----------|------|
| Circuit Breaker | `redditrepostsleuth/core/services/spam/circuit_breaker.py` |
| Rate Limiter | `redditrepostsleuth/core/services/spam/rate_limiter.py` |
| Tier 2 Features | `redditrepostsleuth/core/services/spam/tier2_features.py` |
| User Data Fetcher | `redditrepostsleuth/core/services/spam/user_data_fetcher.py` |
| Celery Tasks | `redditrepostsleuth/core/celery/tasks/spam_detection_tasks.py` |

### External Documentation

- [PRAW Documentation](https://praw.readthedocs.io/)
- [Reddit API Rate Limits](https://github.com/reddit-archive/reddit/wiki/API#api-rules)
- [Circuit Breaker Pattern](https://martinfowler.com/bliki/CircuitBreaker.html)
- [Redis Documentation](https://redis.io/documentation)

---

**Document Version**: 1.0
**Last Updated**: January 2024
**Status**: Complete - Phase 3 Implementation
