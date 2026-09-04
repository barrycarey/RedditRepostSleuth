# Phase 4: Trigger Integration

## Overview
- **Duration**: Week 9-10
- **Dependencies**: Phase 3 (Tier 2 enrichment)
- **Goal**: Integrate spam detection into existing workflows

---

## Table of Contents
1. [Phase 4.5: Shadow Mode & Production Validation](#1-phase-45-shadow-mode--production-validation)
2. [Trigger Points](#2-trigger-points)
3. [MonitoredSub Configuration](#3-monitoredsub-configuration)
4. [Repost Detection Integration](#4-repost-detection-integration)
5. [Summons Integration](#5-summons-integration)
6. [Action Handler](#6-action-handler)
7. [Scheduled Tasks](#7-scheduled-tasks)
8. [Admin API Endpoints](#8-admin-api-endpoints)
9. [Testing Strategy](#9-testing-strategy)
10. [Verification Checklist](#10-verification-checklist)

---

## 1. Phase 4.5: Shadow Mode & Production Validation

### Overview

Before enabling automated actions (remove posts, ban users), run the system in **shadow mode** (2-4 weeks):

- Score all posts/users normally
- Log scores and proposed actions
- **Do NOT take any automated actions**
- Manually validate against known spam accounts
- Measure false positive and false negative rates

### Rollout Criteria

| Metric | Success Criteria | Validation Method |
|--------|-----------------|------------------|
| **False Positive Rate** | <5% | Manual review of 100 random HIGH/CRITICAL scored users |
| **False Negative Rate** | <20% | Check against r/TheseFuckingAccounts reports |
| **Correctly Scored** | >80% accuracy | Compare scores against labeled training data |
| **No Critical Errors** | Zero unhandled exceptions | Check error logs, circuit breaker health |
| **Performance** | <500ms/user | Monitor processing latency percentiles |
| **API Health** | 99%+ success rate | Track API call success rates |

### Shadow Mode Configuration

```python
# In config/environment
SPAM_DETECTION_ENABLED = True
SPAM_DETECTION_SHADOW_MODE = True  # Don't take actions
SPAM_DETECTION_AUTO_ACTIONS_ENABLED = False  # Extra safety
```

### Shadow Mode Logging

Log all proposed actions for analysis:

```python
def handle_spam_detection_result(username: str, score: ScoringResult, config: SpamDetectionConfig):
    """Handle scoring result in shadow mode."""

    log.info(
        "SHADOW_MODE: Proposed action",
        extra={
            'username': username,
            'score': score.score,
            'risk_level': score.risk_level,
            'would_remove_post': config.remove_post and score.score >= config.score_threshold,
            'would_ban_user': config.ban_user and score.score >= config.score_threshold,
            'reason': score.reasons,
            'timestamp': datetime.utcnow().isoformat(),
        }
    )

    # In shadow mode: only log, don't take action
    if not config.should_take_action(score.score):
        return

    # Log what would happen
    actions = config.get_actions(score.score)
    for action, enabled in actions.items():
        if enabled:
            log.warning(f"SHADOW_MODE: Would {action} for {username}")
```

### Validation Workflow

1. **Week 1-2: Shadow Mode Monitoring**
   - [ ] Collect 1000+ scored users
   - [ ] Monitor false positive rate
   - [ ] Check circuit breaker health

2. **Week 2-3: Known Account Validation**
   - [ ] Test against 50 known spam accounts
   - [ ] Test against 50 known legitimate accounts
   - [ ] Calculate confusion matrix (TP, TN, FP, FN)

3. **Week 3-4: Threshold Tuning**
   - [ ] Adjust score thresholds if needed
   - [ ] Re-validate against known accounts
   - [ ] Prepare for production launch

### Rollback Procedures

If false positive rate >5% or critical issues found:

**Automated Rollback Script**:

```bash
#!/bin/bash
# rollback_spam_detection.sh

# Disable spam detection immediately
kubectl set env deployment/bot \
  SPAM_DETECTION_ENABLED=false

# Switch to shadow mode
kubectl set env deployment/bot \
  SPAM_DETECTION_SHADOW_MODE=true

# Clear any pending spam actions
psql -c "UPDATE user_review SET \
  spam_detection_action_taken = false \
  WHERE spam_detection_action_taken = true \
  AND spam_detection_action_taken_at > NOW() - INTERVAL 1 HOUR"

# Notify ops
curl -X POST https://hooks.slack.com/... \
  -d 'Spam detection rolled back due to high false positive rate'

echo "Rollback complete. Check logs at ops dashboard."
```

**Manual Rollback**:

1. Disable feature flag: `SPAM_DETECTION_ENABLED = False`
2. Restart bot services: `kubectl rollout restart deployment/bot`
3. Revert any removed posts: `SELECT * FROM moderation_audit WHERE action='remove'`
4. Restore any banned users: `SELECT * FROM bans WHERE automatic_spam_ban=true`
5. Review logs: `kubectl logs -l app=bot --tail=10000 | grep SPAM`

---

## 2. Trigger Points

### When to Analyze Users

| Trigger | When | Priority | Depth |
|---------|------|----------|-------|
| **Repost Detection** | User's post is detected as repost | High | Tier 1 |
| **Summons** | Bot summoned on user's post | Medium | Tier 1 |
| **High Volume** | Existing high-volume reposter detection | High | Tier 1+2 |
| **Scheduled** | Periodic analysis of top reposters | Low | Tier 1+2 |
| **Manual** | Admin triggers analysis | High | Full |
| **MonitoredSub Post** | New post in monitored sub (if enabled) | Medium | Tier 1 |

### Analysis Decision Flow

```
┌─────────────────────┐
│  Trigger Event      │
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐     Yes    ┌─────────────────────┐
│ Is user on          │───────────▶│ Skip analysis       │
│ verified_legit?     │            │ (whitelisted)       │
└─────────┬───────────┘            └─────────────────────┘
          │ No
          ▼
┌─────────────────────┐     Yes    ┌─────────────────────┐
│ Recently analyzed?  │───────────▶│ Use cached score    │
│ (within 7 days)     │            │                     │
└─────────┬───────────┘            └─────────────────────┘
          │ No
          ▼
┌─────────────────────┐     No     ┌─────────────────────┐
│ Enough data for     │───────────▶│ Queue for later     │
│ analysis? (≥3 posts)│            │ (insufficient data) │
└─────────┬───────────┘            └─────────────────────┘
          │ Yes
          ▼
┌─────────────────────┐
│ Queue spam analysis │
│ task                │
└─────────────────────┘
```

---

## 3. MonitoredSub Configuration

### Database Schema (From Phase 0)

Already defined in Phase 0 migration:

```python
# In MonitoredSub model
spam_detection_enabled = Column(Boolean, default=False)
spam_detection_remove_post = Column(Boolean, default=False)
spam_detection_ban_user = Column(Boolean, default=False)
spam_detection_notify_mod_mail = Column(Boolean, default=False)
spam_detection_score_threshold = Column(Float, default=0.7)
spam_detection_removal_reason = Column(String(300))
spam_detection_ban_reason = Column(String(300))
```

### Configuration Helper

**File**: `redditrepostsleuth/core/services/spam/spam_config_helper.py`

```python
"""
Spam Detection Configuration Helper

Provides easy access to spam detection settings for a MonitoredSub.
"""
from dataclasses import dataclass
from typing import Optional

from redditrepostsleuth.core.db.databasemodels import MonitoredSub


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
        """
        Get actions to take based on score.

        Returns dict of action -> should_take
        """
        if not self.should_take_action(score):
            return {
                'remove_post': False,
                'ban_user': False,
                'notify_mod_mail': False,
            }

        return {
            'remove_post': self.remove_post,
            'ban_user': self.ban_user,
            'notify_mod_mail': self.notify_mod_mail,
        }


def get_spam_config(monitored_sub: MonitoredSub) -> SpamDetectionConfig:
    """
    Get spam detection config for a monitored sub.

    Convenience function for use in task logic.
    """
    return SpamDetectionConfig.from_monitored_sub(monitored_sub)
```

### Default Configuration Values

| Setting | Default | Recommended Initial |
|---------|---------|---------------------|
| `enabled` | False | False (opt-in) |
| `remove_post` | False | False (log only initially) |
| `ban_user` | False | False (log only initially) |
| `notify_mod_mail` | False | True (for awareness) |
| `score_threshold` | 0.7 | 0.8 (conservative) |

---

## 4. Repost Detection Integration

### Integration Point

The main integration point is in the monitored sub task logic.

**File**: `redditrepostsleuth/core/celery/task_logic/monitored_sub_task_logic.py`

Add spam detection check after repost detection:

```python
# At top of file, add imports
from redditrepostsleuth.core.services.spam.spam_config_helper import get_spam_config
from redditrepostsleuth.core.celery.tasks.spam_detection_tasks import (
    score_and_flag_user,
    score_with_tier2,
)


async def check_submission(
    self,
    submission: Submission,
    monitored_sub: MonitoredSub,
    ...
) -> None:
    """
    Check a submission for reposts and spam.

    Extended to include spam detection when enabled.
    """
    # ... existing repost detection logic ...

    # After repost detection, check for spam if enabled
    spam_config = get_spam_config(monitored_sub)

    if spam_config.enabled:
        await self._check_author_for_spam(
            submission=submission,
            monitored_sub=monitored_sub,
            spam_config=spam_config,
            is_repost=repost_detected,  # From repost detection above
        )

    # ... rest of existing logic ...


async def _check_author_for_spam(
    self,
    submission: Submission,
    monitored_sub: MonitoredSub,
    spam_config: SpamDetectionConfig,
    is_repost: bool = False,
) -> Optional[ScoringResult]:
    """
    Check submission author for spam indicators.

    Args:
        submission: The Reddit submission
        monitored_sub: The monitored subreddit config
        spam_config: Spam detection configuration
        is_repost: Whether this submission is a repost

    Returns:
        ScoringResult if analysis performed, None otherwise
    """
    author = submission.author.name if submission.author else None

    if not author or author == '[deleted]':
        return None

    # Check if user should be analyzed
    if not self._should_analyze_user(author):
        log.debug(f"Skipping spam analysis for {author}")
        return None

    # Prioritize analysis if this is a repost
    # Reposts from spam accounts are higher priority
    priority = 'high' if is_repost else 'normal'

    # Queue async analysis
    # Use .delay() to not block the main flow
    task = score_and_flag_user.apply_async(
        args=[author],
        kwargs={'update_user_review': True},
        priority=10 if priority == 'high' else 5,
    )

    # For immediate action, we need the result
    # Only wait if actions are configured
    if spam_config.remove_post or spam_config.ban_user:
        try:
            # Wait up to 5 seconds for result
            result = task.get(timeout=5.0)

            if result and result['score'] >= spam_config.score_threshold:
                await self._handle_spam_detection(
                    submission=submission,
                    monitored_sub=monitored_sub,
                    spam_config=spam_config,
                    scoring_result=result,
                )
                return result

        except TimeoutError:
            log.warning(f"Spam analysis timed out for {author}")
            # Don't block - analysis will complete async

    return None


def _should_analyze_user(self, username: str) -> bool:
    """
    Determine if a user should be analyzed for spam.

    Skips:
    - Verified legitimate users
    - Recently analyzed users
    - Users with insufficient data
    """
    with self.uowm.start() as uow:
        # Check whitelist (verified legitimate)
        review = uow.user_review.get_by_username(username)
        if review and review.is_verified_legit:
            return False

        # Check if recently analyzed
        if uow.spam_features.user_was_recently_analyzed(username, within_days=7):
            return False

        # Check if enough data (at least 3 posts tracked)
        count = uow.author_activity.get_author_count(username)
        if count < 3:
            return False

    return True


async def _handle_spam_detection(
    self,
    submission: Submission,
    monitored_sub: MonitoredSub,
    spam_config: SpamDetectionConfig,
    scoring_result: dict,
) -> None:
    """
    Handle detected spam based on configuration.

    Takes configured actions: remove, ban, notify.
    """
    author = submission.author.name
    score = scoring_result['score']
    risk_level = scoring_result['risk_level']
    reasons = scoring_result.get('reasons', [])

    log.info(
        f"Spam detected in r/{monitored_sub.name}: "
        f"u/{author} score={score:.2f} ({risk_level})"
    )

    actions_taken = []

    # Remove post if configured
    if spam_config.remove_post:
        try:
            removal_reason = spam_config.removal_reason or (
                f"Automated spam detection (score: {score:.2f})"
            )
            submission.mod.remove(spam=True, mod_note=removal_reason)
            actions_taken.append('removed')
            log.info(f"Removed spam post {submission.id} by u/{author}")
        except Exception as e:
            log.error(f"Failed to remove spam post: {e}")

    # Ban user if configured
    if spam_config.ban_user:
        try:
            ban_reason = spam_config.ban_reason or (
                f"Spam account (detection score: {score:.2f})"
            )
            monitored_sub_obj = self.reddit.subreddit(monitored_sub.name)
            monitored_sub_obj.banned.add(
                author,
                ban_reason=ban_reason,
                ban_message=f"Your account has been flagged as spam. Score: {score:.2f}",
                note=f"Automated spam detection. Reasons: {', '.join(reasons[:3])}"
            )
            actions_taken.append('banned')
            log.info(f"Banned spam user u/{author} from r/{monitored_sub.name}")
        except Exception as e:
            log.error(f"Failed to ban spam user: {e}")

    # Notify via modmail if configured
    if spam_config.notify_mod_mail:
        try:
            await self._send_spam_modmail(
                monitored_sub=monitored_sub,
                submission=submission,
                scoring_result=scoring_result,
                actions_taken=actions_taken,
            )
        except Exception as e:
            log.error(f"Failed to send spam modmail: {e}")


async def _send_spam_modmail(
    self,
    monitored_sub: MonitoredSub,
    submission: Submission,
    scoring_result: dict,
    actions_taken: list,
) -> None:
    """Send modmail notification about spam detection."""
    author = submission.author.name
    score = scoring_result['score']
    risk_level = scoring_result['risk_level']
    reasons = scoring_result.get('reasons', [])

    subject = f"[Spam Detection] {risk_level} risk user detected"

    body = f"""
**Spam Detection Alert**

**User:** u/{author}
**Post:** [{submission.title}]({submission.permalink})
**Spam Score:** {score:.2f} ({risk_level})

**Contributing Factors:**
{chr(10).join(f'- {r}' for r in reasons[:5])}

**Actions Taken:**
{chr(10).join(f'- {a}' for a in actions_taken) if actions_taken else '- None (logging only)'}

---
*This is an automated message from RepostSleuthBot spam detection.*
*Configure spam detection settings in the wiki or contact the bot admin.*
"""

    subreddit = self.reddit.subreddit(monitored_sub.name)
    subreddit.message(subject, body)
```

---

## 5. Summons Integration

### Integration Point

When the bot is summoned on a post, analyze the post author.

**File**: `redditrepostsleuth/summonssvc/summons_handler.py`

```python
# Add to summons handling logic

async def handle_summons(self, summons: Summons) -> None:
    """Handle a bot summons."""
    # ... existing summons logic ...

    # After processing summons, queue spam analysis for post author
    if summons.post and summons.post.author:
        author = summons.post.author

        # Don't analyze the person who summoned (requestor)
        # Analyze the post author instead
        if author != summons.requestor:
            self._queue_spam_analysis(author, priority='low')


def _queue_spam_analysis(self, username: str, priority: str = 'normal') -> None:
    """Queue spam analysis for a user."""
    from redditrepostsleuth.core.celery.tasks.spam_detection_tasks import (
        score_and_flag_user
    )

    # Check if worth analyzing
    with self.uowm.start() as uow:
        review = uow.user_review.get_by_username(username)
        if review and review.is_verified_legit:
            return  # Skip whitelisted

        if uow.spam_features.user_was_recently_analyzed(username, within_days=7):
            return  # Recently analyzed

    # Queue for background processing
    task_priority = 3 if priority == 'high' else 7
    score_and_flag_user.apply_async(
        args=[username],
        kwargs={'update_user_review': True},
        priority=task_priority,
    )
```

---

## 6. Action Handler

### Centralized Action Handler

**File**: `redditrepostsleuth/core/services/spam/spam_action_handler.py`

```python
"""
Spam Action Handler

Centralizes spam detection actions (remove, ban, notify).
"""
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from praw import Reddit
from praw.models import Submission

from redditrepostsleuth.core.db.databasemodels import MonitoredSub
from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.core.services.spam.spam_config_helper import SpamDetectionConfig

log = logging.getLogger(__name__)


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
    """
    Handles actions for detected spam.

    Provides consistent action handling across all trigger points.
    """

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
        """
        Handle spam detection with configured actions.

        Args:
            username: Detected spam user
            score: Spam score
            risk_level: Risk classification
            reasons: Contributing factors
            submission: Optional submission that triggered detection
            monitored_sub: Optional monitored sub for config
            config: Optional override config

        Returns:
            SpamActionResult with action outcomes
        """
        result = SpamActionResult(
            username=username,
            score=score,
            risk_level=risk_level,
            actions_attempted=[],
            actions_succeeded=[],
            actions_failed=[],
            error_messages=[],
        )

        # Get config
        if config is None and monitored_sub:
            from redditrepostsleuth.core.services.spam.spam_config_helper import (
                get_spam_config
            )
            config = get_spam_config(monitored_sub)

        if config is None:
            # No config = log only mode
            log.info(
                f"Spam detected (log only): u/{username} "
                f"score={score:.2f} ({risk_level})"
            )
            self._log_detection(username, score, risk_level, reasons, submission)
            return result

        # Check if action threshold met
        if not config.should_take_action(score):
            log.debug(
                f"Score {score:.2f} below threshold {config.score_threshold} "
                f"for u/{username}"
            )
            return result

        # Execute actions
        actions = config.get_actions(score)

        if actions['remove_post'] and submission:
            result.actions_attempted.append('remove_post')
            if self._remove_post(submission, config.removal_reason, reasons):
                result.actions_succeeded.append('remove_post')
            else:
                result.actions_failed.append('remove_post')

        if actions['ban_user'] and monitored_sub:
            result.actions_attempted.append('ban_user')
            if self._ban_user(username, monitored_sub, config.ban_reason, score, reasons):
                result.actions_succeeded.append('ban_user')
            else:
                result.actions_failed.append('ban_user')

        if actions['notify_mod_mail'] and monitored_sub:
            result.actions_attempted.append('notify_mod_mail')
            if self._notify_modmail(
                username, monitored_sub, submission, score, risk_level, reasons,
                result.actions_succeeded
            ):
                result.actions_succeeded.append('notify_mod_mail')
            else:
                result.actions_failed.append('notify_mod_mail')

        # Always log the detection
        self._log_detection(username, score, risk_level, reasons, submission)

        return result

    def _remove_post(
        self,
        submission: Submission,
        reason: Optional[str],
        factors: List[str]
    ) -> bool:
        """Remove a spam post."""
        try:
            mod_note = reason or "Automated spam detection"
            submission.mod.remove(spam=True, mod_note=mod_note)
            log.info(f"Removed spam post {submission.id}")
            return True
        except Exception as e:
            log.error(f"Failed to remove post {submission.id}: {e}")
            return False

    def _ban_user(
        self,
        username: str,
        monitored_sub: MonitoredSub,
        reason: Optional[str],
        score: float,
        factors: List[str]
    ) -> bool:
        """Ban a spam user from the subreddit."""
        try:
            subreddit = self.reddit.subreddit(monitored_sub.name)
            ban_reason = reason or f"Spam account (score: {score:.2f})"

            subreddit.banned.add(
                username,
                ban_reason=ban_reason[:100],  # Reddit limit
                ban_message=(
                    f"Your account has been identified as spam. "
                    f"If you believe this is an error, please contact the moderators."
                ),
                note=f"Auto-ban: spam score {score:.2f}. Factors: {', '.join(factors[:2])}"[:300]
            )
            log.info(f"Banned u/{username} from r/{monitored_sub.name}")
            return True
        except Exception as e:
            log.error(f"Failed to ban u/{username}: {e}")
            return False

    def _notify_modmail(
        self,
        username: str,
        monitored_sub: MonitoredSub,
        submission: Optional[Submission],
        score: float,
        risk_level: str,
        factors: List[str],
        actions_taken: List[str]
    ) -> bool:
        """Send modmail notification."""
        try:
            subreddit = self.reddit.subreddit(monitored_sub.name)

            subject = f"[Spam Alert] {risk_level} risk: u/{username}"

            post_info = ""
            if submission:
                post_info = f"""
**Post:** [{submission.title[:50]}...]({submission.permalink})
"""

            body = f"""
## Spam Detection Alert

**User:** u/{username}
**Score:** {score:.2f} ({risk_level})
{post_info}
**Top Factors:**
{chr(10).join(f'- {f}' for f in factors[:5])}

**Actions Taken:** {', '.join(actions_taken) if actions_taken else 'None (logging only)'}

---
*Automated message from RepostSleuthBot*
"""

            subreddit.message(subject, body)
            log.info(f"Sent spam modmail for u/{username} to r/{monitored_sub.name}")
            return True
        except Exception as e:
            log.error(f"Failed to send modmail: {e}")
            return False

    def _log_detection(
        self,
        username: str,
        score: float,
        risk_level: str,
        factors: List[str],
        submission: Optional[Submission]
    ) -> None:
        """Log spam detection to database."""
        with self.uowm.start() as uow:
            review = uow.user_review.get_by_username(username)
            if review:
                review.spam_score = score
                review.risk_level = risk_level
                review.spam_score_updated_at = datetime.utcnow()
            else:
                from redditrepostsleuth.core.db.databasemodels import UserReview
                review = UserReview(
                    username=username,
                    spam_score=score,
                    risk_level=risk_level,
                    spam_score_updated_at=datetime.utcnow(),
                )
                uow.session.add(review)
            uow.commit()
```

---

## 7. Scheduled Tasks

### Periodic Analysis Tasks

**File**: `redditrepostsleuth/core/celery/tasks/spam_detection_tasks.py`

Add scheduled tasks:

```python
from celery.schedules import crontab


# Add to celery beat schedule (in celeryconfig.py or separate schedule file)
CELERYBEAT_SCHEDULE = {
    # ... existing schedules ...

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


@shared_task(bind=True, base=SqlAlchemyTask, queue='spam_detection')
def scheduled_analyze_top_reposters(self) -> dict:
    """
    Scheduled task: Analyze top reposters for spam.

    Runs daily at 3 AM UTC during low-traffic period.
    """
    log.info("Starting scheduled top reposter analysis")
    return score_top_reposters(
        limit=100,
        days=7,
        min_reposts=3
    )


@shared_task(bind=True, base=RedditTask, queue='spam_detection')
def scheduled_enrich_high_risk(self) -> dict:
    """
    Scheduled task: Enrich Tier 2 data for high-risk users.

    Runs daily at 4 AM UTC.
    """
    log.info("Starting scheduled Tier 2 enrichment")
    return enrich_high_risk_users(
        min_score=0.5,
        limit=50
    )


@shared_task(bind=True, base=SqlAlchemyTask, queue='spam_detection')
def scheduled_cleanup_features(self) -> dict:
    """
    Scheduled task: Clean up old feature records.

    Runs weekly on Sunday at 5 AM UTC.
    """
    log.info("Starting scheduled feature cleanup")
    return cleanup_old_feature_records(keep_per_user=5)


@shared_task(bind=True, base=SqlAlchemyTask, queue='spam_detection')
def scheduled_purge_activity_tracking(self) -> dict:
    """
    Scheduled task: Purge old activity tracking records.

    Runs weekly on Sunday at 6 AM UTC.
    Keeps last 180 days of data.
    """
    log.info("Starting scheduled activity tracking purge")

    with self.uowm.start() as uow:
        deleted = uow.author_activity.purge_old_records(days=180)
        uow.commit()

    log.info(f"Purged {deleted} old activity tracking records")
    return {'deleted': deleted}
```

---

## 8. Admin API Endpoints

### Spam Detection Admin Endpoints

**File**: `redditrepostsleuth/adminsvc/endpoints/spam_admin.py`

```python
"""
Admin API endpoints for spam detection.
"""
import logging
from datetime import datetime

import falcon

from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.core.celery.tasks.spam_detection_tasks import (
    score_and_flag_user,
    score_with_tier2,
    enrich_user_features_tier2,
)

log = logging.getLogger(__name__)


class SpamScoreUserEndpoint:
    """Endpoint to trigger spam scoring for a user."""

    def __init__(self, uowm: UnitOfWorkManager):
        self.uowm = uowm

    def on_post(self, req, resp):
        """
        POST /api/admin/spam/score

        Body: {"username": "some_user", "enrich_tier2": false}
        """
        data = req.media
        username = data.get('username')
        enrich_tier2 = data.get('enrich_tier2', False)

        if not username:
            resp.status = falcon.HTTP_400
            resp.media = {'error': 'username is required'}
            return

        # Queue analysis
        if enrich_tier2:
            task = score_with_tier2.delay(username)
        else:
            task = score_and_flag_user.delay(username, update_user_review=True)

        resp.media = {
            'status': 'queued',
            'task_id': task.id,
            'username': username,
        }


class SpamUserDetailsEndpoint:
    """Endpoint to get spam details for a user."""

    def __init__(self, uowm: UnitOfWorkManager):
        self.uowm = uowm

    def on_get(self, req, resp, username):
        """
        GET /api/admin/spam/user/{username}
        """
        with self.uowm.start() as uow:
            # Get latest features
            features = uow.spam_features.get_latest_by_username(username)

            # Get user review
            review = uow.user_review.get_by_username(username)

            # Get activity summary
            activity_count = uow.author_activity.get_author_count(username)

        if not features and not review:
            resp.status = falcon.HTTP_404
            resp.media = {'error': 'User not found in spam detection system'}
            return

        resp.media = {
            'username': username,
            'features': features.to_dict() if features else None,
            'review': {
                'spam_score': review.spam_score if review else None,
                'risk_level': review.risk_level if review else None,
                'is_verified_spam': review.is_verified_spam if review else False,
                'is_verified_legit': review.is_verified_legit if review else False,
            },
            'activity_count': activity_count,
        }


class SpamHighRiskUsersEndpoint:
    """Endpoint to list high-risk users."""

    def __init__(self, uowm: UnitOfWorkManager):
        self.uowm = uowm

    def on_get(self, req, resp):
        """
        GET /api/admin/spam/high-risk?min_score=0.6&limit=50
        """
        min_score = float(req.params.get('min_score', 0.6))
        limit = int(req.params.get('limit', 50))

        with self.uowm.start() as uow:
            high_risk = uow.spam_features.get_high_risk_users(
                min_score=min_score,
                limit=limit
            )

        resp.media = {
            'users': [
                {
                    'username': f.username,
                    'score': f.final_score,
                    'risk_level': f.risk_level,
                    'computed_at': f.computed_at.isoformat() if f.computed_at else None,
                    'top_factors': f.top_contributing_factors[:3] if f.top_contributing_factors else [],
                }
                for f in high_risk
            ],
            'total': len(high_risk),
        }


class SpamLabelUserEndpoint:
    """Endpoint to manually label a user."""

    def __init__(self, uowm: UnitOfWorkManager):
        self.uowm = uowm

    def on_post(self, req, resp):
        """
        POST /api/admin/spam/label

        Body: {
            "username": "some_user",
            "label": "SPAM" | "LEGITIMATE",
            "notes": "optional notes",
            "source_url": "optional evidence URL"
        }
        """
        data = req.media
        username = data.get('username')
        label = data.get('label')

        if not username or label not in ['SPAM', 'LEGITIMATE']:
            resp.status = falcon.HTTP_400
            resp.media = {'error': 'username and valid label (SPAM/LEGITIMATE) required'}
            return

        with self.uowm.start() as uow:
            # Update training labels
            from redditrepostsleuth.core.db.databasemodels import SpamTrainingLabels
            uow.spam_training_labels.add(SpamTrainingLabels(
                username=username,
                label=label,
                labeled_by='manual',
                labeled_at=datetime.utcnow(),
                confidence=1.0,
                source_url=data.get('source_url'),
                notes=data.get('notes'),
            ))

            # Update user review
            review = uow.user_review.get_by_username(username)
            if review:
                review.is_verified_spam = (label == 'SPAM')
                review.is_verified_legit = (label == 'LEGITIMATE')
            uow.commit()

        resp.media = {
            'status': 'labeled',
            'username': username,
            'label': label,
        }


class SpamStatsEndpoint:
    """Endpoint to get spam detection statistics."""

    def __init__(self, uowm: UnitOfWorkManager):
        self.uowm = uowm

    def on_get(self, req, resp):
        """
        GET /api/admin/spam/stats
        """
        with self.uowm.start() as uow:
            # Get label counts
            label_counts = uow.spam_training_labels.get_label_counts()

            # Get risk level distribution
            from sqlalchemy import func
            from redditrepostsleuth.core.db.databasemodels import UserSpamFeatures

            risk_dist = uow.session.query(
                UserSpamFeatures.risk_level,
                func.count(UserSpamFeatures.id)
            ).group_by(UserSpamFeatures.risk_level).all()

            # Get recent analysis count
            from datetime import timedelta
            recent_cutoff = datetime.utcnow() - timedelta(days=7)
            recent_count = uow.session.query(func.count(UserSpamFeatures.id)).filter(
                UserSpamFeatures.computed_at >= recent_cutoff
            ).scalar()

        resp.media = {
            'training_labels': label_counts,
            'risk_distribution': {level: count for level, count in risk_dist if level},
            'analyzed_last_7_days': recent_count,
        }


# Register endpoints in admin app
def register_spam_endpoints(app, uowm):
    """Register spam admin endpoints."""
    app.add_route('/api/admin/spam/score', SpamScoreUserEndpoint(uowm))
    app.add_route('/api/admin/spam/user/{username}', SpamUserDetailsEndpoint(uowm))
    app.add_route('/api/admin/spam/high-risk', SpamHighRiskUsersEndpoint(uowm))
    app.add_route('/api/admin/spam/label', SpamLabelUserEndpoint(uowm))
    app.add_route('/api/admin/spam/stats', SpamStatsEndpoint(uowm))
```

---

## 9. Testing Strategy

### Integration Tests

**File**: `tests/core/services/spam/test_trigger_integration.py`

```python
"""Tests for spam detection trigger integration."""
import unittest
from unittest.mock import MagicMock, patch, AsyncMock

from redditrepostsleuth.core.services.spam.spam_config_helper import (
    SpamDetectionConfig,
    get_spam_config,
)
from redditrepostsleuth.core.services.spam.spam_action_handler import (
    SpamActionHandler,
    SpamActionResult,
)


class TestSpamDetectionConfig(unittest.TestCase):

    def test_from_monitored_sub(self):
        """Test config creation from MonitoredSub."""
        mock_sub = MagicMock()
        mock_sub.spam_detection_enabled = True
        mock_sub.spam_detection_remove_post = True
        mock_sub.spam_detection_ban_user = False
        mock_sub.spam_detection_notify_mod_mail = True
        mock_sub.spam_detection_score_threshold = 0.8
        mock_sub.spam_detection_removal_reason = "Test reason"
        mock_sub.spam_detection_ban_reason = None

        config = SpamDetectionConfig.from_monitored_sub(mock_sub)

        self.assertTrue(config.enabled)
        self.assertTrue(config.remove_post)
        self.assertFalse(config.ban_user)
        self.assertTrue(config.notify_mod_mail)
        self.assertEqual(config.score_threshold, 0.8)

    def test_should_take_action(self):
        """Test action threshold logic."""
        config = SpamDetectionConfig(
            enabled=True,
            remove_post=True,
            ban_user=False,
            notify_mod_mail=True,
            score_threshold=0.7,
            removal_reason=None,
            ban_reason=None,
        )

        self.assertTrue(config.should_take_action(0.8))
        self.assertTrue(config.should_take_action(0.7))
        self.assertFalse(config.should_take_action(0.69))

    def test_disabled_config_no_action(self):
        """Test that disabled config returns no action."""
        config = SpamDetectionConfig(
            enabled=False,
            remove_post=True,
            ban_user=True,
            notify_mod_mail=True,
            score_threshold=0.5,
            removal_reason=None,
            ban_reason=None,
        )

        self.assertFalse(config.should_take_action(0.9))


class TestSpamActionHandler(unittest.TestCase):

    def setUp(self):
        self.mock_reddit = MagicMock()
        self.mock_uowm = MagicMock()
        self.handler = SpamActionHandler(self.mock_reddit, self.mock_uowm)

    def test_handle_no_config_logs_only(self):
        """Test that no config results in log-only mode."""
        result = self.handler.handle_spam_detection(
            username='testuser',
            score=0.9,
            risk_level='CRITICAL',
            reasons=['High repost ratio'],
            submission=None,
            monitored_sub=None,
            config=None,
        )

        self.assertEqual(len(result.actions_attempted), 0)

    def test_handle_below_threshold(self):
        """Test that score below threshold takes no action."""
        config = SpamDetectionConfig(
            enabled=True,
            remove_post=True,
            ban_user=True,
            notify_mod_mail=True,
            score_threshold=0.8,
            removal_reason=None,
            ban_reason=None,
        )

        result = self.handler.handle_spam_detection(
            username='testuser',
            score=0.5,  # Below 0.8 threshold
            risk_level='MEDIUM',
            reasons=['Some reason'],
            submission=MagicMock(),
            monitored_sub=MagicMock(),
            config=config,
        )

        self.assertEqual(len(result.actions_attempted), 0)
```

---

## 10. Verification Checklist

### Pre-Implementation
- [ ] Phase 3 completed and verified
- [ ] MonitoredSub model has spam detection columns
- [ ] Rate limiting working correctly

### Configuration
- [ ] SpamDetectionConfig correctly loads from MonitoredSub
- [ ] Default values are conservative (log-only)
- [ ] Threshold logic works correctly

### Integration
- [ ] Repost detection triggers spam analysis
- [ ] Summons trigger spam analysis
- [ ] Analysis respects whitelist
- [ ] Recently analyzed users are skipped

### Actions
- [ ] Post removal works when configured
- [ ] User banning works when configured
- [ ] Modmail notification works when configured
- [ ] Actions logged to database

### Scheduled Tasks
- [ ] Top reposter analysis runs on schedule
- [ ] Tier 2 enrichment runs on schedule
- [ ] Cleanup tasks run without errors

### Admin API
- [ ] All endpoints return correct data
- [ ] Manual scoring works
- [ ] Manual labeling works
- [ ] Stats endpoint accurate

---

## Dependencies

### Python Packages
No new packages required.

### Services
- Phase 3 Tier 2 enrichment
- Celery beat for scheduled tasks

---

## Estimated Effort

| Task | Estimate |
|------|----------|
| MonitoredSub config helper | 2 hours |
| Repost detection integration | 4 hours |
| Summons integration | 2 hours |
| Action handler | 4 hours |
| Scheduled tasks | 3 hours |
| Admin API endpoints | 4 hours |
| Integration tests | 4 hours |
| Documentation | 2 hours |
| **Total** | ~25 hours |
