# Spam Detection System - Complete Flow Documentation

## Overview

The Repost Sleuth Spam Detection System is a multi-phase, distributed architecture designed to identify and analyze spam and promotional accounts on Reddit. The system works with zero API calls to Reddit (after initial post ingestion) by analyzing existing database records and extracting behavioral patterns indicative of spam activity.

**Key Goals:**
- Detect promotional and spam accounts through behavioral analysis
- Identify high-risk reposters for moderator review
- Build a foundation for future machine learning-based classification
- Scale horizontally using Celery distributed task processing
- Maintain performance without requiring additional API quota

**Current Implementation Status:** Phase 3 (Tier 2 Enrichment) - Reddit API Integration Complete

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────────────────┐
│                        REDDIT POST INGESTION                             │
│                    (Existing Ingest Pipeline)                            │
└────────────────────────────────┬─────────────────────────────────────────┘
                                 │
                                 ▼
        ┌────────────────────────────────────────────┐
        │  1. TRACK AUTHOR ACTIVITY (Phase 0)         │
        │     - Post metadata extraction              │
        │     - URL pattern detection                 │
        │     - Store in author_activity_tracking DB  │
        └────────────┬─────────────────────────────────┘
                     │
                     ▼
        ┌────────────────────────────────────────────┐
        │  2. EXTRACT TIER 1 FEATURES (Phase 1)       │
        │     - Compute behavioral features           │
        │     - Username pattern analysis             │
        │     - Store in user_spam_features DB        │
        └────────────┬─────────────────────────────────┘
                     │
                     ▼
        ┌────────────────────────────────────────────┐
        │  3. FUTURE PHASES (2-6)                     │
        │     - Scoring engines                       │
        │     - Tier 2 enrichment                     │
        │     - Trigger integration                   │
        │     - ML training data preparation          │
        │     - ML model training & scoring           │
        └────────────────────────────────────────────┘
```

---

## Phase 0: Data Collection Flow

### Purpose
Establish lightweight author activity tracking for all posts ingested into the system. This foundation captures raw behavioral signals that will feed all subsequent analysis phases.

### Data Ingestion Path

#### Step 1: Post Ingestion (Existing Process)
When a new post is discovered from Reddit:
1. Post metadata is extracted by the ingest service (via PRAW)
2. Post is stored in the `post` table with full metadata
3. Task `track_author_activity` is enqueued in the `spam_detection` queue

#### Step 2: Author Activity Tracking Task

**Task:** `track_author_activity` (Celery Task)
- **Queue:** `spam_detection`
- **Retry:** 3 retries with 60-second intervals
- **Idempotency:** Checks if post already tracked before inserting

**Function Signature:**
```python
def track_author_activity(
    post_id: str,
    author: str,
    subreddit: str,
    url: Optional[str],
    is_nsfw: bool,
    post_type_id: int,
    created_at_iso: str
) -> None
```

**Input Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `post_id` | str | Reddit post ID (15 chars max) |
| `author` | str | Reddit username |
| `subreddit` | str | Target subreddit name |
| `url` | str or None | Post URL (if applicable) |
| `is_nsfw` | bool | Whether post is marked NSFW |
| `post_type_id` | int | Post type: 1=text, 2=image, 3=link |
| `created_at_iso` | str | ISO format timestamp |

**Processing Logic:**
```
1. Skip if author is None or '[deleted]'
2. Parse created_at from ISO format (fallback to UTC now on error)
3. Detect adult platform links using ADULT_PLATFORM_PATTERNS
4. Detect URL shorteners using SHORT_LINK_PATTERNS
5. Create AuthorActivityTracking record
6. Check idempotency (prevent duplicates)
7. Store in database with commit
```

### URL Pattern Detection

> **Important Note:** Phase 0/1 adult link detection is **post-URL only**. This means only URLs directly embedded in the post are scanned. User comments, bio, and profile links are **not** analyzed in this phase. Comprehensive multi-source detection (comments, bio, profile, landing page deep scanning) is planned for Phase 3 Tier 2 Enrichment. See [Phase 3 Preview](#phase-3-tier-2-enrichment) for details.
>
> The existing `adult_promoter` detection system in `onlyfans_handling.py` continues to operate for monitored subreddits and provides real-time comprehensive checking including comments and profile analysis. The new spam detection system is designed to build a feature foundation for ML-based classification rather than real-time action.

#### Adult Platform Detection
The system identifies URLs linking to adult content platforms:

**Detected Platforms:**
- OnlyFans, Fansly, FanCentro, ManyVids
- Pornhub (model/user profiles), XVideos (channels)
- Cam platforms: Chaturbate, MyFreeCams, Stripchat, Cam4
- Booking platforms: BongaCams, LiveJasmin, Streamate, CamSoda
- Creator platforms: LoyalFans, AdmireMe, Frisk.chat

**Pattern Type:** Regex-based matching (case-insensitive)
**Storage:** `has_adult_link` boolean in `author_activity_tracking`

#### URL Shortener Detection
Identifies link aggregators and redirect services:

**Detected Services:**
- Bit.ly, TinyURL, Goo.gl, T.co
- Ow.ly, Is.gd, Buff.ly, Adf.ly
- Link aggregators: Linktr.ee, Beacons.ai, AllMyLinks, Linkin.bio
- Newer services: Snipfeed, Koji, Campsite.bio

**Pattern Type:** Regex-based matching (case-insensitive)
**Storage:** `has_short_link` boolean in `author_activity_tracking`

### author_activity_tracking Table Schema

**Purpose:** Lightweight record of each post and author behavior signals

**Table Structure:**
```sql
CREATE TABLE author_activity_tracking (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    post_id VARCHAR(15) NOT NULL UNIQUE,
    author VARCHAR(25) NOT NULL,
    subreddit VARCHAR(25) NOT NULL,
    created_at DATETIME NOT NULL,
    post_type_id TINYINT NOT NULL,
    is_nsfw BOOLEAN DEFAULT FALSE,
    has_adult_link BOOLEAN DEFAULT FALSE,
    has_short_link BOOLEAN DEFAULT FALSE,
    tracked_at DATETIME DEFAULT UTC_TIMESTAMP(),

    INDEX idx_author_created (author, created_at),
    INDEX idx_author_subreddit (author, subreddit),
    INDEX idx_created_at (created_at)
);
```

**Column Descriptions:**

| Column | Type | Purpose |
|--------|------|---------|
| `id` | BIGINT | Unique record identifier |
| `post_id` | VARCHAR(15) | Reddit post ID (unique) |
| `author` | VARCHAR(25) | Reddit username |
| `subreddit` | VARCHAR(25) | Target subreddit |
| `created_at` | DATETIME | Post creation timestamp (UTC) |
| `post_type_id` | TINYINT | 1=text, 2=image, 3=link |
| `is_nsfw` | BOOLEAN | Post marked NSFW? |
| `has_adult_link` | BOOLEAN | URL points to adult platform? |
| `has_short_link` | BOOLEAN | URL uses shortener service? |
| `tracked_at` | DATETIME | When record was created |

**Indexes:**
- `idx_author_created`: Fast queries by author + time (most common query pattern)
- `idx_author_subreddit`: Analyze author subreddit distribution
- `idx_created_at`: Find posts within time range

**Data Characteristics:**
- Immutable after creation (writes only)
- Row count: ~1 billion+ (one per Reddit post indexed)
- Growth rate: ~50-100k/day
- Used by: Phase 1 feature extraction

---

## Phase 1: Feature Extraction Flow (Tier 1)

### Purpose
Extract behavioral and pattern-based features from existing author activity records and reposts. These features form the basis for spam detection scoring.

### Feature Extraction Pipeline

#### Overview
The `SpamFeatureExtractor` service analyzes all available data about a user to compute 50+ features covering:
- Activity metrics (post counts, frequency)
- Content patterns (NSFW, adult links, shorteners)
- Subreddit behavior (distribution, concentration)
- Temporal patterns (posting times, entropy, bursts)
- Username patterns (suspicious naming conventions)

#### Key Components

**1. SpamFeatureExtractor Service**

Location: `redditrepostsleuth/core/services/spam/spam_feature_extractor.py`

**Responsibilities:**
- Extract all Tier 1 features for a user
- Compute behavioral metrics from activity data
- Analyze username patterns
- Store features in database
- Cache spam subreddit list (1-hour TTL)

**Key Methods:**

```python
class SpamFeatureExtractor:
    def __init__(self, uowm: UnitOfWorkManager) -> None

    def is_user_worth_analyzing(username: str) -> bool
        """Check if user has minimum 3 posts for analysis."""

    def check_username_pattern(username: str) -> Tuple[bool, float, List[str]]
        """Analyze username for suspicious patterns."""
        Returns: (is_suspicious, confidence, matched_patterns)

    def extract_subreddit_behavior(username: str) -> dict
        """Get subreddit distribution and concentration metrics."""

    def get_activity_timeline(username: str) -> dict
        """Analyze posting timeline for patterns and intervals."""

    def extract_tier1_features(username: str) -> Optional[Tier1Features]
        """Extract all Tier 1 features."""
        Returns: Tier1Features object or None if insufficient data

    def store_features(features: Tier1Features) -> bool
        """Store features to user_spam_features table."""

    def extract_and_store(username: str) -> Optional[Tier1Features]
        """Extract and immediately store features."""
```

**2. Tier1Features Dataclass**

Holds all extracted features for a user:

```python
@dataclass
class Tier1Features:
    # Basic activity metrics
    username: str
    total_posts_indexed: int
    total_reposts_detected: int
    repost_ratio: float
    unique_subreddits_posted: int
    posts_per_day_avg: float
    first_post_date: Optional[datetime]
    last_post_date: Optional[datetime]
    account_age_days: int
    nsfw_post_count: int
    nsfw_post_ratio: float
    summons_received: int

    # Adult platform / promotional link metrics
    adult_platform_post_count: int
    adult_platform_ratio: float
    short_link_post_count: int
    short_link_ratio: float
    detected_platforms: List[str]

    # Username pattern metrics
    username_suspicious_pattern: bool
    username_pattern_confidence: float
    username_pattern_matches: List[str]

    # Subreddit behavior metrics
    subreddit_distribution: Dict[str, int]
    subreddit_concentration_hhi: float  # Herfindahl-Hirschman Index
    karma_farming_sub_posts: int
    easy_karma_sub_posts: int
    spam_subreddit_posts: int

    # Posting pattern metrics
    max_posts_per_day: int
    posting_entropy: float
    burst_posting_detected: bool
    avg_time_between_posts_minutes: float
```

### Feature Categories

#### 1. Basic Activity Metrics

**Computed From:** `author_activity_tracking` table

| Feature | Calculation | Interpretation |
|---------|-----------|-----------------|
| `total_posts_indexed` | COUNT of all posts | Volume of activity |
| `total_reposts_detected` | COUNT of matching reposts | Repost frequency |
| `repost_ratio` | reposts / total_posts | 0.0-1.0, higher = more reposts |
| `unique_subreddits_posted` | DISTINCT subreddit count | Spread across communities |
| `posts_per_day_avg` | total_posts / account_age_days | Activity velocity |
| `account_age_days` | MAX(created_at) - MIN(created_at) | Time span of posts |
| `nsfw_post_count` | COUNT where is_nsfw=true | NSFW content volume |
| `nsfw_post_ratio` | nsfw_count / total_posts | 0.0-1.0, higher = more NSFW |
| `summons_received` | COUNT from summons table | User mentions by bot |

**High Risk Indicators:**
- Repost ratio > 0.5 (50%+ of posts are reposts)
- NSFW ratio > 0.7 (70%+ NSFW content)
- Posting velocity > 50 posts/day (automated behavior)

#### 2. Adult Platform & Promotional Link Metrics

**Computed From:** `author_activity_tracking.has_adult_link`, `has_short_link`

| Feature | Calculation | Interpretation |
|---------|-----------|-----------------|
| `adult_platform_post_count` | COUNT where has_adult_link=true | Posts linking to adult sites |
| `adult_platform_ratio` | adult_count / total_posts | 0.0-1.0 |
| `short_link_post_count` | COUNT where has_short_link=true | Posts with link aggregators |
| `short_link_ratio` | short_link_count / total_posts | 0.0-1.0 |
| `detected_platforms` | List of matched platform names | Which adult platforms linked |

**High Risk Indicators:**
- Adult platform ratio > 0.2 (20%+ adult links)
- Short link ratio > 0.3 (30%+ URL shorteners)
- Adult links + short links combined > 0.4

#### 3. Username Pattern Analysis

**Analyzer:** `redditrepostsleuth/core/services/spam/username_patterns.py`

**Pattern Categories:**

| Category | Examples | Confidence Weight |
|----------|----------|-------------------|
| Reddit auto-generated | `Adorable_Fox_1234` | 0.85 (Very High) |
| Camel case + digits | `MobileUserXyz123` | 0.70 (High) |
| Lowercase + underscore + digits | `user_name_1234` | 0.65 (High) |
| Random alphanumeric | `abc123def456` | 0.55 (Medium) |
| Crypto/NFT prefixes | `crypto_trader_x` | 0.25 (Low) |
| Promo/deal prefixes | `deal_finder_bot` | 0.30 (Low) |
| Repeated characters | `userrrr_name` | 0.35 (Low) |

**Features Computed:**

| Feature | Calculation |
|---------|-----------|
| `username_suspicious_pattern` | Boolean: confidence >= 0.5 |
| `username_pattern_confidence` | Float: 0.0-1.0 (normalized weight) |
| `username_pattern_matches` | List: all matched pattern names |

**Legitimate Pattern Exceptions** (negative weights):
- Throwaway accounts: `throwaway123`, `alt_account`
- Year suffixes: `username2024`
- Standard Reddit format: `some_user_name`

**High Risk Indicators:**
- Confidence >= 0.7 (Very suspicious username)
- Multiple pattern matches (>3 patterns matched)

#### 4. Subreddit Behavior Metrics

**Computed From:** `author_activity_tracking.subreddit` distribution

**Analysis Methods:**

1. **Subreddit Distribution**
   - Count posts per subreddit
   - Returns dict: `{subreddit_name: post_count}`
   - Reveals if user targets specific communities

2. **Concentration Index (HHI)**
   ```
   HHI = Σ(market_share^2) where market_share = posts_in_sub / total_posts

   Range: 0.0 to 1.0
   - 0.0 = perfectly distributed (many subs, few posts each)
   - 1.0 = concentrated in one sub (all posts in one place)
   - 0.5 = moderate concentration (few subs, many posts each)
   ```

   **Interpretation:**
   - HHI > 0.7: Highly concentrated (targeting specific communities)
   - HHI > 0.9: Extreme concentration (single subreddit focus)

3. **Spam Subreddit Detection**
   - Maintains list of known spam/karma farming subreddits
   - Categories: `karma_farming`, `easy_karma`, `spam_network`
   - Counts posts in each category
   - 1-hour cache TTL for performance

**Features Computed:**

| Feature | Type | Meaning |
|---------|------|---------|
| `subreddit_distribution` | Dict | Posts per subreddit |
| `subreddit_concentration_hhi` | Float | 0.0-1.0 concentration |
| `karma_farming_sub_posts` | Int | Posts in karma farming subs |
| `easy_karma_sub_posts` | Int | Posts in easy karma subs |
| `spam_subreddit_posts` | Int | Total posts in spam subs |

**High Risk Indicators:**
- HHI > 0.8 (very concentrated posting)
- Spam subreddit posts > 5
- Karma farming + easy karma > 20% of all posts

#### 5. Posting Pattern Metrics

**Computed From:** `author_activity_tracking.created_at` timeline

**Analysis Metrics:**

1. **Daily Posting Volume**
   - Count posts per day
   - Find maximum posts in single day
   - Feature: `max_posts_per_day`
   - High value (>20) suggests automation

2. **Posting Entropy** (Shannon Entropy)
   ```
   Entropy = -Σ(p_i * log2(p_i))
   where p_i = posts_in_hour_i / total_posts

   Normalized by log2(24) to 0.0-1.0 scale

   Interpretation:
   - 0.0 = all posts same hour (highly regular/automated)
   - 1.0 = evenly distributed across hours (random/natural)
   ```

3. **Burst Detection**
   - Count posts per hour
   - Detect if > 10 posts in single hour
   - Boolean flag: `burst_posting_detected`
   - Indicates automated posting sessions

4. **Average Interval Between Posts**
   ```
   intervals = [(post_i+1.created_at - post_i.created_at)
                for all consecutive posts]
   avg_interval_minutes = mean(intervals)
   ```
   - Low values (< 5 minutes) suggest automation
   - High values (> 1440 minutes) suggest sporadic user

**Features Computed:**

| Feature | Type | Interpretation |
|---------|------|-----------------|
| `max_posts_per_day` | Int | Peak daily activity |
| `posting_entropy` | Float | 0.0-1.0 randomness |
| `burst_posting_detected` | Bool | >10 posts/hour detected |
| `avg_time_between_posts_minutes` | Float | Minutes between posts |

**High Risk Indicators:**
- Entropy < 0.3 (very regular/automated pattern)
- Burst detected = true
- Max posts/day > 20
- Avg interval < 10 minutes (rapid fire posting)

### Feature Extraction Workflow

```
1. Validation
   ├─ Check if user has minimum 3 posts
   ├─ Skip if user is None or '[deleted]'
   └─ Return None if insufficient data

2. Basic Activity Metrics
   ├─ Query author_activity_tracking table
   ├─ Count total posts, reposts, NSFW, adult links, short links
   └─ Calculate ratios and averages

3. Username Pattern Analysis
   ├─ Apply pattern regex matching
   ├─ Compute confidence score
   └─ Return suspicious status and matched patterns

4. Subreddit Behavior
   ├─ Query subreddit distribution
   ├─ Calculate HHI concentration
   ├─ Check against spam subreddit list (cached)
   └─ Count posts in each spam category

5. Activity Timeline
   ├─ Fetch all posts (up to 500)
   ├─ Sort by created_at
   ├─ Calculate daily/hourly distributions
   ├─ Compute entropy, burst detection, intervals
   └─ Determine account age and PPD

6. Storage
   └─ Store all features in user_spam_features table
      with full feature_data JSON blob
```

### user_spam_features Table Schema

**Purpose:** Store computed Tier 1 features for users, indexed for quick retrieval

**Table Structure:**
```sql
CREATE TABLE user_spam_features (
    username VARCHAR(25) PRIMARY KEY NOT NULL UNIQUE,
    spam_score FLOAT NULL,
    spam_score_confidence FLOAT NULL,
    computed_at DATETIME DEFAULT UTC_TIMESTAMP() NOT NULL,

    total_posts INT DEFAULT 0,
    nsfw_post_count INT DEFAULT 0,
    nsfw_post_ratio FLOAT NULL,
    unique_subreddit_count INT DEFAULT 0,
    adult_link_count INT DEFAULT 0,
    short_link_count INT DEFAULT 0,
    spam_subreddit_count INT DEFAULT 0,
    avg_posts_per_day FLOAT NULL,
    max_posts_per_day INT NULL,

    feature_data JSON NULL,

    INDEX idx_spam_score (spam_score),
    INDEX idx_computed_at (computed_at)
);
```

**Column Descriptions:**

| Column | Type | Purpose |
|--------|------|---------|
| `username` | VARCHAR(25) | Reddit username (PK) |
| `spam_score` | FLOAT | Future: overall spam confidence (0.0-1.0) |
| `spam_score_confidence` | FLOAT | Future: confidence in score |
| `computed_at` | DATETIME | When features were last computed |
| `total_posts` | INT | Denormalized: total posts |
| `nsfw_post_count` | INT | Denormalized: NSFW posts |
| `nsfw_post_ratio` | FLOAT | Denormalized: NSFW ratio |
| `unique_subreddit_count` | INT | Denormalized: subreddit diversity |
| `adult_link_count` | INT | Denormalized: adult platform links |
| `short_link_count` | INT | Denormalized: URL shortener links |
| `spam_subreddit_count` | INT | Denormalized: posts in spam subs |
| `avg_posts_per_day` | FLOAT | Denormalized: average PPD |
| `max_posts_per_day` | INT | Denormalized: peak PPD |
| `feature_data` | JSON | Complete Tier1Features as JSON |

**Design Notes:**
- Username as composite primary key (one record per user)
- Denormalized columns for fast filtering/sorting
- Complete `feature_data` JSON for historical queries
- Indexed on spam_score and computed_at for sorting/filtering

**Data Characteristics:**
- Row count: ~100k-1M (actively indexed users)
- Growth rate: Users analyzed on demand or batches
- Updated: Replaced entirely when recomputed (not incremental)
- Used by: Phase 2 scoring, Phase 3+ enrichment

---

## Celery Tasks Reference

### Task: track_author_activity

**Location:** `redditrepostsleuth/core/celery/tasks/spam_detection_tasks.py`

**Configuration:**
```python
@celery.task(
    bind=True,
    base=SpamDetectionTask,
    ignore_results=True,
    serializer='pickle',
    autoretry_for=(Exception,),
    retry_kwargs={'max_retries': 3, 'countdown': 60}
)
```

**Queue:** `spam_detection`
**Retry:** 3 attempts with 60-second intervals
**Result Handling:** Ignore (fire-and-forget)

**Usage:**
```python
# Enqueue from post ingestion
track_author_activity.delay(
    post_id='abc123def45',
    author='SomeUser',
    subreddit='AskReddit',
    url='https://t.co/xyz123',
    is_nsfw=False,
    post_type_id=3,
    created_at_iso='2024-01-25T12:34:56'
)
```

### Task: compute_user_spam_features_tier1

**Location:** `redditrepostsleuth/core/celery/tasks/spam_detection_tasks.py`

**Configuration:**
```python
@celery.task(
    bind=True,
    base=SpamDetectionTask,
    ignore_results=True,
    serializer='pickle',
    autoretry_for=(Exception,),
    retry_kwargs={'max_retries': 3, 'countdown': 60}
)
```

**Purpose:** Compute and store Tier 1 spam features for a single user

**Returns:** Dict of features (or None if insufficient data)

**Usage:**
```python
# Process single user
result = compute_user_spam_features_tier1.delay('UserName')

# Returns:
{
    'username': 'UserName',
    'total_posts_indexed': 42,
    'repost_ratio': 0.33,
    'posting_entropy': 0.7,
    # ... all other Tier1Features fields
}
```

**Error Handling:**
- Max 3 retries on exception
- Logs errors with username
- Does not block other processing

### Task: batch_compute_spam_features

**Location:** `redditrepostsleuth/core/celery/tasks/spam_detection_tasks.py`

**Purpose:** Compute features for multiple users efficiently

**Returns:** Dict with counts
```python
{
    'success_count': 45,
    'failure_count': 2,
    'skipped_count': 3
}
```

**Usage:**
```python
# Process batch of users
usernames = ['User1', 'User2', 'User3', ...]
result = batch_compute_spam_features.delay(usernames)
```

**Features:**
- Single SpamFeatureExtractor instance (efficient reuse)
- Skips None, '[deleted]', empty strings
- Continues on individual user failures
- Logs summary statistics

**Scale:** Can handle 100-1000+ users per task

### Task: analyze_top_reposters

**Location:** `redditrepostsleuth/core/celery/tasks/spam_detection_tasks.py`

**Purpose:** Identify and analyze top reposters for spam patterns

**Parameters:**
```python
def analyze_top_reposters(
    self,
    limit: int = 100,      # Max users to analyze
    days: int = 30         # Look-back period
) -> dict
```

**Returns:** Dict with analysis results
```python
{
    'analyzed_count': 87,           # Users successfully analyzed
    'high_risk_count': 23           # Users flagged as high risk
}
```

**High Risk Criteria:**
```python
if (repost_ratio > 0.5 or
    username_suspicious_pattern or
    spam_subreddit_posts > 5):
    # Mark as high risk
```

**Usage:**
```python
# Analyze top 100 reposters from last 30 days
result = analyze_top_reposters.delay(limit=100, days=30)
```

**Algorithm:**
```
1. Query top reposters from repost table
   - Filter by created_at >= (now - days)
   - Sort by repost count descending
   - Limit to N users

2. For each reposter:
   - Extract Tier 1 features
   - Check high-risk criteria
   - Increment counters

3. Return summary statistics
```

### Task: cleanup_old_feature_records

**Location:** `redditrepostsleuth/core/celery/tasks/spam_detection_tasks.py`

**Purpose:** Clean up old feature records (currently no-op)

**Note:** UserSpamFeatures uses username as primary key, so one record per user. This task is a placeholder for future historical tracking versions.

**Returns:** Dict with deletion count (currently 0)
```python
{
    'deleted_count': 0
}
```

---

## Database Schema Summary

### Tables Used

#### 1. author_activity_tracking
- **Rows:** ~1 billion+ (all indexed posts)
- **Purpose:** Raw post-level activity data
- **Key Indexes:** author+created_at, author+subreddit, created_at
- **Fields:** 11 columns (lightweight, immutable)

#### 2. user_spam_features
- **Rows:** ~100k-1M (computed users)
- **Purpose:** Cached feature extraction results
- **Key Indexes:** spam_score, computed_at
- **Fields:** 14 columns + JSON feature blob
- **Update Mode:** Replace entire record (not incremental)

#### 3. spam_subreddit_list (Reference)
- **Rows:** ~500-1000 (manually curated)
- **Purpose:** Known spam/karma farm subreddit catalog
- **Categories:** karma_farming, easy_karma, spam_network, etc.
- **Maintenance:** Manual updates by admins

#### 4. repost (Existing Table)
- Used to count author reposts
- Query: `count_reposts_by_author(username)`

#### 5. summons (Existing Table)
- Used to count bot mentions
- Query: `count_by_post_author(username)`

#### 6. post (Existing Table)
- Base posts table
- Used to retrieve all posts by author

### Database Relationships

```
author_activity_tracking
├─ many-to-one → post (via post_id)
└─ many-to-many → authors (via author)

user_spam_features
├─ one-to-many → author_activity_tracking (via username)
├─ one-to-many → repost (via author)
└─ many-to-many → spam_subreddit_list (via subreddit_distribution)

spam_subreddit_list
└─ one-to-many → author_activity_tracking (via subreddit)
```

---

## Data Flow Examples

### Example 1: New Post Ingestion

```
Timeline: Post found at 12:00 UTC

12:00:00 - Ingest service finds new post
12:00:01 - Post stored in 'post' table
12:00:02 - track_author_activity task enqueued
           Arguments: post_id='abc1d2e3f4g5h6i7', author='PromoBob',
                     subreddit='memes', url='https://bit.ly/promo123',
                     is_nsfw=false, post_type_id=3, created_at_iso='2024-01-25T12:00:00'

12:00:05 - Celery worker picks up task
12:00:06 - Detects has_short_link=true (bit.ly match)
12:00:07 - Creates AuthorActivityTracking record
12:00:08 - Record committed to database

12:00:10 - Task complete

Future: compute_user_spam_features_tier1('PromoBob') can now analyze all tracked posts
```

### Example 2: Feature Extraction on Demand

```
Timeline: Admin requests analysis of user 'SuspiciousUser'

14:30:00 - Admin triggers compute_user_spam_features_tier1('SuspiciousUser')
14:30:01 - Task starts, SpamFeatureExtractor initialized
14:30:02 - Query author_activity_tracking for SuspiciousUser
           Result: 127 posts found

14:30:03 - Compute basic metrics
           total_posts=127, repost_count=68, repost_ratio=0.535

14:30:04 - Analyze username pattern
           Pattern match: 'reddit_auto_adjective_noun_number'
           Confidence: 0.85, is_suspicious=true

14:30:05 - Extract subreddit behavior
           Distribution: {memes: 45, FreeKarma4U: 32, AutoKarma: 50}
           HHI: 0.28 (moderate spread)

14:30:06 - Analyze posting timeline
           Post span: 45 days, max_posts_per_day=18
           Entropy: 0.35 (automated pattern)
           Burst detected: true (23 posts in one hour)

14:30:07 - Check spam subreddits
           Posts in FreeKarma4U (easy_karma): 32
           Posts in AutoKarma (karma_farming): 50
           Total spam_subreddit_posts: 82

14:30:08 - Create Tier1Features dataclass with all computed values
14:30:09 - Store in user_spam_features table
14:30:10 - Return features dict with all metrics

Result: Feature extraction complete, ready for Phase 2 scoring
```

### Example 3: Batch Analysis of Top Reposters

```
Timeline: Scheduled batch job runs daily

06:00:00 - Scheduler triggers analyze_top_reposters(limit=100, days=30)
06:00:01 - Query repost table for top 100 authors in last 30 days
           Result: [(User1, 45 reposts), (User2, 38 reposts), ...]

06:00:05 - For each user:
           ├─ User1: Extract features
           │  └─ repost_ratio=0.62 (HIGH), spam_sub_posts=8 (HIGH)
           │     → Flag as HIGH RISK
           ├─ User2: Extract features
           │  └─ repost_ratio=0.31 (normal), spam_sub_posts=2
           │     → Normal risk
           ├─ User3: Extract features
           │  └─ repost_ratio=0.28 (normal), spam_pattern_confidence=0.8
           │     → Flag as HIGH RISK
           └─ ...100 users processed

06:15:00 - Summary:
           analyzed_count: 98
           high_risk_count: 23
           (2 users skipped due to errors)

06:15:01 - Task complete, results logged
```

---

## Integration Points

### Input Sources
1. **Post Ingestion** → track_author_activity task
2. **Celery Beat Scheduler** → Periodic batch analyses
3. **Admin API** → Manual feature computation

### Output Consumers (Future Phases)
1. **Phase 2: Scoring Engine** - Consumes Tier1Features
2. **Phase 3: Tier 2 Enrichment** - Enriches with external data
3. **Phase 4: Trigger Integration** - Automated actions
4. **Phase 5: Training Data** - ML dataset preparation
5. **Phase 6: ML Model** - Trains on features
6. **Web Interface** - Display features and flags
7. **Admin Tools** - Manual review interface

### External Dependencies
1. **Database** - MySQL with SQLAlchemy ORM
2. **Unit of Work Manager** - Database access abstraction
3. **Redis/Celery** - Task queue and distribution
4. **Configuration** - Config class for settings

---

## Performance Characteristics

### Database Operations

**author_activity_tracking:**
- INSERT: 1-2ms (per post)
- SELECT by author: 50-100ms (typical 100 posts)
- SELECT subreddit distribution: 150-300ms
- Total indexed rows: 1B+, growth: 50-100k/day

**user_spam_features:**
- SELECT all features: 5-10ms
- UPDATE/INSERT: 20-50ms
- Total rows: 100k-1M, growth: variable

**Typical Feature Extraction Time:** 200-500ms per user
- Database queries: 300-400ms
- Processing: 50-100ms
- Storage: 20-50ms

### Scaling Characteristics

**Single Celery Worker:**
- Tracks ~1000 posts/second (track_author_activity)
- Analyzes ~5-10 users/second (compute_user_spam_features_tier1)
- Processes ~500 users in batch (batch_compute_spam_features)

**With 10 Workers:**
- Tracks ~10,000 posts/second
- Analyzes ~50-100 users/second
- Can handle 5000+ users in batch

### Storage Requirements

**author_activity_tracking:**
- ~100 bytes per row
- 1B rows = 100GB
- Indexes: ~30-40GB additional

**user_spam_features:**
- ~2KB per row (with JSON feature_data)
- 500k rows = 1GB
- Indexes: ~200MB additional

---

## Future Phases Preview

### Phase 2: Scoring Engine
- Compute overall spam scores from Tier 1 features
- Apply configurable thresholds
- Generate risk classifications

### Phase 3: Tier 2 Enrichment

**Status: IMPLEMENTED** - Reddit API integration with rate limiting and circuit breaker protection.

Tier 2 enrichment extends detection capabilities beyond post-URL analysis with Reddit API-sourced features.

**Implemented Tier 2 Enrichment Tasks:**

1. **enrich_user_features_tier2(username)**
   - Fetch user account data via Reddit API (single Redditor call)
   - Scan user's profile description and recent comments for links
   - Detect Telegram links, adult platform links
   - Update database with 15 new Tier 2 feature columns
   - Includes circuit breaker protection and rate limiting
   - Auto-retries on rate limit (up to 3 times)

2. **check_user_suspended_task(username)**
   - Quick check if user is suspended/deleted (single API call)
   - Used for training data collection (confirmed spam)
   - Returns boolean: True if suspended, False if active

3. **enrich_high_risk_users(min_score, limit)**
   - Batch enrichment of high-risk users without Tier 2 data
   - Finds users with high spam scores needing API enrichment
   - Processes ~40-50 users per day (rate-limited at 50 req/min)
   - Respects circuit breaker state

4. **scan_user_for_telegram_links(username)**
   - Focused Telegram link detection in profile and comments
   - Identifies promotional accounts using off-platform services
   - Updates database with findings

**Tier 2 Features Collected:**

Account Info (from single API call):
- `account_age_days`, `total_karma`, `post_karma`, `comment_karma`
- `karma_per_day`, `has_verified_email`, `is_gold`, `has_custom_avatar`
- `account_suspended`, `is_mod`

Profile/Comment Scanning Results:
- `has_adult_profile_links` - Adult platforms in profile/comments
- `has_telegram_links` - Telegram links for off-platform communication
- `profile_link_sources` - Map of where links were found

**Core Components:**

- **CircuitBreaker** (`circuit_breaker.py`) - Protects against cascading API failures with CLOSED/OPEN/HALF_OPEN states
- **PerMinuteRateLimiter** (`rate_limiter.py`) - Redis-based sliding window limiting to 50 req/min
- **UserDataFetcher** (`user_data_fetcher.py`) - Service for fetching user data with protection mechanisms
- **Tier2Features** (`tier2_features.py`) - Dataclass for API-sourced features with helper methods

**Rate Limiting Strategy:**
- Single-worker queue for effective concurrency control
- 50 requests/minute (conservative, 10 req/min below Reddit's 60 limit)
- 1.5 second minimum interval between API calls
- Exponential backoff on consecutive errors
- Automatic recovery testing when API unavailable

**Graceful Degradation:**
- Falls back to Tier 1-only scoring if API unavailable (circuit breaker OPEN)
- Continues processing without blocking other operations
- Automatic recovery attempts every 60 seconds (increasing timeout on repeated failures)

**Database Changes:**
- 15 new columns added to `user_spam_features` table
- `tier2_enriched_at` timestamp for cache freshness
- `tier2_enrichment_failed` flag for tracking failures
- All updates are non-blocking

See `/docs/SpamDetection/FinalDocs/tier2-enrichment-usage.md` for complete implementation details, configuration, and usage examples.

### Phase 4: Trigger Integration
- Automatic subreddit mod actions
- Flag high-risk posts for review
- Send notifications to admins

### Phase 5: Training Data Preparation
- Label confirmed spam/legitimate users
- Generate training datasets
- Track model performance

### Phase 6: ML Model Training
- Train classification models
- Continuous improvement pipeline
- Explainability features

---

## Deployment and Operations

### Configuration
- Uses Config class for environment/file settings
- Database credentials via environment
- Celery queue configuration
- Task retry policies

### Monitoring
- Task execution logs in system logger
- Feature computation metrics
- Database performance monitoring
- Queue depth monitoring

### Maintenance
- Regular spam subreddit list updates
- Feature schema evolution (Alembic)
- Archive old activity records (optional)
- Performance optimization

### Troubleshooting

**No features generated:**
- Check author has minimum 3 posts
- Verify author_activity_tracking records exist
- Check database connectivity

**High latency features:**
- Monitor database query performance
- Check for locks on author_activity_tracking
- Verify indexes exist
- Scale Celery workers if needed

---

## Code Locations Summary

| Component | Location |
|-----------|----------|
| Spam detection tasks | `redditrepostsleuth/core/celery/tasks/spam_detection_tasks.py` |
| Feature extractor | `redditrepostsleuth/core/services/spam/spam_feature_extractor.py` |
| Username patterns | `redditrepostsleuth/core/services/spam/username_patterns.py` |
| Database models | `redditrepostsleuth/core/db/databasemodels.py` |
| Unit of Work | `redditrepostsleuth/core/db/uow/` |
| Repositories | `redditrepostsleuth/core/db/repository/` |
| Tests | `tests/core/services/spam/` |

---

## Relationship with Existing Adult Promoter System

The new spam detection system operates alongside the existing `adult_promoter` detection system. Understanding the differences is important for proper usage.

### Existing System: `adult_promoter` Detection

**Location:** `redditrepostsleuth/core/util/onlyfans_handling.py`

**Purpose:** Real-time, comprehensive adult content promoter detection for monitored subreddits.

**Capabilities:**
| Source | What's Checked |
|--------|----------------|
| User Bio | `redditor.subreddit.public_description` for flagged domains |
| Profile Links | All links from user's Reddit profile |
| **User Comments** | Up to 100 comments scanned for adult links |
| Landing Pages | Deep scanning of linktree, beacons.ai, etc. for hidden adult links |

**Flagged Domains:** `fans.ly`, `onlyfans.com`, `fansly.com`

**Landing Page Detection:** `beacons.ai`, `linktr.ee`, `linkbio.co`, `snipfeed.co`, `allmylink.me`

**Trigger:** Called by `monitored_sub_service.py` when configured for a subreddit.

**Action:** Adds user to `UserReview` table for moderator action.

### New System: Spam Detection (This Document)

**Purpose:** Batch feature extraction for ML-based classification.

**Current Capabilities (Phase 0/1):**
| Source | What's Checked |
|--------|----------------|
| Post URL | 18 adult platform patterns, 21 URL shortener patterns |

**Not Currently Checked:**
- User bio
- Profile links
- User comments
- Landing page deep scanning

**Trigger:** Called during post ingestion for all posts.

**Action:** Stores features in `author_activity_tracking` and `user_spam_features` tables.

### Why the Difference?

The systems have different design goals:

| Aspect | Adult Promoter System | New Spam Detection |
|--------|----------------------|-------------------|
| **Goal** | Real-time detection & action | Feature collection for ML |
| **Scope** | Per monitored subreddit | All ingested posts |
| **API Calls** | Multiple per user | Zero (Phase 0/1) |
| **Action** | Immediate mod action | Feature storage |
| **Coverage** | Bio, profile, comments | Post URL only |

**Phase 0/1 Design Rationale:**
- Zero API calls to maintain ingest pipeline performance
- Per-post tracking for granular behavioral analysis
- Foundation for ML model training
- Comprehensive detection deferred to Phase 3 Tier 2 enrichment

### Coexistence Strategy

Both systems should continue operating:

1. **Adult Promoter System** - Continues handling real-time detection for monitored subreddits that have `adult_promoter` enabled.

2. **New Spam Detection System** - Builds feature foundation for eventual ML-based classification that will work across all subreddits.

When Phase 3 Tier 2 enrichment is implemented, it will reuse the detection logic from `onlyfans_handling.py` to ensure consistency.

---

## Conclusion

The spam detection system provides a solid foundation (Phase 0) for identifying suspicious behavior through:

1. **Lightweight activity tracking** - Captures behavior signals during post ingestion
2. **Comprehensive feature extraction** - 50+ features from existing database data
3. **Distributed processing** - Scales horizontally via Celery
4. **Modular design** - Easy to extend with new features and phases

Future phases will build on this foundation to implement scoring, enrichment, and machine learning components.

---

## References

### Key Files
- Spam detection tasks: `spam_detection_tasks.py` (334 lines)
- Feature extractor: `spam_feature_extractor.py` (413 lines)
- Username patterns: `username_patterns.py` (215 lines)

### Database Models
- `AuthorActivityTracking` (18 columns)
- `UserSpamFeatures` (15 columns)
- `SpamSubredditList` (8 columns)

### External Documentation
- Celery: http://docs.celeryproject.org/
- SQLAlchemy: https://docs.sqlalchemy.org/
- Python dataclasses: https://docs.python.org/3/library/dataclasses.html
