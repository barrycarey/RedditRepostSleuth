# Spam Detection System - Complete Flow Documentation

## Overview

The Repost Sleuth Spam Detection System is a multi-phase, distributed architecture designed to identify and analyze spam and promotional accounts on Reddit. The system works with zero API calls to Reddit (after initial post ingestion) by analyzing existing database records and extracting behavioral patterns indicative of spam activity.

**Key Goals:**
- Detect promotional and spam accounts through behavioral analysis
- Identify high-risk reposters for moderator review
- Build a foundation for future machine learning-based classification
- Scale horizontally using Celery distributed task processing
- Maintain performance without requiring additional API quota

**Current Implementation Status:** Phases 0-4 and 5.5 Complete - Production Ready (Shadow Mode)

---

## Entry Points and Flow Diagrams

The spam detection system has multiple entry points through which data flows into the detection pipeline. This section provides a quick reference for developers to understand how each entry point works, what triggers it, and what happens downstream.

### Entry Point Matrix

| Entry Point | Trigger | Location | Primary Task | Queue | Purpose |
|-------------|---------|----------|--------------|-------|---------|
| 1. Post Ingestion | Every new post indexed | `ingest_tasks.py:140-146` | `track_author_activity` | `spam_detection` | Track behavioral signals |
| 2. Monitored Subreddit Check | Post checked in monitored sub | `monitored_sub_task_logic.py:129-161` | `score_and_flag_user` | async | Score authors for spam |
| 3. Summons Request | Repost summons received | `summonshandler.py:495-521` | `score_and_flag_user` | async | Analyze reposters |
| 4. Admin API | POST to spam scoring endpoint | `spam_admin.py` | `score_and_flag_user` | async | Manual trigger |
| 5. Scheduled Tasks | Celery Beat scheduler | `celeryconfig.py:120-136` | Multiple | async | Daily/weekly analyses |
| 6. Batch Script | Command line execution | `queue_spam_scoring.py` | `score_and_flag_user` | async | Batch processing |

### Entry Point 1: Post Ingestion Pipeline (Phase 0)

**Trigger Point:** Every new post ingested into the system
**Config Gate:** `spam_author_tracking_enabled`

**Call Chain:**
```
save_new_post() [ingest_tasks.py:140-146]
  └─ if spam_author_tracking_enabled:
     └─ track_author_activity.apply_async() → spam_detection queue
```

**Task Flow Details:**
```
Entry: save_new_post() with post metadata
  ├─ Check config: spam_author_tracking_enabled
  ├─ Extract post metadata (id, author, subreddit, url, nsfw, post_type_id, created_at)
  └─ Queue async task: track_author_activity.apply_async(
       post_id, author, subreddit, url, is_nsfw, post_type_id, created_at_iso
     )

Celery Task: track_author_activity
  ├─ Input: post metadata (7 parameters)
  ├─ Detect adult platform links (regex matching)
  ├─ Detect URL shortener links (regex matching)
  ├─ Detect Telegram links (regex matching)
  ├─ Create AuthorActivityTracking record
  ├─ Store in database
  └─ Output: None (fire-and-forget)

Result:
  └─ author_activity_tracking table has new record
     └─ Future analysis tasks can aggregate posts by author
```

**File Locations:**
- Entry: `/home/barry/PycharmProjects/RedditRepostSleuth/redditrepostsleuth/core/celery/tasks/ingest_tasks.py` (lines 140-146)
- Task: `/home/barry/PycharmProjects/RedditRepostSleuth/redditrepostsleuth/core/celery/tasks/spam_detection_tasks.py` (lines 163-241)

---

### Entry Point 2: Monitored Subreddit Pipeline (Phase 4)

**Trigger Point:** Post checked in monitored subreddit with `spam_detection_enabled=True`
**Flow Type:** Synchronous scoring

**Call Chain:**
```
monitored_sub_task_logic.queue_spam_analysis() [monitored_sub_task_logic.py:129-161]
  └─ score_and_flag_user.delay(
       username=post_author,
       update_user_review=True
     )
```

**Task Flow Details:**
```
Entry: queue_spam_analysis() in monitored subreddit pipeline
  ├─ Check if sub has spam_detection_enabled=True
  ├─ Extract post author
  ├─ Queue spam scoring task
  └─ Input to task: username, update_user_review=True

Celery Task: score_and_flag_user
  ├─ Input: username, update_user_review flag
  ├─ Call score_user_spam() directly (not async)
  │  ├─ Extract Tier 1 features via SpamFeatureExtractor
  │  ├─ Score user via SpamScorer
  │  └─ Store computed score in database
  ├─ if update_user_review=True:
  │  └─ Create/update UserReview record
  ├─ if score exceeds threshold:
  │  └─ Queue action handler: SpamActionHandler.handle_spam_detection()
  │     ├─ Remove post
  │     ├─ Ban user
  │     └─ Notify modmail
  └─ Output: Spam score + action status

Result:
  ├─ user_spam_features table updated with score
  ├─ user_review table may be updated
  └─ Moderation actions queued (if threshold exceeded)
```

**File Locations:**
- Entry: `/home/barry/PycharmProjects/RedditRepostSleuth/redditrepostsleuth/core/celery/task_logic/monitored_sub_task_logic.py` (lines 129-161)
- Task: `/home/barry/PycharmProjects/RedditRepostSleuth/redditrepostsleuth/core/celery/tasks/spam_detection_tasks.py` (lines 899-970)
- Scorer: `/home/barry/PycharmProjects/RedditRepostSleuth/redditrepostsleuth/core/services/spam/spam_scorer.py`
- Action Handler: `/home/barry/PycharmProjects/RedditRepostSleuth/redditrepostsleuth/core/services/spam/spam_action_handler.py`

---

### Entry Point 3: Summons Pipeline

**Trigger Point:** Processing a repost summons request
**Flow Type:** Asynchronous

**Call Chain:**
```
SummonsHandler._queue_spam_analysis() [summonshandler.py:495-521]
  └─ score_and_flag_user.delay(
       username=detected_reposter,
       update_user_review=True
     )
```

**Task Flow Details:**
```
Entry: _queue_spam_analysis() when processing summons
  ├─ Check if post author is marked as reposter
  ├─ Extract username from post author (not summons requestor)
  ├─ Queue spam scoring for the reposter
  └─ Input to task: username, update_user_review=True

Celery Task: score_and_flag_user
  ├─ Input: username (the reposter), update_user_review=True
  ├─ Call score_user_spam() directly
  │  ├─ Extract Tier 1 features
  │  ├─ Score user
  │  └─ Store score
  ├─ Update UserReview record
  ├─ Log detection event
  └─ Output: Spam score

Result:
  └─ Reposter profile enriched with spam features
     └─ Available for admin review and potential actions
```

**File Locations:**
- Entry: `/home/barry/PycharmProjects/RedditRepostSleuth/redditrepostsleuth/summonssvc/summonshandler.py` (lines 495-521)
- Task: `/home/barry/PycharmProjects/RedditRepostSleuth/redditrepostsleuth/core/celery/tasks/spam_detection_tasks.py` (lines 899-970)

---

### Entry Point 4: Admin API (Manual Trigger)

**Trigger Point:** POST request to admin API endpoint
**Endpoint:** `/admin/spam/score-user`
**Flow Type:** Synchronous HTTP response with async background task

**Call Chain:**
```
POST /admin/spam/score-user
  └─ SpamScoreUserEndpoint.handle_post()
     └─ score_and_flag_user.delay(
          username=request_param,
          update_user_review=True
        )
```

**Task Flow Details:**
```
Entry: HTTP POST request to admin endpoint
  ├─ Admin provides: username
  ├─ Endpoint validates authorization
  ├─ Queue async spam scoring task
  └─ Return: Task ID + immediate feedback

Celery Task: score_and_flag_user (async)
  ├─ Input: username, update_user_review=True
  ├─ Extract Tier 1 features
  ├─ Score user
  ├─ Store score
  ├─ Update UserReview record
  └─ Log detection

Result:
  └─ Admin can check task status
     └─ Results available in UserReview table
```

**File Locations:**
- Endpoint: `/home/barry/PycharmProjects/RedditRepostSleuth/redditrepostsleuth/repostsleuthsiteapi/endpoints/spam_admin.py`
- Task: `/home/barry/PycharmProjects/RedditRepostSleuth/redditrepostsleuth/core/celery/tasks/spam_detection_tasks.py` (lines 899-970)

---

### Entry Point 5: Scheduled Tasks (Celery Beat)

**Trigger Point:** Celery Beat scheduler at configured times
**Config Location:** `/home/barry/PycharmProjects/RedditRepostSleuth/redditrepostsleuth/core/celery/celeryconfig.py` (lines 120-136)

**Scheduled Tasks:**

#### Task A: scheduled_analyze_top_reposters
**Schedule:** Daily at 3 AM UTC
**Call Chain:**
```
Celery Beat (3:00 AM UTC)
  └─ scheduled_analyze_top_reposters.delay()
     ├─ Query repost table for top reposters (last 30 days)
     ├─ For each reposter:
     │  ├─ Extract Tier 1 features
     │  ├─ Check high-risk criteria
     │  └─ Count high-risk users
     └─ Log summary statistics
```

**Output:** Summary of high-risk reposters identified

#### Task B: scheduled_enrich_high_risk
**Schedule:** Daily at 4 AM UTC
**Call Chain:**
```
Celery Beat (4:00 AM UTC)
  └─ scheduled_enrich_high_risk.delay()
     ├─ Query user_spam_features with high scores
     ├─ For each high-risk user without Tier 2 data:
     │  ├─ Fetch user data via Reddit API
     │  ├─ Scan profile for links
     │  ├─ Store Tier 2 features
     │  └─ Respect rate limiting (50 req/min)
     └─ Log enrichment results
```

**Output:** High-risk users enriched with Tier 2 data

#### Task C: scheduled_cleanup_features
**Schedule:** Weekly Sunday at 5 AM UTC
**Call Chain:**
```
Celery Beat (Sunday 5:00 AM UTC)
  └─ scheduled_cleanup_features.delay()
     ├─ Clean old feature records (placeholder)
     └─ Log cleanup results
```

#### Task D: scheduled_purge_activity_tracking
**Schedule:** Weekly Sunday at 6 AM UTC
**Call Chain:**
```
Celery Beat (Sunday 6:00 AM UTC)
  └─ scheduled_purge_activity_tracking.delay()
     ├─ Purge old activity tracking records (optional)
     └─ Log purge results
```

**File Locations:**
- Config: `/home/barry/PycharmProjects/RedditRepostSleuth/redditrepostsleuth/core/celery/celeryconfig.py` (lines 120-136)
- Tasks: `/home/barry/PycharmProjects/RedditRepostSleuth/redditrepostsleuth/core/celery/tasks/spam_detection_tasks.py`

---

### Entry Point 6: Utility Scripts (Batch Processing)

**Trigger Point:** Manual command-line execution
**Script Location:** `/home/barry/PycharmProjects/RedditRepostSleuth/utility_scripts/queue_spam_scoring.py`

**Call Chain:**
```
python queue_spam_scoring.py --users user1 user2 user3 ...
  └─ For each username:
     └─ score_and_flag_user.delay(username, update_user_review=True)
```

**Task Flow Details:**
```
Entry: Command-line script
  ├─ Read list of usernames from arguments
  ├─ For each username:
  │  └─ Queue spam scoring task asynchronously
  └─ Report queued task count

Celery Task: score_and_flag_user
  ├─ Input: username, update_user_review=True
  ├─ Extract Tier 1 features
  ├─ Score user
  ├─ Store score
  ├─ Update UserReview
  └─ Output: Spam score

Result:
  └─ Each user scored and available for review
```

**Usage:**
```bash
python utility_scripts/queue_spam_scoring.py --users SuspiciousUser1 SuspiciousUser2
```

**File Locations:**
- Script: `/home/barry/PycharmProjects/RedditRepostSleuth/utility_scripts/queue_spam_scoring.py`

---

## Complete System Architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│                        REDDIT POST INGESTION                             │
│                    (Existing Ingest Pipeline)                            │
└────────────────────────────────┬─────────────────────────────────────────┘
                                 │
                    ┌────────────┼────────────┐
                    │            │            │
                    ▼            ▼            ▼
        ┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐
        │ Entry Point 1:   │ │ Entry Point 2:   │ │ Entry Point 3:   │
        │ Post Ingestion   │ │ Monitored Sub    │ │ Summons Handler  │
        │ (Every post)     │ │ (If enabled)     │ │ (Repost found)   │
        └────────┬─────────┘ └────────┬─────────┘ └────────┬─────────┘
                 │                    │                    │
                 ▼                    ▼                    ▼
        ┌──────────────────────────────────────────────────────────┐
        │  Async Task: track_author_activity (Entry 1 only)        │
        │  Or async: score_and_flag_user (Entry 2, 3, 4, 6)        │
        └────────┬─────────────────────────────────────────────────┘
                 │
    ┌────────────┴────────────┐
    │                         │
    ▼                         ▼
┌──────────────────┐   ┌──────────────────────────┐
│ Feature          │   │ Spam Scoring             │
│ Extraction       │   │ & Action Handling        │
│ (Tier 1)         │   │ (Tier 1 + optional 2)    │
└────────┬─────────┘   └────────┬─────────────────┘
         │                      │
         ▼                      ▼
    ┌────────────────────────────────┐
    │ Database Updates:              │
    │ - author_activity_tracking     │
    │ - user_spam_features           │
    │ - user_review                  │
    └────────────────────────────────┘
         │
         ├─ Entry Point 5: Scheduled Tasks (daily/weekly)
         │  ├─ analyze_top_reposters
         │  ├─ enrich_high_risk
         │  └─ cleanup tasks
         │
         └─ Entry Point 4: Admin API (manual query)
            └─ SpamScoreUserEndpoint
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
    tracked_span_days: int  # Span of tracked activity (max ~90 days due to retention)
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
| `posts_per_day_avg` | total_posts / tracked_span_days | Activity velocity |
| `tracked_span_days` | MAX(created_at) - MIN(created_at) | Span of tracked activity (max ~90 days) |
| `nsfw_post_count` | COUNT where is_nsfw=true | NSFW content volume |

> **Note:** `tracked_span_days` in Tier1Features is the span of tracked activity data (limited to ~90 days due to `author_activity_tracking` retention). For the actual Reddit account age, see `account_age_days` in Tier2Features (fetched from Reddit API).

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

## Phase 2: Spam Scoring and Risk Classification

**Status:** ✅ COMPLETE (616 lines implemented)

### Purpose
Convert extracted Tier 1 features into spam scores and risk levels using rule-based scoring with configurable weights.

### Scoring Architecture

**Main Service:** `SpamScorer` (located in `spam_scorer.py`)

**Core Classes:**
- `SpamScorer` - Rule-based scoring from Tier 1 features
- `SpamScorerWithTier2` - Extended scoring with Tier 2 features
- `ScoringConfig` - Configurable thresholds and weights
- `ScoringResult` - Result container with score, confidence, risk level, reasons

**Scoring Method:**
```python
def score_user(features: Tier1Features) -> ScoringResult
```

**Returns:** ScoringResult with:
- `score`: float (0.0-1.0, higher = more spam)
- `confidence`: float (0.0-1.0, based on data availability)
- `risk_level`: str (LOW/MEDIUM/HIGH/CRITICAL)
- `reasons`: List[str] (human-readable explanations)
- `component_scores`: Dict[str, float] (individual signal scores)

### Scoring Signals (6 Primary Signals)

**Signal 1: Repost Behavior** (Weight: 0.15-0.35)
- Thresholds: 30% (0.15), 50% (0.25), 70% (0.35)
- Measures ratio of reposts to total posts
- High weight for 70%+ repost ratio

**Signal 2: Adult Platform Linking** (Weight: 0.10-0.35)
- Thresholds: 1% (0.10), 20% (0.25), 50% (0.35)
- Detects OnlyFans, Fansly, and 16 other platforms
- High weight for 50%+ adult links

**Signal 3: Posting Patterns** (Weight: 0.08-0.20)
- Posting frequency: 5+ (0.08), 10+ (0.15), 15+ (0.20) posts/day
- Subreddit diversity: < 3 subs (+0.12)
- Combines frequency and concentration metrics

**Signal 4: Username Patterns** (Weight: 0.12)
- Reddit auto-generated format (0.85 confidence)
- CamelCase + digits (0.70 confidence)
- 7 suspicious pattern categories detected

**Signal 5: Karma Farming** (Weight: 0.05-0.30)
- Scales: 0.05 per post in karma farming subs
- Max weight: 0.30 (capped at 6+ posts)
- Detects FreeKarma4U, AutoKarma, etc.

**Signal 6: Supporting Signals** (Weight: 0.03-0.15)
- Short link ratio > 30% (+0.08)
- NSFW + adult platform combo (+0.15)
- Cumulative from multiple factors

### Risk Level Classification

**Risk Thresholds:**
- **LOW:** 0.0 - 0.30 (normal activity)
- **MEDIUM:** 0.30 - 0.60 (moderate concerns)
- **HIGH:** 0.60 - 0.80 (strong spam indicators)
- **CRITICAL:** 0.80 - 1.0 (confirmed or high-confidence spam)

### Confidence Calculation

Based on post count:
- 100+ posts: 0.95 confidence
- 50-99 posts: 0.85 confidence
- 20-49 posts: 0.70 confidence
- 10-19 posts: 0.55 confidence
- 5-9 posts: 0.40 confidence
- < 5 posts: 0.25 confidence
- Boost: +0.05 if repost data available (max 0.98)

### Celery Tasks

**Implemented Tasks:**
- `score_user_spam(username)` - Score single user
- `batch_score_users(usernames)` - Batch scoring
- `score_and_flag_user(username, update_user_review)` - Score and update UserReview
- `rescore_user_with_tier2(username)` - Re-score with Tier 2 data

### Database Integration

**Columns Added to user_spam_features:**
- `spam_score` (Float) - Calculated spam score
- `spam_score_confidence` (Float) - Confidence in score
- `risk_level` (String) - Risk classification
- `computed_at` (DateTime) - Last computation timestamp

See `/docs/SpamDetection/FinalDocs/scoring-engine-reference.md` for complete scoring algorithm details.

---

## Celery Tasks Reference

### Task: track_author_activity

**Location:** `/home/barry/PycharmProjects/RedditRepostSleuth/redditrepostsleuth/core/celery/tasks/spam_detection_tasks.py`

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

**Location:** `/home/barry/PycharmProjects/RedditRepostSleuth/redditrepostsleuth/core/celery/tasks/spam_detection_tasks.py`

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

### Task: score_user_spam

**Location:** `/home/barry/PycharmProjects/RedditRepostSleuth/redditrepostsleuth/core/celery/tasks/spam_detection_tasks.py` (lines 705-788)

**Purpose:** Score a user for spam and return spam score

**Configuration:**
```python
@celery.task(bind=True, base=SpamDetectionTask)
def score_user_spam(self, username: str) -> dict
```

**Returns:**
```python
{
    'username': username,
    'spam_score': 0.75,
    'confidence': 0.82,
    'risk_level': 'HIGH',
    'primary_signals': ['repost_behavior', 'posting_patterns'],
    'computed_at': '2024-01-25T14:30:00'
}
```

**Usage:**
```python
# Score a single user
result = score_user_spam.delay('SuspiciousUser')
```

### Task: score_and_flag_user

**Location:** `/home/barry/PycharmProjects/RedditRepostSleuth/redditrepostsleuth/core/celery/tasks/spam_detection_tasks.py` (lines 899-970)

**Purpose:** Score user and optionally flag for review

**Configuration:**
```python
@celery.task(bind=True, base=SpamDetectionTask)
def score_and_flag_user(
    self,
    username: str,
    update_user_review: bool = False
) -> dict
```

**Parameters:**
- `username`: Reddit username to score
- `update_user_review`: If True, create/update UserReview record

**Returns:**
```python
{
    'username': username,
    'spam_score': 0.82,
    'risk_level': 'HIGH',
    'user_review_updated': True,
    'actions_queued': ['post_removal', 'user_ban']
}
```

**Workflow:**
```
1. Call score_user_spam() directly (not async)
2. Store score in user_spam_features
3. if update_user_review=True:
   ├─ Create or update UserReview record
   ├─ Set review status based on score
   └─ Assign to moderator queue
4. if score exceeds threshold:
   ├─ Initialize SpamActionHandler
   ├─ Queue moderation actions:
   │  ├─ Remove posts
   │  ├─ Ban user
   │  └─ Notify modmail
   └─ Log detection event
5. Return results
```

**Usage:**
```python
# From monitored subreddit pipeline
result = score_and_flag_user.delay('RepostUser', update_user_review=True)

# From summons handler
result = score_and_flag_user.delay('DetectedReposter', update_user_review=True)

# From admin API
result = score_and_flag_user.delay('ManuallyTriggeredUser', update_user_review=True)
```

### Task: enrich_user_features_tier2

**Location:** `/home/barry/PycharmProjects/RedditRepostSleuth/redditrepostsleuth/core/celery/tasks/spam_detection_tasks.py` (lines 429-527)

**Purpose:** Enrich user features with Tier 2 data (Reddit API sourced)

**Configuration:**
```python
@celery.task(bind=True, base=SpamDetectionTask)
def enrich_user_features_tier2(self, username: str) -> dict
```

**Returns:**
```python
{
    'username': username,
    'success': True,
    'tier2_features_added': ['account_age_days', 'total_karma', 'has_telegram_links'],
    'enriched_at': '2024-01-25T14:35:00'
}
```

**Processing:**
1. Fetch user account data via Reddit API
2. Scan user profile for links
3. Detect adult platform links
4. Detect Telegram links
5. Store 15 new Tier 2 feature columns
6. Queue rescore task

**Rate Limiting:**
- 50 requests/minute via PerMinuteRateLimiter
- Circuit breaker protection
- Auto-retry on rate limit (up to 3 times)

### Task: rescore_user_with_tier2

**Location:** `/home/barry/PycharmProjects/RedditRepostSleuth/redditrepostsleuth/core/celery/tasks/spam_detection_tasks.py` (lines 791-896)

**Purpose:** Re-score user using both Tier 1 and Tier 2 features

**Configuration:**
```python
@celery.task(bind=True, base=SpamDetectionTask)
def rescore_user_with_tier2(self, username: str) -> dict
```

**Returns:**
```python
{
    'username': username,
    'spam_score_tier2': 0.88,
    'confidence_tier2': 0.92,
    'score_change': '+0.06',
    'updated_tables': ['user_spam_features', 'user_review']
}
```

### Task: batch_compute_spam_features

**Location:** `/home/barry/PycharmProjects/RedditRepostSleuth/redditrepostsleuth/core/celery/tasks/spam_detection_tasks.py`

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

**Location:** `/home/barry/PycharmProjects/RedditRepostSleuth/redditrepostsleuth/core/celery/tasks/spam_detection_tasks.py`

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

**Location:** `/home/barry/PycharmProjects/RedditRepostSleuth/redditrepostsleuth/core/celery/tasks/spam_detection_tasks.py`

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

#### 3. user_review
- **Purpose:** Track users flagged for moderator review
- **Key Columns:** username, review_status, assigned_mod, created_at

#### 4. spam_subreddit_list (Reference)
- **Rows:** ~500-1000 (manually curated)
- **Purpose:** Known spam/karma farm subreddit catalog
- **Categories:** karma_farming, easy_karma, spam_network, etc.
- **Maintenance:** Manual updates by admins

#### 5. repost (Existing Table)
- Used to count author reposts
- Query: `count_reposts_by_author(username)`

#### 6. summons (Existing Table)
- Used to count bot mentions
- Query: `count_by_post_author(username)`

#### 7. post (Existing Table)
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
├─ one-to-one → user_review (via username)
└─ many-to-many → spam_subreddit_list (via subreddit_distribution)

user_review
└─ one-to-one → user_spam_features (via username)

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

### Example 3: Monitored Subreddit Trigger

```
Timeline: Post detected in monitored subreddit with spam_detection enabled

10:15:00 - Post submitted to monitored subreddit
10:15:05 - Monitored subreddit pipeline checks post
10:15:06 - Check passes, post.author='PromoJoe'
10:15:07 - queue_spam_analysis() called
           ├─ Check sub has spam_detection_enabled=True → YES
           └─ Queue: score_and_flag_user('PromoJoe', update_user_review=True)

10:15:08 - Celery worker picks up task
10:15:09 - score_user_spam('PromoJoe'):
           ├─ Extract Tier 1 features
           │  ├─ total_posts=156, repost_ratio=0.68
           │  ├─ adult_link_ratio=0.35
           │  ├─ username_pattern_confidence=0.82
           │  └─ spam_subreddit_posts=45
           ├─ Score across 6 signals:
           │  ├─ repost_behavior: 0.85 (HIGH)
           │  ├─ adult_platform: 0.70 (HIGH)
           │  ├─ posting_patterns: 0.60 (MEDIUM)
           │  ├─ username_pattern: 0.75 (HIGH)
           │  ├─ karma_farming: 0.80 (HIGH)
           │  └─ supporting_signals: 0.65 (MEDIUM)
           ├─ Weighted aggregate: 0.74
           └─ Risk level: HIGH

10:15:10 - Store score in user_spam_features
10:15:11 - update_user_review=True:
           ├─ Create UserReview record
           ├─ Set status='HIGH_RISK'
           └─ Add to moderator queue

10:15:12 - score > threshold (0.70), execute actions:
           ├─ Initialize SpamActionHandler
           ├─ Queue post removal
           ├─ Queue user ban
           └─ Queue modmail notification

10:15:13 - Log detection event
10:15:14 - Return results

Result: User flagged, actions queued for moderator/admin approval
```

### Example 4: Batch Analysis of Top Reposters

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
2. **Monitored Subreddit Pipeline** → score_and_flag_user task
3. **Summons Handler** → score_and_flag_user task
4. **Admin API** → score_and_flag_user task
5. **Celery Beat Scheduler** → Periodic batch analyses
6. **Utility Scripts** → Manual batch processing

### Output Consumers (Current & Future Phases)
1. **User Review Table** - Moderator review queue
2. **Moderation Actions Queue** - Post removal, bans, notifications
3. **Admin Dashboard** - View user scores and flags
4. **Tier 2 Enrichment** - Enhanced scoring with API data
5. **Phase 2: Scoring Engine** - Consumes Tier1Features
6. **Phase 5: Training Data** - ML dataset preparation
7. **Phase 6: ML Model** - Trains on features

### External Dependencies
1. **Database** - MySQL with SQLAlchemy ORM
2. **Unit of Work Manager** - Database access abstraction
3. **Redis/Celery** - Task queue and distribution
4. **Configuration** - Config class for settings
5. **Reddit PRAW API** - Tier 2 enrichment only
6. **Circuit Breaker** - API failure protection
7. **Rate Limiter** - Concurrency control

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
- Scores ~10-15 users/second (score_user_spam)
- Processes ~500 users in batch (batch_compute_spam_features)

**With 10 Workers:**
- Tracks ~10,000 posts/second
- Analyzes ~50-100 users/second
- Scores ~100-150 users/second
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

## Phase 3: Tier 2 Enrichment

### Status: IMPLEMENTED
Reddit API integration with rate limiting and circuit breaker protection.

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

---

## Phase 4: Trigger Integration

### Status: ✅ COMPLETE
Full trigger integration with shadow mode support. System ready for production deployment.

**Implemented Components:**

1. **Configuration Management** (111 lines)
   - `SpamDetectionConfig` dataclass for per-subreddit settings
   - `from_monitored_sub()` factory method
   - `should_take_action()` threshold checking
   - `get_actions()` action determination

2. **Action Handler** (345 lines)
   - `SpamActionHandler` class with shadow mode support
   - Post removal with configurable reason
   - User ban with configurable reason
   - Modmail notification
   - Comprehensive audit logging
   - Graceful error handling

3. **Monitored Subreddit Pipeline Integration**
   - Calls `score_and_flag_user` when post checked
   - Respects whitelist (verified_legit users skipped)
   - Cache checking (recently analyzed users skipped)
   - Minimum 3 posts required
   - Non-blocking async execution

4. **Summons Handler Integration**
   - Scores detected reposters on summons
   - Analyzes post author (not requestor)
   - Low priority queue assignment
   - Skips verified legitimate users

5. **Admin API Endpoints** (5 endpoints, 404 lines)
   - `POST /api/admin/spam/score` - Trigger scoring
   - `GET /api/admin/spam/user/{username}` - Get spam details
   - `GET /api/admin/spam/high-risk` - List high-risk users
   - `POST /api/admin/spam/label` - Manual labeling
   - `GET /api/admin/spam/stats` - Detection statistics

6. **Scheduled Tasks** (4 Celery Beat tasks)
   - `scheduled_analyze_top_reposters` - Daily 3 AM UTC
   - `scheduled_enrich_high_risk` - Daily 4 AM UTC
   - `scheduled_cleanup_features` - Weekly Sunday 5 AM
   - `scheduled_purge_activity_tracking` - Weekly Sunday 6 AM

**Shadow Mode Features:**
- Disabled by default via `SPAM_DETECTION_SHADOW_MODE=true`
- All actions logged but not executed
- Safe for production testing and tuning
- Per-subreddit enable/disable control

---

## Future Phases Preview

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
- Rate limiting settings

### Monitoring
- Task execution logs in system logger
- Feature computation metrics
- Database performance monitoring
- Queue depth monitoring
- Circuit breaker state tracking
- API rate limit monitoring

### Maintenance
- Regular spam subreddit list updates
- Feature schema evolution (Alembic)
- Archive old activity records (optional)
- Performance optimization
- Circuit breaker recovery monitoring

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

**Tier 2 enrichment not working:**
- Check circuit breaker state (should be CLOSED)
- Verify Reddit API credentials
- Monitor rate limit status
- Check for cascading failures

**Actions not executing:**
- Verify SpamActionHandler configuration
- Check moderation action queue depth
- Verify subreddit permissions
- Check moderator assignments

---

## Code Locations Summary

| Component | Location |
|-----------|----------|
| Spam detection tasks | `/home/barry/PycharmProjects/RedditRepostSleuth/redditrepostsleuth/core/celery/tasks/spam_detection_tasks.py` |
| Feature extractor | `/home/barry/PycharmProjects/RedditRepostSleuth/redditrepostsleuth/core/services/spam/spam_feature_extractor.py` |
| Username patterns | `/home/barry/PycharmProjects/RedditRepostSleuth/redditrepostsleuth/core/services/spam/username_patterns.py` |
| Spam scorer | `/home/barry/PycharmProjects/RedditRepostSleuth/redditrepostsleuth/core/services/spam/spam_scorer.py` |
| Spam action handler | `/home/barry/PycharmProjects/RedditRepostSleuth/redditrepostsleuth/core/services/spam/spam_action_handler.py` |
| User data fetcher (Tier 2) | `/home/barry/PycharmProjects/RedditRepostSleuth/redditrepostsleuth/core/services/spam/user_data_fetcher.py` |
| Circuit breaker (Tier 2) | `/home/barry/PycharmProjects/RedditRepostSleuth/redditrepostsleuth/core/services/spam/circuit_breaker.py` |
| Rate limiter (Tier 2) | `/home/barry/PycharmProjects/RedditRepostSleuth/redditrepostsleuth/core/services/spam/rate_limiter.py` |
| Post ingestion tasks | `/home/barry/PycharmProjects/RedditRepostSleuth/redditrepostsleuth/core/celery/tasks/ingest_tasks.py` |
| Monitored sub logic | `/home/barry/PycharmProjects/RedditRepostSleuth/redditrepostsleuth/core/celery/task_logic/monitored_sub_task_logic.py` |
| Summons handler | `/home/barry/PycharmProjects/RedditRepostSleuth/redditrepostsleuth/summonssvc/summonshandler.py` |
| Admin API endpoints | `/home/barry/PycharmProjects/RedditRepostSleuth/redditrepostsleuth/repostsleuthsiteapi/endpoints/spam_admin.py` |
| Celery config | `/home/barry/PycharmProjects/RedditRepostSleuth/redditrepostsleuth/core/celery/celeryconfig.py` |
| Database models | `/home/barry/PycharmProjects/RedditRepostSleuth/redditrepostsleuth/core/db/databasemodels.py` |
| Unit of Work | `/home/barry/PycharmProjects/RedditRepostSleuth/redditrepostsleuth/core/db/uow/` |
| Repositories | `/home/barry/PycharmProjects/RedditRepostSleuth/redditrepostsleuth/core/db/repository/` |
| Tests | `/home/barry/PycharmProjects/RedditRepostSleuth/tests/core/services/spam/` |

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

When Phase 3 Tier 2 enrichment is fully utilized, it will reuse the detection logic from `onlyfans_handling.py` to ensure consistency.

---

## Conclusion

The spam detection system provides a solid foundation (Phases 0-3) for identifying suspicious behavior through:

1. **Lightweight activity tracking** - Captures behavior signals during post ingestion
2. **Comprehensive feature extraction** - 50+ features from existing database data
3. **Statistical scoring** - Risk classification based on behavioral signals
4. **Tier 2 enrichment** - Enhanced features from Reddit API (with protection)
5. **Trigger integration** - Queues moderation actions for review
6. **Distributed processing** - Scales horizontally via Celery
7. **Modular design** - Easy to extend with new features and phases

Future phases will build on this foundation to implement automated actions, training data, and machine learning components.

---

## References

### Key Files
- Spam detection tasks: `spam_detection_tasks.py` (970+ lines)
- Feature extractor: `spam_feature_extractor.py` (413 lines)
- Spam scorer: `spam_scorer.py` (300+ lines)
- Username patterns: `username_patterns.py` (215 lines)
- Action handler: `spam_action_handler.py` (250+ lines)
- User data fetcher: `user_data_fetcher.py` (400+ lines)

### Database Models
- `AuthorActivityTracking` (11 columns)
- `UserSpamFeatures` (30+ columns with Tier 2)
- `UserReview` (12+ columns)
- `SpamSubredditList` (8 columns)

### External Documentation
- Celery: http://docs.celeryproject.org/
- SQLAlchemy: https://docs.sqlalchemy.org/
- Python dataclasses: https://docs.python.org/3/library/dataclasses.html
- Reddit API (PRAW): https://praw.readthedocs.io/