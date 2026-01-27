# Spam Detection System - Phase 2 Scoring Engine Reference

## Overview

The Phase 2 Spam Scoring Engine is a rule-based system that converts Tier 1 behavioral features into a unified spam risk score (0.0-1.0). The engine uses a conservative, additive approach designed for explainability and tunability.

**Core Philosophy:**

- **Conservative:** Defaults to LOW risk unless strong evidence exists for higher classifications
- **Explainable:** Every score contribution has a human-readable reason
- **Tunable:** All weights, thresholds, and confidence calculations are configurable
- **Additive:** Multiple signals combine to increase confidence (no single signal determines outcome)
- **No Caps Until Final:** Individual signals can exceed maximum, capped only at final score (1.0)

**Current Status:** Phase 2 implementation complete with Tier 1 feature support. Phase 3 Tier 2 enrichment extends scoring with Reddit API data.

---

## Scoring Algorithm

### Formula

```
final_score = min(1.0, sum(component_scores))

where component_scores includes:
  - repost_behavior_score
  - adult_platform_score
  - posting_patterns_score
  - username_pattern_score
  - karma_farming_score
  - supporting_signals_score
```

### Calculation Process

```
1. Extract Tier 1 features for user
   └─ Query author_activity_tracking, repost counts, patterns

2. Score each signal independently
   ├─ Repost behavior (0.0-0.35)
   ├─ Adult platform promotion (0.0-0.35)
   ├─ Posting patterns (0.0-0.20)
   ├─ Username pattern (0.0-0.12)
   ├─ Karma farming (0.0-0.30)
   └─ Supporting signals (0.0-0.15)

3. Sum all component scores
   └─ Uncapped addition (can exceed 1.0)

4. Cap final score
   └─ min(1.0, sum) ensures 0.0-1.0 range

5. Calculate confidence
   └─ Based on post count and data availability

6. Classify risk level
   └─ Map score to LOW/MEDIUM/HIGH/CRITICAL

7. Return ScoringResult
   └─ score, confidence, risk_level, reasons, component_scores
```

### Key Design Principle: Additive Scoring

Each signal contributes independently. A user can trigger multiple signals, each adding to the final score:

```python
# Example user with multiple concerning factors
user_score = 0.0

# Signal 1: High repost ratio
user_score += 0.25  # Running total: 0.25

# Signal 2: Adult platform links detected
user_score += 0.25  # Running total: 0.50

# Signal 3: Suspicious username
user_score += 0.12  # Running total: 0.62

# Signal 4: Karma farming posts
user_score += 0.20  # Running total: 0.82

# Signal 5: Short promo links
user_score += 0.08  # Running total: 0.90

# Final cap
final_score = min(1.0, 0.90)  # Result: 0.90 (CRITICAL)
```

This approach ensures that multiple corroborating signals increase confidence in the classification.

---

## Signal Categories

### Signal 1: Repost Behavior (0.0 - 0.35)

**Weight Range:** 0.0 to 0.35 (maximum single contribution)

**Thresholds:**
| Repost Ratio | Weight | Risk Indicator |
|--------------|--------|----------------|
| >= 70% | 0.35 | CRITICAL - Primary spam behavior |
| 50-69% | 0.25 | HIGH - Strong indication |
| 30-49% | 0.15 | MEDIUM - Elevated activity |
| < 30% | 0.0 | Normal range |

**Interpretation:**
- **70%+ reposts:** Account primarily posts duplicates of existing content. High automation indicator.
- **50-69% reposts:** More than half of posts are reposts. Strong spam signal.
- **30-49% reposts:** Significant repost activity, combined with other signals creates concern.
- **Below 30%:** Normal content distribution for legitimate users.

**Configuration:**
```python
repost_ratio_critical: float = 0.70
repost_ratio_high: float = 0.50
repost_ratio_medium: float = 0.30

repost_weight_critical: float = 0.35
repost_weight_high: float = 0.25
repost_weight_medium: float = 0.15
```

**Code Location:** `SpamScorer._score_repost_behavior()`

**Example:**
```python
features = extract_features('UserName')
# User has 100 posts, 75 are reposts
# repost_ratio = 0.75

# Score calculation:
if ratio >= 0.70:
    score = 0.35  # Maximum weight for this signal
    reason = "Critical repost ratio: 75.0% of posts are reposts"
```

---

### Signal 2: Adult Platform Promotion (0.0 - 0.35)

**Weight Range:** 0.0 to 0.35

**Thresholds:**
| Adult Link Ratio | Weight | Indicator |
|-----------------|--------|-----------|
| >= 50% | 0.35 | CRITICAL - Primarily adult content |
| 20-49% | 0.25 | HIGH - Frequent promotion |
| 1-19% | 0.10 | LOW - Detected but infrequent |
| 0% | 0.0 | No detection |

**Detected Platforms:**
- OnlyFans, Fansly, FanCentro, ManyVids
- Pornhub (model/user profiles), XVideos (channels)
- Cam platforms: Chaturbate, MyFreeCams, Stripchat, Cam4
- Booking platforms: BongaCams, LiveJasmin, Streamate, CamSoda
- Creator platforms: LoyalFans, AdmireMe, Frisk.chat

**Configuration:**
```python
adult_ratio_critical: float = 0.50
adult_ratio_high: float = 0.20
adult_ratio_low: float = 0.01  # Any detection

adult_weight_critical: float = 0.35
adult_weight_high: float = 0.25
adult_weight_low: float = 0.10
```

**Code Location:** `SpamScorer._score_adult_platform()`

**Example:**
```python
features = extract_features('UserName')
# User has 30 posts, 10 link to OnlyFans (ratio = 0.33)

if ratio >= 0.20:
    score = 0.25
    reason = "Adult platform links detected: 33.3% (OnlyFans)"
```

---

### Signal 3: Posting Patterns (0.0 - 0.20)

**Weight Range:** 0.0 to 0.20

**Components:**

#### 3a. Posting Frequency

| Posts/Day | Weight | Indicator |
|-----------|--------|-----------|
| >= 15.0 | 0.20 | CRITICAL - Likely bot/automation |
| 10.0-14.9 | 0.15 | HIGH - Unusually frequent |
| 5.0-9.9 | 0.08 | MEDIUM - Elevated activity |
| < 5.0 | 0.0 | Normal range |

**Interpretation:**
- **15+ posts/day:** Almost certainly automated. Average human cannot sustain this.
- **10-14 posts/day:** Highly suspicious, suggests coordinated posting.
- **5-9 posts/day:** Active user, but worth noting in combination with other signals.
- **Below 5:** Normal human activity level.

#### 3b. Subreddit Diversity

**Trigger:** Only evaluated with 20+ total posts (minimum data threshold)

**Signal:** Posts to < 3 unique subreddits

**Weight:** +0.12 if triggered

**Interpretation:**
- Very concentrated posting (all in 2-3 communities)
- Suggests targeted promotion/spam rather than organic participation
- Less suspicious if user legitimately focuses on specific topics

**Configuration:**
```python
low_diversity_threshold: int = 3
min_posts_for_diversity: int = 20
```

**Code Location:** `SpamScorer._score_posting_patterns()`

**Example:**
```python
features = extract_features('UserName')
# User has 45 posts across 2 subreddits: FreeKarma4U (30), AutoKarma (15)
# unique_subreddits = 2 < 3, total_posts = 45 >= 20

# Score additions:
if ppd >= 5.0:
    score += 0.08  # Elevated frequency
if total_posts >= 20 and unique_subreddits < 3:
    score += 0.12  # Low diversity
# Total from posting patterns: 0.20
```

**Configuration:**
```python
posts_per_day_critical: float = 15.0
posts_per_day_high: float = 10.0
posts_per_day_elevated: float = 5.0

posting_weight_critical: float = 0.20
posting_weight_high: float = 0.15
posting_weight_elevated: float = 0.08
```

---

### Signal 4: Username Pattern (0.0 - 0.12)

**Weight Range:** 0.0 to 0.12

**Detected Patterns:**

| Pattern | Confidence | Weight |
|---------|-----------|--------|
| Reddit auto-generated | 0.85 | 0.12 |
| CamelCase + digits | 0.70 | 0.12 |
| word_word_numbers | 0.65 | 0.12 |
| Random alphanumeric | 0.55 | 0.12 |
| Crypto/NFT prefixes | 0.25 | 0.08 |
| Promo/deal prefixes | 0.30 | 0.08 |
| Repeated characters | 0.35 | 0.08 |

**Examples:**
- **Reddit auto-generated:** `Adorable_Fox_1234`, `Happy_Tiger_5678`
- **CamelCase + digits:** `MobileUserXyz123`, `PromoBot2024`
- **word_word_numbers:** `user_name_1234`, `crypto_trader_9999`
- **Random alphanumeric:** `abc123def456`

**Legitimate Exceptions:**
- Throwaway accounts: `throwaway123`, `alt_account`
- Year suffixes: `username2024`
- Standard Reddit format: `some_user_name`

**Configuration:**
```python
username_pattern_weight: float = 0.12
```

**Code Location:**
- Detection: `redditrepostsleuth/core/services/spam/username_patterns.py`
- Scoring: `SpamScorer._score_username_pattern()`

**Example:**
```python
features = extract_features('Happy_Tiger_5678')
# Pattern matches: reddit_autogenerated (confidence 0.85)
# is_suspicious = True

score = 0.12
reason = "Suspicious username pattern: Reddit auto-generated format"
```

---

### Signal 5: Karma Farming Subreddit Participation (0.0 - 0.30)

**Weight Range:** 0.0 to 0.30 (scaled by post count)

**Calculation:**
```python
if karma_farming_posts > 0:
    score = min(
        karma_farm_weight_max,      # 0.30
        karma_posts * weight_per_post  # per-post scaling
    )
```

**Configured Values:**
```python
karma_farm_weight_per_post: float = 0.05  # 5% per post
karma_farm_weight_max: float = 0.30       # Cap at 30%
```

**Known Karma Farming Subreddits:**
- `FreeKarma4U`, `FreeKarma4Everyone`
- `AutoKarma`, `Karma4U`
- `EasyKarma`, `QuickKarma`
- `KarmaFarm`, `KarmaFarming`

**Interpretation:**
| Posts | Score | Meaning |
|-------|-------|---------|
| 0 | 0.0 | Not engaging with karma farms |
| 1-2 | 0.05-0.10 | Minimal karma farming |
| 3-5 | 0.15-0.25 | Moderate engagement |
| 6+ | 0.30 | Heavy karma farming focus |

**Code Location:** `SpamScorer._score_karma_farming()`

**Example:**
```python
features = extract_features('UserName')
# User has 7 posts in karma farming subreddits

karma_posts = 7
score = min(0.30, 7 * 0.05)  # min(0.30, 0.35)
score = 0.30  # Capped

reason = "Karma farming subreddit posts: 7"
```

**Database Source:**
Karma farming subreddits are identified in the `spam_subreddit_list` table with `category='karma_farming'`. The list is cached for 1 hour in SpamFeatureExtractor.

---

### Signal 6: Supporting Signals (0.0 - 0.15)

**Weight Range:** 0.0 to 0.15 (combined from sub-signals)

**Components:**

#### 6a. Short/Promo Links

| Short Link Ratio | Weight | Indicator |
|------------------|--------|-----------|
| > 30% | 0.08 | HIGH - Primary use is link redirection |
| 2-3 posts | 0.05 | MEDIUM - Multiple short links |
| 0 | 0.0 | None detected |

**Detected Link Shorteners:**
- Bit.ly, TinyURL, Goo.gl, T.co (Twitter)
- Ow.ly, Is.gd, Buff.ly, Adf.ly
- **Link aggregators:** Linktr.ee, Beacons.ai, AllMyLinks, Linkin.bio, Campsite.bio
- **Newer services:** Snipfeed, Koji, Tap.bio, Hoo.be

**Interpretation:**
- Regular users rarely use shortened links
- Promotional accounts use link aggregators to hide multiple redirects
- High short link ratio suggests coordinated promotion

#### 6b. NSFW + Adult Platform Combo

| Condition | Weight |
|-----------|--------|
| NSFW ratio > 50% AND Adult links > 10% | 0.15 |
| Either condition alone | 0.0 |

**Interpretation:**
- NSFW content combined with adult platform links = strong promotional indicator
- This combo suggests explicit adult content promotion
- Weight added only when BOTH conditions met (synergistic signal)

**Configuration:**
```python
short_link_weight: float = 0.08
nsfw_adult_combo_weight: float = 0.15
```

**Code Location:** `SpamScorer._score_supporting_signals()`

**Example 1: Short Links**
```python
features = extract_features('UserName')
# User has 20 posts, 8 use short links (ratio = 0.40)

if ratio > 0.30:
    score += 0.08
    reasons.append("High promo link ratio: 40.0%")
```

**Example 2: NSFW + Adult Combo**
```python
features = extract_features('UserName')
# User: 60% NSFW posts, 25% adult platform links

if nsfw_ratio > 0.5 and adult_ratio > 0.1:
    score += 0.15
    reasons.append("NSFW content + adult platform promotion pattern")
```

---

## Risk Levels

Risk levels are determined by final score and provide intuitive classifications.

### Classification Thresholds

```
Risk Level    Score Range    Interpretation
─────────────────────────────────────────────────
CRITICAL      >= 0.80        Confirmed or high-confidence spam
HIGH          0.60 - 0.79    Strong spam indicators
MEDIUM        0.30 - 0.59    Moderate concerns, warrants review
LOW           < 0.30         Normal activity or insufficient data
```

**Configuration:**
```python
risk_critical_threshold: float = 0.80
risk_high_threshold: float = 0.60
risk_medium_threshold: float = 0.30
```

**Code Location:** `SpamScorer._classify_risk()`

### Risk Level Characteristics

**CRITICAL (0.80-1.0)**
- Multiple strong signals (3+ major factors)
- High repost ratio (70%+) OR high adult promotion (50%+)
- Likely automated spam account
- Recommended action: Remove/suspend after verification
- Example: 0.80+ score from repost (0.35) + adult promotion (0.25) + posting patterns (0.15) + username pattern (0.12)

**HIGH (0.60-0.79)**
- Multiple concerning signals (2+ moderate factors)
- Repost ratio 50-69% OR adult links 20-49%
- Suspicious but not definitive
- Recommended action: Flag for manual review
- Example: 0.70 score from repost (0.25) + karma farming (0.25) + posting frequency (0.15) + supporting signals (0.05)

**MEDIUM (0.30-0.59)**
- One or two concerning factors
- Repost ratio 30-49% OR elevated posting frequency
- Ambiguous; legitimate users can trigger these
- Recommended action: Monitor for pattern escalation
- Example: 0.45 score from elevated posting frequency (0.15) + username pattern (0.12) + low diversity (0.12) + short links (0.08)

**LOW (< 0.30)**
- Minimal concerning signals
- Normal activity pattern
- Likely legitimate user
- No action needed unless escalated by other systems
- Example: Score < 0.20 from single weak signal or no signals

---

## Confidence Calculation

Confidence reflects how much data is available to support the score. More data = higher confidence.

### Confidence Tiers (by post count)

```
Post Count    Base Confidence    Interpretation
─────────────────────────────────────────────────
100+          0.95               Very high confidence
50-99         0.85               High confidence
20-49         0.70               Moderate confidence
10-19         0.55               Fair confidence
5-9           0.40               Low confidence
<5            0.25               Very low confidence
```

**Configuration:**
```python
# Confidence thresholds (in SpamScorer._calculate_confidence)
if posts >= 100: base_confidence = 0.95
elif posts >= 50: base_confidence = 0.85
elif posts >= 20: base_confidence = 0.70
elif posts >= 10: base_confidence = 0.55
elif posts >= 5: base_confidence = 0.40
else: base_confidence = 0.25
```

### Confidence Boosters

**Repost Data Boost:** +0.05 (up to 0.98 max)
- If user has any detected reposts, add 5% confidence
- Reason: Repost detection is highly reliable
- Cannot exceed 0.98 (leave margin for unknown factors)

**Code Location:** `SpamScorer._calculate_confidence()`

### Interpretation

- **0.90+:** Score is very reliable; act on it
- **0.70-0.89:** Score is fairly reliable; reasonable for review/action
- **0.50-0.69:** Score has meaningful signal but limited data; use with caution
- **< 0.50:** Score based on very little data; treat as preliminary only

---

## Celery Tasks Reference

### Task: score_user_spam(username)

**Location:** `redditrepostsleuth/core/celery/tasks/spam_detection_tasks.py`

**Purpose:** Extract features, calculate score, and store results

**Signature:**
```python
@celery.task(bind=True, base=SpamDetectionTask, ...)
def score_user_spam(self, username: str) -> Optional[dict]:
    """
    Score a user for spam likelihood.

    Returns: Dict with scoring results or None if insufficient data
    """
```

**Configuration:**
```python
retry: 3 attempts, 60 second intervals
queue: spam_detection
serializer: pickle
ignore_results: False  # We want the score result
```

**Returns:**
```python
{
    'score': 0.75,                    # Final score (0.0-1.0)
    'confidence': 0.85,               # Confidence (0.0-1.0)
    'risk_level': 'HIGH',             # CRITICAL/HIGH/MEDIUM/LOW
    'reasons': [
        'High repost ratio: 60.0% of posts are reposts',
        'Adult platform links detected: 25.0% (OnlyFans)',
        'Elevated posting frequency: 8.5 posts/day'
    ],
    'component_scores': {
        'repost_behavior': 0.25,
        'adult_platform': 0.25,
        'posting_patterns': 0.15,
        'username_pattern': 0.0,
        'karma_farming': 0.10,
        'supporting_signals': 0.0
    }
}
```

**Usage:**
```python
# Direct call (not async)
from redditrepostsleuth.core.celery.tasks.spam_detection_tasks import score_user_spam

result = score_user_spam('UserName')

# Or via Celery (async)
from redditrepostsleuth.core.celery.tasks.spam_detection_tasks import score_user_spam

task = score_user_spam.delay('UserName')
result = task.get()  # Wait for result
```

---

### Task: score_and_flag_user(username, update_user_review=True)

**Location:** `redditrepostsleuth/core/celery/tasks/spam_detection_tasks.py`

**Purpose:** Score user and optionally create/update UserReview entry

**Signature:**
```python
@celery.task(bind=True, base=SpamDetectionTask, ...)
def score_and_flag_user(
    self,
    username: str,
    update_user_review: bool = True
) -> Optional[dict]:
```

**Configuration:**
```python
retry: 3 attempts, 60 second intervals
queue: spam_detection
update_user_review: Updates UserReview table by default
```

**Returns:** Same as score_user_spam()

**Database Updates (if update_user_review=True):**
```python
# Updates or creates UserReview entry with:
- spam_score: The calculated score
- spam_score_confidence: Confidence value
- spam_score_updated_at: Current timestamp
- risk_level: Risk classification
```

**Usage:**
```python
# Main entry point for spam detection pipeline
result = score_and_flag_user('SuspiciousUser', update_user_review=True)

if result['risk_level'] == 'CRITICAL':
    # Take immediate action
    notify_admins(result)
elif result['risk_level'] == 'HIGH':
    # Flag for manual review
    send_to_review_queue(result)
```

---

### Task: batch_score_users(usernames)

**Location:** `redditrepostsleuth/core/celery/tasks/spam_detection_tasks.py`

**Purpose:** Score multiple users efficiently

**Signature:**
```python
@celery.task(bind=True, base=SpamDetectionTask, ...)
def batch_score_users(self, usernames: List[str]) -> dict:
```

**Returns:**
```python
{
    'total': 50,              # Total users requested
    'scored': 45,             # Successfully scored
    'skipped': 3,             # Insufficient data
    'failed': 2,              # Errors during scoring
    'high_risk': 12,          # Count of HIGH risk
    'critical_risk': 4        # Count of CRITICAL risk
}
```

**Usage:**
```python
users = ['User1', 'User2', 'User3', ..., 'User50']
result = batch_score_users(users)

print(f"Scored {result['scored']}/{result['total']} users")
print(f"Critical: {result['critical_risk']}, High: {result['high_risk']}")
```

**Performance:**
- Processes ~5-10 users/second per worker
- Suitable for batches of 100-1000+ users
- Each user independently scored (no shared state)

---

### Task: score_top_reposters(limit=100, days=30, min_reposts=5)

**Location:** `redditrepostsleuth/core/celery/tasks/spam_detection_tasks.py`

**Purpose:** Score users with most reposts for spam detection

**Signature:**
```python
@celery.task(bind=True, base=SpamDetectionTask, ...)
def score_top_reposters(
    self,
    limit: int = 100,
    days: int = 30,
    min_reposts: int = 5
) -> dict:
```

**Parameters:**
- `limit`: Maximum users to analyze (default 100)
- `days`: Look-back period for repost detection (default 30)
- `min_reposts`: Minimum reposts to qualify (default 5)

**Returns:**
```python
{
    'analyzed': 87,           # Users successfully analyzed
    'total': 100,             # Total found with criteria
}
```

**Algorithm:**
```
1. Query repost table for top N authors by repost count
   - Filter: reposts from past `days` days
   - Filter: author != None and '[deleted]'
   - Filter: repost_count >= min_reposts
   - Limit: top N by count

2. For each user:
   - Check if recently scored (< 7 days)
   - If not scored or > 7 days old, add to batch

3. Batch score all users needing updates
   - Uses batch_score_users internally
```

**Usage:**
```python
# Daily job to analyze top reposters
result = score_top_reposters.delay(
    limit=100,
    days=30,
    min_reposts=5
)

# Or use lower thresholds for more frequent analysis
result = score_top_reposters.delay(
    limit=50,
    days=7,
    min_reposts=2
)
```

**Schedule Example (Celery Beat):**
```python
from celery.schedules import crontab

app.conf.beat_schedule = {
    'score-top-reposters-daily': {
        'task': 'redditrepostsleuth.core.celery.tasks.spam_detection_tasks.score_top_reposters',
        'schedule': crontab(hour=2, minute=0),  # 2 AM daily
        'args': (100, 30, 5)
    },
}
```

---

## Redis Cache

The `SpamDetectionCache` provides distributed caching for spam scores and features.

### Cache Interface

**Location:** `redditrepostsleuth/core/services/spam/spam_cache.py`

**Initialization:**
```python
from redditrepostsleuth.core.services.spam.spam_cache import SpamDetectionCache
import redis

redis_client = redis.Redis(host='localhost', port=6379, db=0)
cache = SpamDetectionCache(redis_client, ttl_seconds=3600)
```

### Methods

#### get_user_features(username) -> Optional[Dict]

Retrieve cached Tier 1 features for a user.

**Cache Key Format:** `spam:features:v{version}:{username_lower}`

**TTL:** 1 hour (default)

**Returns:** Feature dict or None if expired/missing

```python
features = cache.get_user_features('UserName')
if features:
    print(f"Cached: {features['total_posts_indexed']} posts")
else:
    print("Not in cache, need to extract")
```

#### set_user_features(username, features, ttl_seconds=None)

Store Tier 1 features in cache.

```python
from redditrepostsleuth.core.services.spam.spam_feature_extractor import SpamFeatureExtractor

extractor = SpamFeatureExtractor(uowm)
features = extractor.extract_tier1_features('UserName')

if features:
    cache.set_user_features('UserName', features.to_dict())
```

#### get_user_score(username) -> Optional[Dict]

Retrieve cached spam score result.

**Cache Key Format:** `spam:score:v{version}:{username_lower}`

```python
score_result = cache.get_user_score('UserName')
if score_result:
    print(f"Score: {score_result['score']}, Risk: {score_result['risk_level']}")
```

#### set_user_score(username, score_result, ttl_seconds=None)

Store spam score in cache.

```python
scorer = SpamScorer(uowm)
result = scorer.score_user(features)

cache.set_user_score('UserName', result.to_dict())
```

#### invalidate_user(username) -> bool

Invalidate all cached data for a user.

Useful when user data changes or scores are updated.

```python
# After manual review updates the user
cache.invalidate_user('UserName')
```

#### invalidate_all() -> bool

Invalidate all spam detection cache.

Call when scoring weights change significantly.

```python
# After updating ScoringConfig thresholds
cache.invalidate_all()  # Increments version
```

#### get_cache_key_count() -> int

Get approximate number of cached spam detection keys.

Useful for monitoring cache size.

```python
count = cache.get_cache_key_count()
print(f"Cached users: {count}")
```

### Cache Strategy

**Key Format:**
```
spam:{type}:v{version}:{username_lower}

Types:
- features: Tier 1 feature extraction results
- score: Spam score and classification
```

**Version Invalidation:**
Instead of clearing Redis, increment the cache version to atomically invalidate all cached data:

```python
cache.version = 1  # Increments to 2
# All old keys (v1:*) become orphaned
# New keys use v2:*
```

**Benefits:**
- No need to clear Redis
- Atomic invalidation across distributed workers
- Old keys naturally expire via TTL

---

## User Review Integration

The `UserReview` table stores manual review decisions and spam scores for training data.

### Database Model

**Location:** `redditrepostsleuth/core/db/databasemodels.py`

**Key Columns:**
```python
username: str              # Primary key
spam_score: float          # Calculated spam score (0.0-1.0)
spam_score_confidence: float  # Confidence in score
spam_score_updated_at: datetime  # When score was last updated
risk_level: str            # CRITICAL/HIGH/MEDIUM/LOW
is_verified_spam: bool     # Manually verified as spam
is_verified_legit: bool    # Manually verified as legitimate
last_checked: datetime     # When manually reviewed
notes: str                 # Admin notes
```

### Repository Methods

**Location:** `redditrepostsleuth/core/db/repository/user_review_repo.py`

#### get_high_risk_users(min_score=0.6, limit=100)

Get users with spam scores above threshold.

**Returns:** List of UserReview objects

```python
from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager

with uowm.start() as uow:
    high_risk = uow.user_review.get_high_risk_users(
        min_score=0.75,
        limit=50
    )

    for user in high_risk:
        print(f"{user.username}: {user.spam_score} ({user.risk_level})")
```

#### get_users_needing_review(limit=100)

Get flagged users not yet verified.

**Criteria:**
- spam_score >= 0.6
- is_verified_spam == False
- is_verified_legit == False

**Returns:** List of users needing manual review

```python
users_to_review = uow.user_review.get_users_needing_review(limit=100)
for user in users_to_review:
    print(f"Review {user.username}: {user.risk_level}")
```

#### mark_verified_spam(username)

Mark user as verified spam after manual review.

**Returns:** True if successful

```python
with uowm.start() as uow:
    success = uow.user_review.mark_verified_spam('ConfirmedSpammer')
    if success:
        print("Marked as verified spam")
```

#### mark_verified_legit(username)

Mark user as verified legitimate after manual review.

**Returns:** True if successful

```python
with uowm.start() as uow:
    success = uow.user_review.mark_verified_legit('FalsePositive')
    if success:
        print("Marked as verified legitimate")
```

#### get_verified_spam_users(limit=100)

Get all users manually verified as spam.

Used for training data collection.

```python
with uowm.start() as uow:
    verified = uow.user_review.get_verified_spam_users(limit=1000)

    # Export for ML training
    for user in verified:
        export_training_data(user)
```

#### get_verified_legit_users(limit=100)

Get all users manually verified as legitimate.

Used for training data collection (negative examples).

```python
with uowm.start() as uow:
    verified = uow.user_review.get_verified_legit_users(limit=1000)

    # Use as negative examples in training
    for user in verified:
        add_negative_example(user)
```

### Workflow Example

```python
# 1. Score user
result = score_and_flag_user('SuspiciousUser')
print(f"Score: {result['score']}, Risk: {result['risk_level']}")

# 2. Get flagged users for review
with uowm.start() as uow:
    users = uow.user_review.get_users_needing_review(limit=20)

# 3. Admin reviews each user
for user in users:
    # Manual investigation happens here
    decision = admin_review(user)

# 4. Mark verified decision
with uowm.start() as uow:
    if decision == 'spam':
        uow.user_review.mark_verified_spam('UserName')
    elif decision == 'legit':
        uow.user_review.mark_verified_legit('UserName')
    uow.commit()

# 5. Later: Extract training data
with uowm.start() as uow:
    spam_users = uow.user_review.get_verified_spam_users(limit=5000)
    legit_users = uow.user_review.get_verified_legit_users(limit=5000)

    # Use for training ML models
    train_spam_classifier(spam_users, legit_users)
```

---

## Usage Examples

### Example 1: Score a Single User

```python
from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.db.db_utils import get_db_engine
from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.core.services.spam.spam_feature_extractor import SpamFeatureExtractor
from redditrepostsleuth.core.services.spam.spam_scorer import SpamScorer

# Initialize
config = Config()
engine = get_db_engine(config)
uowm = UnitOfWorkManager(engine)

# Extract features
extractor = SpamFeatureExtractor(uowm)
features = extractor.extract_tier1_features('TargetUser')

if not features:
    print("Insufficient data for user")
    exit()

# Score user
scorer = SpamScorer(uowm)
result = scorer.score_user(features)

# Display results
print(f"Username: TargetUser")
print(f"Score: {result.score:.3f}")
print(f"Confidence: {result.confidence:.2f}")
print(f"Risk Level: {result.risk_level}")
print(f"\nComponent Scores:")
for component, score in result.component_scores.items():
    print(f"  {component}: {score:.3f}")
print(f"\nReasons:")
for reason in result.reasons:
    print(f"  - {reason}")
```

### Example 2: Batch Score Top Reposters

```python
from redditrepostsleuth.core.celery.tasks.spam_detection_tasks import score_top_reposters

# Schedule async task
task = score_top_reposters.delay(
    limit=100,        # Top 100 reposters
    days=30,          # From last 30 days
    min_reposts=5     # With 5+ reposts
)

# Wait for results
results = task.get()

print(f"Analyzed: {results['analyzed']}")
print(f"Total found: {results['total']}")

# Get high-risk users from database
with uowm.start() as uow:
    high_risk = uow.user_review.get_high_risk_users(min_score=0.75)

    for user in high_risk:
        print(f"\n{user.username}")
        print(f"  Score: {user.spam_score:.3f}")
        print(f"  Risk: {user.risk_level}")
        print(f"  Needs Review: {user.is_verified_spam is None}")
```

### Example 3: Manual Review and Verification

```python
# Get users flagged for review
with uowm.start() as uow:
    users_to_review = uow.user_review.get_users_needing_review(limit=10)

# Review each user
for user in users_to_review:
    print(f"\n{'='*60}")
    print(f"User: {user.username}")
    print(f"Spam Score: {user.spam_score:.3f}")
    print(f"Risk Level: {user.risk_level}")
    print(f"Reasons: {user.notes if user.notes else 'None'}")

    # Get full feature data
    features = uow.spam_features.get_by_username(user.username)
    if features and features.feature_data:
        print(f"Total Posts: {features.feature_data.get('total_posts_indexed')}")
        print(f"Repost Ratio: {features.feature_data.get('repost_ratio'):.1%}")

    # Admin decision
    decision = input("Decision (spam/legit/skip): ").lower()

    if decision == 'spam':
        uow.user_review.mark_verified_spam(user.username)
        print(f"Marked {user.username} as verified spam")
    elif decision == 'legit':
        uow.user_review.mark_verified_legit(user.username)
        print(f"Marked {user.username} as verified legitimate")

    uow.commit()
```

### Example 4: Caching and Performance

```python
from redditrepostsleuth.core.services.spam.spam_cache import SpamDetectionCache
import redis

# Initialize cache
redis_client = redis.Redis(host='localhost', port=6379, db=0)
cache = SpamDetectionCache(redis_client, ttl_seconds=3600)

# First call: Compute and cache
username = 'TargetUser'
score = cache.get_user_score(username)

if not score:
    # Not cached, compute
    result = score_user_spam(username)
    score = result.to_dict()

    # Store in cache
    cache.set_user_score(username, score)
    print(f"Computed and cached score for {username}")
else:
    print(f"Retrieved cached score for {username}")

print(f"Score: {score['score']}, Risk: {score['risk_level']}")

# Later: Cache hit
score2 = cache.get_user_score(username)
print(f"Cache hit: {score2['score']}")
```

### Example 5: Custom Scoring Configuration

```python
from redditrepostsleuth.core.services.spam.spam_scorer import SpamScorer, ScoringConfig

# Create custom config with stricter thresholds
custom_config = ScoringConfig(
    # More aggressive on repost ratio
    repost_ratio_critical=0.60,    # Instead of 0.70
    repost_weight_critical=0.40,   # Instead of 0.35

    # More sensitive to adult content
    adult_ratio_high=0.10,         # Instead of 0.20
    adult_weight_high=0.30,        # Instead of 0.25

    # Stricter posting patterns
    posts_per_day_high=8.0,        # Instead of 10.0
    posting_weight_high=0.20,      # Instead of 0.15

    # Lower risk thresholds
    risk_high_threshold=0.50,      # Instead of 0.60
    risk_medium_threshold=0.20,    # Instead of 0.30
)

# Use custom config
scorer = SpamScorer(uowm, config=custom_config)
result = scorer.score_user(features)

print(f"Custom scoring: {result.score} ({result.risk_level})")
```

---

## Tuning Guidelines

### When to Adjust Weights

**Increase Weight If:**
- Signal too frequently missed (false negatives)
- Signal very reliable with low false positive rate
- Data quality improved (more posts tracked)

**Decrease Weight If:**
- Too many false positives
- Signal less predictive than expected
- Too many legitimate users flagged

### Common Adjustments

#### Sensitivity Adjustment

Adjust risk thresholds to balance precision/recall:

```python
# More sensitive (catch more spam, more false positives)
config.risk_high_threshold = 0.50      # Lower threshold
config.risk_medium_threshold = 0.25

# More conservative (fewer false positives, miss some spam)
config.risk_high_threshold = 0.70      # Raise threshold
config.risk_medium_threshold = 0.40
```

#### Signal Rebalancing

If one signal triggers too often:

```python
# If adult platform too sensitive
config.adult_weight_high = 0.15        # Reduce from 0.25
config.adult_weight_low = 0.05         # Reduce from 0.10

# If repost ratio flags too many
config.repost_ratio_high = 0.60        # Raise from 0.50
config.repost_weight_high = 0.20       # Lower from 0.25
```

#### Threshold Fine-Tuning

Adjust when legitimate users at certain thresholds:

```python
# If legitimate users have 3-5 karma farming posts
config.karma_farm_weight_per_post = 0.03    # Lower from 0.05

# If legitimate users post 12+ times/day
config.posts_per_day_high = 12.0            # Raise from 10.0
```

### Testing Adjustments

Before applying changes:

1. **Test on historical data:**
```python
# Rescore all high-risk users with new config
new_config = ScoringConfig(...)
new_scorer = SpamScorer(uowm, config=new_config)

with uowm.start() as uow:
    users = uow.user_review.get_high_risk_users()
    for user in users:
        features = uow.spam_features.get_by_username(user.username)
        if features:
            new_result = new_scorer.score_user(features)
            print(f"{user.username}: {user.spam_score:.2f} -> {new_result.score:.2f}")
```

2. **Calculate impact metrics:**
```python
# How many users moved risk levels?
reclassified = sum(1 for u in users if old_risk(u) != new_risk(u))
print(f"Reclassified: {reclassified}/{len(users)}")

# How do verified users score?
verified_spam = uow.user_review.get_verified_spam_users()
avg_verified = sum(new_scorer.score_user(f).score
                   for f in features_for(verified_spam)) / len(verified_spam)
print(f"Avg verified spam score: {avg_verified:.2f}")
```

3. **Apply incrementally:**
```python
# Update config in code
updated_config = ScoringConfig(risk_high_threshold=0.55)

# Rescore recent users first
recent = uow.spam_features.get_recent(limit=100)

# Monitor results for issues

# Rollout to full system once validated
```

### Monitoring Effectiveness

Track scoring effectiveness over time:

```python
# Calculate precision/recall on verified users
with uowm.start() as uow:
    verified_spam = set(u.username
                        for u in uow.user_review.get_verified_spam_users())
    verified_legit = set(u.username
                         for u in uow.user_review.get_verified_legit_users())

    # Scoring: How many verified spam scored HIGH/CRITICAL?
    true_positives = 0
    false_negatives = 0

    for username in verified_spam:
        result = score_user_spam(username)
        if result['risk_level'] in ['HIGH', 'CRITICAL']:
            true_positives += 1
        else:
            false_negatives += 1

    recall = true_positives / (true_positives + false_negatives)
    print(f"Recall on verified spam: {recall:.1%}")

    # False positive rate
    false_positives = 0
    true_negatives = 0

    for username in verified_legit:
        result = score_user_spam(username)
        if result['risk_level'] in ['HIGH', 'CRITICAL']:
            false_positives += 1
        else:
            true_negatives += 1

    fpr = false_positives / (false_positives + true_negatives)
    print(f"False positive rate on verified legit: {fpr:.1%}")
```

---

## Code Locations

| Component | File | Lines | Purpose |
|-----------|------|-------|---------|
| Spam Scorer | `redditrepostsleuth/core/services/spam/spam_scorer.py` | 531 | Rule-based scoring engine |
| ScoringConfig | `redditrepostsleuth/core/services/spam/spam_scorer.py` | 50-104 | Configuration dataclass |
| ScoringResult | `redditrepostsleuth/core/services/spam/spam_scorer.py` | 18-46 | Result dataclass |
| Cache | `redditrepostsleuth/core/services/spam/spam_cache.py` | 210 | Redis cache layer |
| Tasks (Scoring) | `redditrepostsleuth/core/celery/tasks/spam_detection_tasks.py` | 670-917 | Celery scoring tasks |
| User Review Repo | `redditrepostsleuth/core/db/repository/user_review_repo.py` | 79 | Database methods |
| Feature Extractor | `redditrepostsleuth/core/services/spam/spam_feature_extractor.py` | 413 | Tier 1 feature extraction |

---

## Integration with Phase 3 Tier 2 Enrichment

Phase 3 extends Phase 2 scoring with Reddit API data.

### Tier 2 Feature Scoring

The `SpamScorerWithTier2` class combines Tier 1 and Tier 2 scores:

```python
# Additional signals from Tier 2:
- Account suspension (0.50) - Confirmed spam
- Account age (0.08-0.15) - Very new accounts suspicious
- Karma ratio (0.05-0.10) - Low karma suspicious
- Email verification (0.05) - No verified email
- Custom avatar (0.03) - Default avatar
- Adult profile links (0.20) - Links in bio/comments
- Telegram links (0.15) - Off-platform communication
```

### Tier 2 Implementation

```python
from redditrepostsleuth.core.services.spam.spam_scorer import SpamScorerWithTier2

scorer = SpamScorerWithTier2(uowm)

# After Tier 2 enrichment:
tier2_result = scorer.score_with_tier2(tier1_features, tier2_features)
# Produces enhanced score with 10% confidence boost
```

See `/docs/SpamDetection/FinalDocs/tier2-enrichment-usage.md` for complete Tier 2 documentation.

---

## Performance Characteristics

### Scoring Latency

| Operation | Time | Notes |
|-----------|------|-------|
| Extract Tier 1 features | 200-500ms | Depends on post count |
| Calculate score | 5-10ms | Very fast (in-memory) |
| Cache lookup | 1-5ms | Redis latency |
| Store to database | 20-50ms | Single insert/update |
| Total per-user | 230-560ms | Dominated by feature extraction |

### Throughput

| Configuration | Users/Second | Notes |
|----------------|-------------|-------|
| Single worker | 2-5 | ~240ms per user |
| 10 workers | 20-50 | Good for batch jobs |
| 50 workers | 100-250 | For high-volume processing |

### Database Impact

| Query | Time | Frequency |
|-------|------|-----------|
| Feature extraction | 300-400ms | Per scoring |
| Database update | 20-50ms | Per scoring |
| Batch operations | ~5ms/user | Much more efficient |

### Optimization Tips

1. **Use batch scoring** when processing multiple users
2. **Enable caching** to avoid recomputing recent scores
3. **Filter users** before batch jobs (only score when necessary)
4. **Use multiple workers** for parallelization
5. **Invalidate cache** only when config changes (not per-user)

---

## Troubleshooting

### Issue: Score too high/low compared to manual review

**Solutions:**
1. Review component scores to identify dominant signal
2. Check threshold values in ScoringConfig
3. Validate feature extraction accuracy
4. Compare against verified training data

### Issue: Too many false positives (LOW users flagged as CRITICAL)

**Solutions:**
1. Reduce individual signal weights
2. Increase risk level thresholds
3. Check if thresholds don't match data distribution
4. Review component scores for unexpected values

### Issue: Missing true positives (HIGH risk users not detected)

**Solutions:**
1. Increase signal weights
2. Lower risk level thresholds
3. Add new signals for missed patterns
4. Review verified spam users for common features

### Issue: Cache inconsistency

**Solutions:**
1. Invalidate user cache manually
2. Increment version to clear all cache
3. Check Redis connection status
4. Verify TTL values are appropriate

---

## Conclusion

The Phase 2 Spam Scoring Engine provides a transparent, tunable scoring system based on behavioral signals. The rule-based approach ensures explainability while allowing flexible adjustment based on observed performance.

Key characteristics:
- **Conservative defaults:** LOW risk unless strong evidence
- **Additive scoring:** Multiple weak signals create stronger classifications
- **Configurable:** All thresholds and weights adjustable
- **Explainable:** Every score includes human-readable reasons
- **Scalable:** Processes 100+ users/second with distributed workers

---

## References

### Related Documentation
- [Spam Detection Flow](spam-detection-flow.md) - Complete system architecture
- [Tier 2 Enrichment](tier2-enrichment-usage.md) - API-based feature enhancement
- [Implementation Progress](implementation-progress.md) - Project status

### Code Files
- Scoring: `redditrepostsleuth/core/services/spam/spam_scorer.py`
- Cache: `redditrepostsleuth/core/services/spam/spam_cache.py`
- Tasks: `redditrepostsleuth/core/celery/tasks/spam_detection_tasks.py`
- Features: `redditrepostsleuth/core/services/spam/spam_feature_extractor.py`
- Database: `redditrepostsleuth/core/db/repository/user_review_repo.py`
