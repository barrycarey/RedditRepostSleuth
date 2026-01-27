# Phase 4: Trigger Integration & Admin API - Complete Implementation

**Status:** ✅ COMPLETE
**Implementation Date:** January 27, 2026
**Files Modified/Created:** 8 files
**New Endpoints:** 5 admin API endpoints
**Scheduled Tasks:** 4 celery beat tasks

---

## Overview

Phase 4 completes the integration of the spam detection system into the production workflows of Reddit Repost Sleuth. This phase implements:

1. **Trigger Points** - Integration with repost detection and summons handling
2. **Configuration Management** - Per-subreddit spam detection settings
3. **Action Handler** - Centralized execution of mod actions (remove, ban, notify)
4. **Scheduled Tasks** - Background jobs for periodic analysis and maintenance
5. **Admin API** - Management endpoints for manual review and triggering

The system operates in **shadow mode by default** (no automated actions) with configurable thresholds per subreddit.

---

## Architecture

### High-Level Flow

```
User Post on Reddit
         │
         ▼
    ┌─────────────────────┐
    │ Ingest Service      │
    │ (Existing)          │
    └──────────┬──────────┘
               │
               ▼
    ┌─────────────────────────────────────┐
    │ Phase 0-1: Track Activity & Extract │
    │ Tier 1 Features                     │
    └──────────┬──────────────────────────┘
               │
               ▼
    ┌─────────────────────────────────────┐
    │ Phase 2: Compute Spam Score         │
    │ (Feature → Score)                   │
    └──────────┬──────────────────────────┘
               │
        ┌──────┴──────────────────────────┐
        │                                 │
        ▼                                 ▼
   ┌──────────────────┐          ┌──────────────────┐
   │ Repost Detected? │          │ User Summoned?   │
   │ (Trigger Point)  │          │ (Trigger Point)  │
   └────────┬─────────┘          └────────┬─────────┘
            │                              │
            ▼                              ▼
   ┌──────────────────────────────────────────────────┐
   │ Phase 4: Spam Analysis & Actions                 │
   │ - Check SpamDetectionConfig                      │
   │ - Verify action threshold met                    │
   │ - Execute configured actions (in shadow mode:    │
   │   remove_post, ban_user, notify_modmail)         │
   │ - Log to database for audit trail                │
   └──────────────────────────────────────────────────┘
```

---

## Component 1: Configuration Management

### SpamDetectionConfig Dataclass

**File:** `redditrepostsleuth/core/services/spam/spam_config_helper.py`

```python
@dataclass
class SpamDetectionConfig:
    """Configuration for spam detection in a monitored subreddit."""
    enabled: bool
    remove_post: bool
    ban_user: bool
    notify_mod_mail: bool
    score_threshold: float
    removal_reason: Optional[str]
    ban_reason: Optional[str]

    @classmethod
    def from_monitored_sub(cls, monitored_sub: MonitoredSub) -> 'SpamDetectionConfig':
        """Create config from MonitoredSub model."""
        return cls(
            enabled=monitored_sub.spam_detection_enabled or False,
            remove_post=monitored_sub.spam_detection_remove_post or False,
            ban_user=monitored_sub.spam_detection_ban_user or False,
            notify_mod_mail=monitored_sub.spam_detection_notify_mod_mail or False,
            score_threshold=monitored_sub.spam_detection_score_threshold or 0.7,
            removal_reason=monitored_sub.spam_detection_removal_reason,
            ban_reason=monitored_sub.spam_detection_ban_reason,
        )

    def should_take_action(self, score: float) -> bool:
        """Check if score exceeds threshold for action."""
        return self.enabled and score >= self.score_threshold

    def get_actions(self, score: float) -> dict:
        """Get actions to take based on score."""
        if not self.should_take_action(score):
            return {'remove_post': False, 'ban_user': False, 'notify_mod_mail': False}
        return {
            'remove_post': self.remove_post,
            'ban_user': self.ban_user,
            'notify_mod_mail': self.notify_mod_mail,
        }
```

### MonitoredSub Schema Extensions

Configuration columns added to `MonitoredSub` table (already in schema):

```python
# In databasemodels.py
class MonitoredSub(Base):
    # ... existing columns ...
    spam_detection_enabled = Column(Boolean, default=False)
    spam_detection_remove_post = Column(Boolean, default=False)
    spam_detection_ban_user = Column(Boolean, default=False)
    spam_detection_notify_mod_mail = Column(Boolean, default=False)
    spam_detection_score_threshold = Column(Float, default=0.7)
    spam_detection_removal_reason = Column(String(300))
    spam_detection_ban_reason = Column(String(300))
```

### Default Configuration

| Setting | Default | Recommended |
|---------|---------|-------------|
| `enabled` | False | False (opt-in) |
| `remove_post` | False | False (start with log-only) |
| `ban_user` | False | False (start with log-only) |
| `notify_mod_mail` | False | True (for awareness) |
| `score_threshold` | 0.7 | 0.75-0.8 (conservative) |

---

## Component 2: Action Handler

### SpamActionHandler Class

**File:** `redditrepostsleuth/core/services/spam/spam_action_handler.py`

```python
@dataclass
class SpamActionResult:
    """Result of spam action handling."""
    username: str
    score: float
    risk_level: str
    actions_attempted: List[str]
    actions_succeeded: List[str]
    actions_failed: List[str]
    error_messages: List[str]

    @property
    def success(self) -> bool:
        return len(self.actions_failed) == 0


class SpamActionHandler:
    """Handles actions for detected spam."""

    def __init__(self, reddit: Reddit, uowm: UnitOfWorkManager):
        self.reddit = reddit
        self.uowm = uowm

    def handle_spam_detection(
        self,
        username: str,
        score: float,
        risk_level: str,
        reasons: List[str],
        submission: Optional[Submission],
        monitored_sub: Optional[MonitoredSub],
        config: Optional[SpamDetectionConfig] = None,
    ) -> SpamActionResult:
        """Handle spam detection with configured actions."""
        # Returns SpamActionResult with outcomes
```

### Action Execution

**Remove Post:**
- Uses `submission.mod.remove(spam=True, mod_note=...)`
- Logs removal to database for audit trail
- Includes configurable removal reason

**Ban User:**
- Uses `subreddit.banned.add()` with Reddit API
- Sets ban_reason with spam score
- Stores ban information in database
- Note includes contributing factors

**Notify Modmail:**
- Sends subreddit modmail with detection details
- Includes spam score, risk level, and top factors
- Lists actions taken
- Template-based formatting

### Shadow Mode Support

Shadow mode can be enabled globally via environment variable:

```python
SPAM_DETECTION_SHADOW_MODE=true
```

In shadow mode:
- All actions are logged but NOT executed
- System behaves as if actions were successful
- Audit trail still created for analysis
- Allows safe testing without affecting users

---

## Component 3: Integration Points

### 3.1 Repost Detection Integration

**File:** `redditrepostsleuth/core/celery/task_logic/monitored_sub_task_logic.py`

Integration after repost is detected:

```python
async def check_submission(
    self,
    submission: Submission,
    monitored_sub: MonitoredSub,
    ...
) -> None:
    """Check a submission for reposts and spam."""
    # ... existing repost detection logic ...

    # New: Check for spam if enabled
    spam_config = get_spam_config(monitored_sub)

    if spam_config.enabled:
        await self._check_author_for_spam(
            submission=submission,
            monitored_sub=monitored_sub,
            spam_config=spam_config,
            is_repost=repost_detected,
        )
```

**Key Features:**
- Non-blocking async execution
- Respects whitelist (verified_legit users skipped)
- Respects cache (recently analyzed users skipped)
- Requires minimum 3 posts for analysis
- High priority queue if repost detected

### 3.2 Summons Integration

**File:** `redditrepostsleuth/summonssvc/summonshandler.py`

Integration when bot is summoned:

```python
async def handle_summons(self, summons: Summons) -> None:
    """Handle a bot summons."""
    # ... existing summons logic ...

    # New: Queue spam analysis for post author
    if summons.post and summons.post.author:
        author = summons.post.author
        if author != summons.requestor:  # Don't analyze summoner
            self._queue_spam_analysis(author, priority='low')
```

**Key Features:**
- Analyzes post author (not requestor)
- Low priority background task
- Respects whitelist and cache
- Non-blocking

---

## Component 4: Scheduled Tasks

### Schedule Configuration

**File:** `celeryconfig.py`

```python
CELERYBEAT_SCHEDULE = {
    'analyze-top-reposters-daily': {
        'task': 'redditrepostsleuth.core.celery.tasks.spam_detection_tasks.scheduled_analyze_top_reposters',
        'schedule': crontab(hour=3, minute=0),  # 3 AM UTC
        'options': {'queue': 'spam_detection'},
    },

    'enrich-high-risk-users-daily': {
        'task': 'redditrepostsleuth.core.celery.tasks.spam_detection_tasks.scheduled_enrich_high_risk',
        'schedule': crontab(hour=4, minute=0),  # 4 AM UTC
        'options': {'queue': 'spam_detection'},
    },

    'cleanup-old-features-weekly': {
        'task': 'redditrepostsleuth.core.celery.tasks.spam_detection_tasks.scheduled_cleanup_features',
        'schedule': crontab(day_of_week=0, hour=5, minute=0),  # Sunday 5 AM
        'options': {'queue': 'spam_detection'},
    },

    'purge-old-activity-tracking-weekly': {
        'task': 'redditrepostsleuth.core.celery.tasks.spam_detection_tasks.scheduled_purge_activity_tracking',
        'schedule': crontab(day_of_week=0, hour=6, minute=0),  # Sunday 6 AM
        'options': {'queue': 'spam_detection'},
    },
}
```

### Task Details

**1. scheduled_analyze_top_reposters** (Daily 3 AM UTC)
```python
@shared_task(bind=True, base=SqlAlchemyTask, queue='spam_detection')
def scheduled_analyze_top_reposters(self) -> dict:
    """Analyze top reposters for spam."""
    return score_top_reposters(
        limit=100,      # Top 100 reposters
        days=7,         # Last 7 days
        min_reposts=3   # At least 3 reposts
    )
```

**Purpose:** Identify high-volume reposters likely to be spam
**Output:** Dict with `analyzed_count` and `high_risk_count`

**2. scheduled_enrich_high_risk** (Daily 4 AM UTC)
```python
@shared_task(bind=True, base=RedditTask, queue='spam_detection')
def scheduled_enrich_high_risk(self) -> dict:
    """Enrich Tier 2 data for high-risk users."""
    return enrich_high_risk_users(
        min_score=0.5,  # Spam score >= 0.5
        limit=50        # Process 50 users
    )
```

**Purpose:** Fetch Reddit API data for potentially risky users
**Output:** Dict with success/failure counts
**Rate Limited:** 50 req/min via circuit breaker + rate limiter

**3. scheduled_cleanup_features** (Weekly Sunday 5 AM UTC)
```python
@shared_task(bind=True, base=SqlAlchemyTask, queue='spam_detection')
def scheduled_cleanup_features(self) -> dict:
    """Clean up old feature records."""
    return cleanup_old_feature_records(keep_per_user=5)
```

**Purpose:** Maintain database, keep last 5 feature snapshots per user
**Output:** Dict with `deleted_count`

**4. scheduled_purge_activity_tracking** (Weekly Sunday 6 AM UTC)
```python
@shared_task(bind=True, base=SqlAlchemyTask, queue='spam_detection')
def scheduled_purge_activity_tracking(self) -> dict:
    """Purge old activity tracking records."""
    with self.uowm.start() as uow:
        deleted = uow.author_activity.purge_old_records(days=180)
        uow.commit()
    return {'deleted': deleted}
```

**Purpose:** Archive old post activity data (keep 6 months)
**Output:** Dict with count of deleted records

---

## Component 5: Admin API Endpoints

### Endpoints Summary

**Base URL:** `/api/admin/spam/`

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/score` | Trigger spam scoring for user |
| GET | `/user/{username}` | Get user spam details |
| GET | `/high-risk` | List high-risk users |
| POST | `/label` | Manually label user SPAM/LEGITIMATE |
| GET | `/stats` | Detection statistics |

### Endpoint Details

#### 1. POST /api/admin/spam/score

**Purpose:** Manually trigger spam scoring for a user

**Request:**
```json
{
    "username": "SomeUser",
    "enrich_tier2": false
}
```

**Response:**
```json
{
    "status": "queued",
    "task_id": "abc123def456",
    "username": "SomeUser"
}
```

**Implementation:**
```python
class SpamScoreUserEndpoint:
    def on_post(self, req, resp):
        data = req.media
        username = data.get('username')
        enrich_tier2 = data.get('enrich_tier2', False)

        if enrich_tier2:
            task = score_with_tier2.delay(username)
        else:
            task = score_and_flag_user.delay(username, update_user_review=True)

        resp.media = {
            'status': 'queued',
            'task_id': task.id,
            'username': username,
        }
```

#### 2. GET /api/admin/spam/user/{username}

**Purpose:** Get detailed spam information for a user

**Response:**
```json
{
    "username": "SomeUser",
    "features": {
        "total_posts_indexed": 42,
        "repost_ratio": 0.33,
        "posting_entropy": 0.7,
        "spam_subreddit_posts": 5,
        ...
    },
    "review": {
        "spam_score": 0.72,
        "risk_level": "HIGH",
        "is_verified_spam": false,
        "is_verified_legit": false
    },
    "activity_count": 42
}
```

#### 3. GET /api/admin/spam/high-risk

**Purpose:** List users flagged as high-risk for spam

**Query Parameters:**
- `min_score` (float, default 0.6) - Minimum spam score
- `limit` (int, default 50) - Max users to return

**Request:** `GET /api/admin/spam/high-risk?min_score=0.7&limit=100`

**Response:**
```json
{
    "users": [
        {
            "username": "SpamUser1",
            "score": 0.85,
            "risk_level": "CRITICAL",
            "computed_at": "2026-01-27T10:30:00",
            "top_factors": [
                "High repost ratio (0.68)",
                "Posts in spam subreddits (8)",
                "Suspicious username pattern"
            ]
        },
        ...
    ],
    "total": 23
}
```

#### 4. POST /api/admin/spam/label

**Purpose:** Manually label a user as SPAM or LEGITIMATE for training data

**Request:**
```json
{
    "username": "SomeUser",
    "label": "SPAM",
    "notes": "Confirmed adult promoter",
    "source_url": "https://reddit.com/r/subreddit/comments/xxx"
}
```

**Response:**
```json
{
    "status": "labeled",
    "username": "SomeUser",
    "label": "SPAM"
}
```

**Side Effects:**
- Creates record in `spam_training_labels` table
- Updates `user_review` table with label status
- Label confidence = 1.0 (manual label)
- Can be used for ML model training (Phase 6)

#### 5. GET /api/admin/spam/stats

**Purpose:** Get overall spam detection statistics

**Response:**
```json
{
    "training_labels": {
        "SPAM": 234,
        "LEGITIMATE": 156,
        "DISPUTED": 12
    },
    "risk_distribution": {
        "LOW": 1000,
        "MEDIUM": 450,
        "HIGH": 120,
        "CRITICAL": 45
    },
    "analyzed_last_7_days": 567
}
```

**Metrics Provided:**
- Training label distribution
- Risk level distribution
- Recent analysis activity

---

## Shadow Mode

### Overview

Shadow mode allows safe testing without taking automated actions. Enable via environment:

```bash
SPAM_DETECTION_SHADOW_MODE=true
```

### Behavior

**With Shadow Mode OFF (production):**
- SpamActionHandler executes remove_post, ban_user, notify_modmail
- Database audit log created
- Moderators see immediate action

**With Shadow Mode ON (testing):**
- All actions logged to database
- Actions marked as "proposed" not "executed"
- No actual mod actions taken
- Allows safe validation before production

### Monitoring Shadow Mode

Logs all proposed actions with full details:

```python
log.info(
    "SHADOW_MODE: Proposed action",
    extra={
        'username': username,
        'score': score,
        'risk_level': risk_level,
        'would_remove_post': would_remove,
        'would_ban_user': would_ban,
        'reason': reasons,
        'timestamp': datetime.utcnow().isoformat(),
    }
)
```

### Transition to Production

1. Deploy with SPAM_DETECTION_SHADOW_MODE=true
2. Monitor logs for false positives (target <5%)
3. Validate scoring accuracy against known spam/legitimate users
4. Enable gradually per-subreddit:
   - Start with notify_mod_mail only
   - Move to remove_post if accuracy good
   - Finally enable ban_user after threshold testing

---

## Database Audit Trail

### user_review Table Extensions

Columns added to track spam detection:

```python
class UserReview(Base):
    # ... existing columns ...
    spam_score = Column(Float)           # Overall spam score
    risk_level = Column(String(20))      # LOW/MEDIUM/HIGH/CRITICAL
    spam_score_updated_at = Column(DateTime)
    needs_review_spam = Column(Boolean)  # Flagged by system
    is_verified_spam = Column(Boolean)   # Admin confirmed SPAM
    is_verified_legit = Column(Boolean)  # Admin confirmed LEGITIMATE
```

### Action Logging

All actions recorded:
- Who (username)
- What (action type: remove/ban/notify)
- When (timestamp)
- Why (score, risk level, factors)
- Result (success/failure with error if failed)

---

## Testing Checklist

### Pre-Deployment
- [ ] SpamDetectionConfig loads correctly from MonitoredSub
- [ ] Default values are conservative (log-only)
- [ ] Threshold logic works (should_take_action)
- [ ] Action threshold correctly determines action eligibility

### Integration
- [ ] Repost detection triggers spam analysis
- [ ] Analysis respects whitelist (verified_legit)
- [ ] Analysis respects cache (recently analyzed)
- [ ] Recently analyzed users are skipped
- [ ] Summons trigger spam analysis for post author

### Action Handler
- [ ] Post removal executes when configured
- [ ] User banning executes when configured
- [ ] Modmail notification sends when configured
- [ ] All actions logged to database
- [ ] Shadow mode prevents action execution

### Scheduled Tasks
- [ ] Top reposter analysis runs at scheduled time
- [ ] Tier 2 enrichment runs on schedule
- [ ] Cleanup task executes without errors
- [ ] Purge task removes old records correctly

### Admin API
- [ ] POST /api/admin/spam/score queues task
- [ ] GET /api/admin/spam/user/{username} returns user data
- [ ] GET /api/admin/spam/high-risk lists high-risk users
- [ ] POST /api/admin/spam/label creates training label
- [ ] GET /api/admin/spam/stats returns statistics

---

## Metrics & Monitoring

### Key Performance Indicators

| Metric | Target | Tool |
|--------|--------|------|
| False Positive Rate | <5% | Manual review of HIGH/CRITICAL users |
| False Negative Rate | <20% | Compare against known spam sources |
| Action Success Rate | >95% | Monitor logs |
| API Latency | <500ms | Celery task monitoring |
| Scheduled Task Success | 100% | Celery flower dashboard |

### Logging

All spam detection events logged with:
- Username
- Spam score
- Risk level
- Contributing factors
- Action taken (or proposed in shadow mode)
- Result (success/failure)

### Alerts

Configure alerts for:
- High failure rate in spam actions
- Circuit breaker OPEN state
- Scheduled task failures
- Unusual spike in HIGH/CRITICAL scores

---

## Configuration Examples

### Conservative Setup (Starting Point)

```python
# In monitored subreddit config
spam_detection_enabled = True
spam_detection_remove_post = False  # Log only
spam_detection_ban_user = False     # Log only
spam_detection_notify_mod_mail = True  # Notify mods
spam_detection_score_threshold = 0.8  # High threshold
removal_reason = "Automated spam detection"
ban_reason = "Spam account"

# Environment variable
SPAM_DETECTION_SHADOW_MODE=true
```

### Aggressive Setup (After Validation)

```python
# In monitored subreddit config
spam_detection_enabled = True
spam_detection_remove_post = True   # Actually remove
spam_detection_ban_user = True      # Actually ban
spam_detection_notify_mod_mail = True  # Notify mods
spam_detection_score_threshold = 0.7  # Standard threshold
removal_reason = "This post was flagged as spam by automated detection"
ban_reason = "Your account has been identified as spam"

# Environment variable
SPAM_DETECTION_SHADOW_MODE=false
```

---

## Troubleshooting

### No Spam Analysis Triggered

**Check:**
1. Is `spam_detection_enabled=true` in MonitoredSub?
2. Is post author's account active (not deleted)?
3. Does author have minimum 3 posts?
4. Is author on verified_legit whitelist?
5. Was user recently analyzed? (cached for 7 days)

### Actions Not Executing

**Check:**
1. Is SPAM_DETECTION_SHADOW_MODE=true? (disables execution)
2. Is spam score >= configured threshold?
3. Is action enabled in config (remove_post, ban_user)?
4. Check Celery task logs for errors
5. Check Reddit API error logs (rate limit, permissions)

### High False Positive Rate

**Action:**
1. Increase score_threshold to 0.75 or 0.8
2. Disable ban_user action, keep remove_post only
3. Monitor shadow mode logs longer
4. Adjust feature weights in spam_scorer.py
5. Review and label false positives for training data

### High False Negative Rate

**Action:**
1. Review missed spam in r/TheseFuckingAccounts
2. Lower score_threshold to 0.65 or 0.6
3. Enable more aggressive Tier 2 enrichment
4. Check which features are NOT triggering for known spam
5. Adjust feature weights accordingly

---

## Files Summary

### Created Files
- `redditrepostsleuth/core/services/spam/spam_config_helper.py` (100 lines)
- `redditrepostsleuth/core/services/spam/spam_action_handler.py` (280 lines)
- `redditrepostsleuth/repostsleuthsiteapi/endpoints/spam_admin.py` (400 lines)

### Modified Files
- `redditrepostsleuth/core/celery/celeryconfig.py` - Added 4 beat schedules
- `redditrepostsleuth/core/celery/task_logic/monitored_sub_task_logic.py` - Added spam check
- `redditrepostsleuth/summonssvc/summonshandler.py` - Added spam queue
- `redditrepostsleuth/core/celery/tasks/spam_detection_tasks.py` - Added wrapper tasks
- `redditrepostsleuth/repostsleuthsiteapi/app.py` - Registered endpoints

### Database
- MonitoredSub: 7 spam detection columns (already present in schema)
- UserReview: spam_score, risk_level, related columns (already present)

---

## Next Steps

### Immediate (Current)
- Deploy to staging with SPAM_DETECTION_SHADOW_MODE=true
- Monitor false positive rate in logs
- Validate action handler behavior

### Short Term (1 Week)
- Run shadow mode for 3-5 days minimum
- Manual validation against known spam accounts
- Enable for 2-3 trusted subreddits first
- Monitor feedback from moderators

### Medium Term (2-3 Weeks)
- Gradual rollout to more subreddits
- Start with notify_mod_mail only
- Progress to remove_post if no issues
- Finally enable ban_user with high thresholds

### Long Term
- Integrate with Phase 5 (training data collection)
- Train ML models (Phase 6) for continuous improvement
- Add more triggers (user page profile, comment analysis)
- Implement user appeal/review mechanism

---

## References

- Configuration Reference: `configuration-reference.md`
- Scoring Engine: `scoring-engine-reference.md`
- Tier 2 Enrichment: `tier2-enrichment-usage.md`
- Overall Flow: `spam-detection-flow.md`

