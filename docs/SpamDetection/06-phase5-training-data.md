# Phase 5: Training Data Collection

## Overview
- **Duration**: Week 11-14
- **Dependencies**: Phase 4 (Trigger integration)
- **Goal**: Build labeled dataset for ML model training

---

## Table of Contents
1. [Training Data Requirements](#1-training-data-requirements)
2. [Data Collection Sources](#2-data-collection-sources)
3. [Error Handling Specifications](#3-error-handling-specifications)
4. [TrainingDataCollector Service](#4-trainingdatacollector-service)
5. [Automated Collection Tasks](#5-automated-collection-tasks)
6. [Manual Labeling Interface](#6-manual-labeling-interface)
7. [Data Quality Assurance](#7-data-quality-assurance)
8. [Dataset Export](#8-dataset-export)
9. [Testing Strategy](#9-testing-strategy)
10. [Verification Checklist](#10-verification-checklist)

---

## 1. Training Data Requirements

### Minimum Dataset Size

| Category | Minimum | Target | Notes |
|----------|---------|--------|-------|
| **SPAM** labeled | 500 | 1,000 | Confirmed spam accounts |
| **LEGITIMATE** labeled | 500 | 1,000 | Confirmed legitimate accounts |
| **Total** | 1,000 | 2,000 | Balanced dataset |

### Label Quality Requirements

| Label | Confidence Requirement | Source Priority |
|-------|----------------------|-----------------|
| SPAM | ≥0.8 | reddit_suspended > community_report > manual |
| LEGITIMATE | ≥0.7 | longevity_heuristic > manual > moderator |

### Feature Requirements

Each labeled account should have:
- [ ] Tier 1 features (from database)
- [ ] Tier 2 features (from API, if possible)
- [ ] At least 5 indexed posts

---

## 2. Data Collection Sources

### Source 1: Reddit Suspended Accounts (Highest Confidence)

**Confidence**: 0.95 (SPAM label)

Users suspended by Reddit are confirmed spam/rule violators.

```
Method:
1. Take top reposters from stat_top_reposter
2. Check if account is suspended (403/404)
3. If suspended → label as SPAM with high confidence
```

**Advantages**:
- Reddit has already determined these are spam
- High confidence labels
- Automated collection

**Limitations**:
- Some suspensions are for non-spam reasons
- Can only check users we know about

### Source 2: r/TheseFuckingAccounts Reports (High Confidence)

**Confidence**: 0.85 (SPAM label)

Community-sourced spam account reports.

```
Method:
1. Scrape posts from r/TheseFuckingAccounts
2. Extract reported usernames
3. Verify still active/suspended
4. Label as SPAM
```

**Advantages**:
- Community-vetted reports
- Detailed evidence often provided
- Active spam detection community

**Limitations**:
- Requires web scraping
- Some reports may be disputed
- Manual review recommended

### Source 3: Long-Term Active Users (Legitimate)

**Confidence**: 0.75 (LEGITIMATE label)

Users with years of activity and engagement are likely legitimate.

```
Criteria for auto-labeling as LEGITIMATE:
- Account age > 2 years
- Has summoned bot at least once (engaged with our service)
- Not on any watchlist
- Not suspended
- Has comment karma > 100 (engaged in discussions)
```

**Advantages**:
- Automated
- Reliable negative examples
- Large pool available

**Limitations**:
- Some old accounts can be sold/compromised
- Lower confidence than suspended accounts

### Source 4: Moderator/Gold Users (Legitimate)

**Confidence**: 0.80 (LEGITIMATE label)

```
Criteria:
- Is moderator of any subreddit
- OR has/had Reddit Gold
- AND not on any watchlist
```

### Source 5: Manual Labeling (Variable Confidence)

**Confidence**: 1.0 (human verified)

Admin interface for manual review and labeling.

---

## 3. Error Handling Specifications

Training data collection involves API calls and must handle errors gracefully:

### Error Scenarios

| Error | Cause | Handling |
|-------|-------|----------|
| API unavailable | Reddit API down | Retry with exponential backoff, max 3 attempts |
| User suspended | Account deleted/banned | Label as SPAM (data collection success) |
| Rate limit (429) | Too many requests | Respect retry-after header, exponential backoff |
| Network timeout | Connection failure | Retry up to 2 times |
| Missing data | User has no posts | Skip, mark as skipped |
| Database error | Connection pool exhausted | Retry with 5s backoff, fail after 3 attempts |

### Retry Strategy

```python
import time
from functools import wraps

def retry_with_backoff(max_attempts=3, initial_backoff=1):
    """Decorator for retryable operations."""
    def decorator(func):
        def wrapper(*args, **kwargs):
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except (TimeoutError, ConnectionError) as e:
                    if attempt >= max_attempts:
                        log.error(f"Failed after {max_attempts} attempts: {e}")
                        raise
                    backoff = initial_backoff * (2 ** (attempt - 1))
                    log.warning(f"Attempt {attempt} failed, retrying in {backoff}s: {e}")
                    time.sleep(backoff)
        return wrapper
    return decorator
```

### Logging Requirements

All operations must log:

```python
log.info(
    "Training data collection",
    extra={
        'operation': 'collect_suspended_accounts',
        'processed': 150,
        'new_labels': 32,
        'skipped': 118,
        'errors': 0,
        'duration_seconds': 45,
    }
)
```

### Dead Letter Queue

Failed individual items go to DLQ for manual review:

```python
def process_username(username: str):
    """Process with error handling."""
    try:
        # Fetch and label
        label = fetch_and_label(username)
        store_label(label)
    except Exception as e:
        log.error(f"Failed to process {username}: {e}")
        # Send to DLQ
        dlq.put({
            'username': username,
            'error': str(e),
            'timestamp': datetime.utcnow(),
        })
```

---

## 4. TrainingDataCollector Service

### File: `redditrepostsleuth/core/services/spam/training_data_collector.py`

```python
"""
Training Data Collector Service

Collects and manages labeled training data for spam detection ML model.
"""
import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Optional, Tuple

from praw import Reddit
from prawcore.exceptions import NotFound, Forbidden, TooManyRequests

from redditrepostsleuth.core.db.databasemodels import SpamTrainingLabels
from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.core.services.spam.user_data_fetcher import (
    UserDataFetcher,
    RateLimitExceeded,
)

log = logging.getLogger(__name__)


@dataclass
class CollectionResult:
    """Result of a data collection operation."""
    source: str
    total_processed: int
    new_labels_added: int
    skipped_existing: int
    skipped_no_data: int
    errors: int


class TrainingDataCollector:
    """
    Collects labeled training data from various sources.

    Sources:
    - Reddit suspended accounts (confirmed spam)
    - r/TheseFuckingAccounts reports (community-sourced)
    - Long-term active users (likely legitimate)
    - Moderators and gold users (likely legitimate)
    - Manual labeling via admin interface
    """

    def __init__(
        self,
        reddit: Reddit,
        uowm: UnitOfWorkManager,
        min_posts_for_label: int = 5,
    ):
        """
        Initialize the training data collector.

        Args:
            reddit: PRAW Reddit instance
            uowm: Unit of Work Manager
            min_posts_for_label: Minimum indexed posts required to label
        """
        self.reddit = reddit
        self.uowm = uowm
        self.min_posts_for_label = min_posts_for_label
        self.user_fetcher = UserDataFetcher(reddit, uowm)

    def check_user_suspended(self, username: str) -> Tuple[bool, Optional[str]]:
        """
        Check if a user account is suspended.

        Args:
            username: Reddit username

        Returns:
            Tuple of (is_suspended, error_message)
        """
        try:
            redditor = self.reddit.redditor(username)
            _ = redditor.created_utc  # Force fetch
            return False, None
        except NotFound:
            return True, "Account not found (deleted or shadowbanned)"
        except Forbidden:
            return True, "Account suspended by Reddit"
        except TooManyRequests as e:
            raise RateLimitExceeded(retry_after=getattr(e, 'retry_after', 60))
        except Exception as e:
            return False, f"Error checking: {str(e)}"

    def has_sufficient_data(self, username: str) -> bool:
        """Check if we have enough data to label this user."""
        with self.uowm.start() as uow:
            count = uow.author_activity.get_author_count(username)
            return count >= self.min_posts_for_label

    def is_already_labeled(self, username: str) -> bool:
        """Check if user is already labeled."""
        with self.uowm.start() as uow:
            existing = uow.spam_training_labels.get_by_username(username)
            return existing is not None

    def add_label(
        self,
        username: str,
        label: str,
        labeled_by: str,
        confidence: float,
        source_url: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> bool:
        """
        Add a training label for a user.

        Args:
            username: Reddit username
            label: SPAM, LEGITIMATE, or UNKNOWN
            labeled_by: Source identifier
            confidence: 0.0 to 1.0
            source_url: Optional URL to evidence
            notes: Optional notes

        Returns:
            True if label was added, False if skipped
        """
        with self.uowm.start() as uow:
            # Check if already labeled with higher confidence
            existing = uow.spam_training_labels.get_by_username(username)
            if existing and existing.confidence >= confidence:
                log.debug(f"Skipping {username}: already labeled with higher confidence")
                return False

            # Add/update label
            uow.spam_training_labels.add(SpamTrainingLabels(
                username=username,
                label=label,
                labeled_by=labeled_by,
                labeled_at=datetime.utcnow(),
                confidence=confidence,
                source_url=source_url,
                notes=notes,
            ))
            uow.commit()
            log.info(f"Labeled {username} as {label} (confidence: {confidence})")
            return True

    # =========================================================================
    # SOURCE 1: Suspended Account Detection
    # =========================================================================

    def collect_from_top_reposters(
        self,
        limit: int = 100,
        days: int = 30,
    ) -> CollectionResult:
        """
        Check top reposters for suspended accounts.

        Suspended accounts are labeled as SPAM with high confidence.

        Args:
            limit: Maximum users to check
            days: Look back period for top reposters

        Returns:
            CollectionResult with statistics
        """
        log.info(f"Collecting suspended accounts from top {limit} reposters")

        result = CollectionResult(
            source='reddit_suspended',
            total_processed=0,
            new_labels_added=0,
            skipped_existing=0,
            skipped_no_data=0,
            errors=0,
        )

        with self.uowm.start() as uow:
            top_reposters = uow.stat_top_reposter.get_top_reposters(
                days=days,
                limit=limit,
            )

        for reposter in top_reposters:
            result.total_processed += 1
            username = reposter.author

            # Skip if already labeled
            if self.is_already_labeled(username):
                result.skipped_existing += 1
                continue

            # Skip if insufficient data
            if not self.has_sufficient_data(username):
                result.skipped_no_data += 1
                continue

            try:
                is_suspended, reason = self.check_user_suspended(username)

                if is_suspended:
                    if self.add_label(
                        username=username,
                        label='SPAM',
                        labeled_by='reddit_suspended',
                        confidence=0.95,
                        notes=reason,
                    ):
                        result.new_labels_added += 1

                # Rate limit protection
                time.sleep(2.0)

            except RateLimitExceeded as e:
                log.warning(f"Rate limited, pausing {e.retry_after}s")
                time.sleep(e.retry_after)
                result.errors += 1

            except Exception as e:
                log.error(f"Error checking {username}: {e}")
                result.errors += 1

        log.info(f"Suspended account collection complete: {result}")
        return result

    # =========================================================================
    # SOURCE 2: r/TheseFuckingAccounts Scraping
    # =========================================================================

    def collect_from_thesefuckingaccounts(
        self,
        limit: int = 100,
        time_filter: str = 'month',
    ) -> CollectionResult:
        """
        Collect spam reports from r/TheseFuckingAccounts.

        Args:
            limit: Maximum posts to scrape
            time_filter: 'day', 'week', 'month', 'year', 'all'

        Returns:
            CollectionResult with statistics
        """
        log.info(f"Collecting from r/TheseFuckingAccounts (limit={limit})")

        result = CollectionResult(
            source='community_report_tfa',
            total_processed=0,
            new_labels_added=0,
            skipped_existing=0,
            skipped_no_data=0,
            errors=0,
        )

        try:
            subreddit = self.reddit.subreddit('TheseFuckingAccounts')
            posts = subreddit.top(time_filter=time_filter, limit=limit)

            for post in posts:
                # Extract usernames from title and body
                usernames = self._extract_usernames(post.title + ' ' + (post.selftext or ''))

                for username in usernames:
                    result.total_processed += 1

                    if self.is_already_labeled(username):
                        result.skipped_existing += 1
                        continue

                    if not self.has_sufficient_data(username):
                        result.skipped_no_data += 1
                        continue

                    # Verify account status
                    try:
                        is_suspended, _ = self.check_user_suspended(username)

                        # Higher confidence if also suspended
                        confidence = 0.95 if is_suspended else 0.85

                        if self.add_label(
                            username=username,
                            label='SPAM',
                            labeled_by='community_report_tfa',
                            confidence=confidence,
                            source_url=f"https://reddit.com{post.permalink}",
                            notes=f"Reported in r/TheseFuckingAccounts. Suspended: {is_suspended}",
                        ):
                            result.new_labels_added += 1

                        time.sleep(1.5)

                    except RateLimitExceeded as e:
                        log.warning(f"Rate limited, pausing {e.retry_after}s")
                        time.sleep(e.retry_after)

                    except Exception as e:
                        log.error(f"Error processing {username}: {e}")
                        result.errors += 1

        except Exception as e:
            log.error(f"Error scraping r/TheseFuckingAccounts: {e}")
            result.errors += 1

        log.info(f"TFA collection complete: {result}")
        return result

    def _extract_usernames(self, text: str) -> List[str]:
        """Extract Reddit usernames from text."""
        # Match u/username or /u/username patterns
        pattern = r'(?:^|[^\w])u/([A-Za-z0-9_-]{3,20})(?:[^\w]|$)'
        matches = re.findall(pattern, text, re.IGNORECASE)

        # Also check for direct username mentions
        direct_pattern = r'(?:user|account)[:\s]+([A-Za-z0-9_-]{3,20})'
        matches.extend(re.findall(direct_pattern, text, re.IGNORECASE))

        # Dedupe and filter
        usernames = list(set(matches))
        # Filter out common false positives
        filtered = [
            u for u in usernames
            if u.lower() not in ['deleted', 'removed', 'automoderator', 'repostsleuthbot']
        ]

        return filtered

    # =========================================================================
    # SOURCE 3: Long-Term Active Users (Legitimate)
    # =========================================================================

    def collect_longterm_legitimate_users(
        self,
        limit: int = 100,
        min_age_days: int = 730,  # 2 years
        min_comment_karma: int = 100,
    ) -> CollectionResult:
        """
        Collect long-term active users as legitimate examples.

        Criteria:
        - Has summoned bot (engaged with our service)
        - Account age > min_age_days
        - Not suspended
        - Comment karma > min_comment_karma

        Args:
            limit: Maximum users to label
            min_age_days: Minimum account age in days
            min_comment_karma: Minimum comment karma required

        Returns:
            CollectionResult with statistics
        """
        log.info(f"Collecting legitimate long-term users (limit={limit})")

        result = CollectionResult(
            source='longevity_heuristic',
            total_processed=0,
            new_labels_added=0,
            skipped_existing=0,
            skipped_no_data=0,
            errors=0,
        )

        # Get users who have summoned the bot
        with self.uowm.start() as uow:
            # Get distinct requestors from summons who have been around
            from sqlalchemy import distinct, func
            from redditrepostsleuth.core.db.databasemodels import Summons

            cutoff = datetime.utcnow() - timedelta(days=min_age_days)
            old_summons_users = uow.session.query(
                distinct(Summons.requestor)
            ).filter(
                Summons.summons_received_at < cutoff
            ).limit(limit * 3).all()

            candidates = [u[0] for u in old_summons_users if u[0]]

        for username in candidates[:limit]:
            result.total_processed += 1

            if self.is_already_labeled(username):
                result.skipped_existing += 1
                continue

            if not self.has_sufficient_data(username):
                result.skipped_no_data += 1
                continue

            try:
                # Verify not suspended and check karma
                tier2 = self.user_fetcher.fetch_basic_user_data(username)

                if tier2 is None:
                    result.errors += 1
                    continue

                if tier2.account_suspended:
                    # Suspended = spam, not legitimate
                    continue

                if tier2.account_age_days < min_age_days:
                    continue

                if tier2.comment_karma < min_comment_karma:
                    continue

                # Meets all criteria - label as legitimate
                if self.add_label(
                    username=username,
                    label='LEGITIMATE',
                    labeled_by='longevity_heuristic',
                    confidence=0.75,
                    notes=f"Account age: {tier2.account_age_days} days, karma: {tier2.total_karma}",
                ):
                    result.new_labels_added += 1

                time.sleep(1.5)

            except RateLimitExceeded as e:
                log.warning(f"Rate limited, pausing {e.retry_after}s")
                time.sleep(e.retry_after)

            except Exception as e:
                log.error(f"Error processing {username}: {e}")
                result.errors += 1

            if result.new_labels_added >= limit:
                break

        log.info(f"Legitimate user collection complete: {result}")
        return result

    # =========================================================================
    # SOURCE 4: Moderators (Legitimate)
    # =========================================================================

    def collect_moderator_users(
        self,
        subreddits: List[str],
        limit: int = 100,
    ) -> CollectionResult:
        """
        Collect subreddit moderators as legitimate examples.

        Args:
            subreddits: List of subreddits to get moderators from
            limit: Maximum moderators to label

        Returns:
            CollectionResult with statistics
        """
        log.info(f"Collecting moderators from {len(subreddits)} subreddits")

        result = CollectionResult(
            source='moderator',
            total_processed=0,
            new_labels_added=0,
            skipped_existing=0,
            skipped_no_data=0,
            errors=0,
        )

        moderators_found = set()

        for sub_name in subreddits:
            try:
                subreddit = self.reddit.subreddit(sub_name)
                for mod in subreddit.moderator():
                    if mod.name not in moderators_found:
                        moderators_found.add(mod.name)
                time.sleep(1.0)
            except Exception as e:
                log.error(f"Error getting mods for r/{sub_name}: {e}")

        for username in list(moderators_found)[:limit]:
            result.total_processed += 1

            # Skip bot accounts
            if 'bot' in username.lower():
                continue

            if self.is_already_labeled(username):
                result.skipped_existing += 1
                continue

            if not self.has_sufficient_data(username):
                result.skipped_no_data += 1
                continue

            try:
                # Verify not suspended
                is_suspended, _ = self.check_user_suspended(username)

                if is_suspended:
                    continue

                if self.add_label(
                    username=username,
                    label='LEGITIMATE',
                    labeled_by='moderator',
                    confidence=0.80,
                    notes=f"Moderator of subreddit(s)",
                ):
                    result.new_labels_added += 1

                time.sleep(1.5)

            except RateLimitExceeded as e:
                log.warning(f"Rate limited, pausing {e.retry_after}s")
                time.sleep(e.retry_after)

            except Exception as e:
                log.error(f"Error processing {username}: {e}")
                result.errors += 1

        log.info(f"Moderator collection complete: {result}")
        return result

    # =========================================================================
    # Dataset Statistics
    # =========================================================================

    def get_dataset_stats(self) -> dict:
        """Get current training dataset statistics."""
        with self.uowm.start() as uow:
            label_counts = uow.spam_training_labels.get_label_counts()

            # Get high-confidence counts
            high_conf = uow.spam_training_labels.get_high_confidence_labels(min_confidence=0.8)
            high_conf_counts = {'SPAM': 0, 'LEGITIMATE': 0}
            for label in high_conf:
                if label.label in high_conf_counts:
                    high_conf_counts[label.label] += 1

            # Get source distribution
            from sqlalchemy import func
            source_dist = uow.session.query(
                SpamTrainingLabels.labeled_by,
                func.count(SpamTrainingLabels.username)
            ).group_by(SpamTrainingLabels.labeled_by).all()

        return {
            'total_labels': sum(label_counts.values()),
            'label_distribution': label_counts,
            'high_confidence_counts': high_conf_counts,
            'source_distribution': {src: count for src, count in source_dist},
            'ready_for_training': (
                label_counts.get('SPAM', 0) >= 500 and
                label_counts.get('LEGITIMATE', 0) >= 500
            ),
        }
```

---

## 5. Automated Collection Tasks

### File: `redditrepostsleuth/core/celery/tasks/spam_detection_tasks.py`

Add these tasks:

```python
from redditrepostsleuth.core.services.spam.training_data_collector import (
    TrainingDataCollector
)


@shared_task(
    bind=True,
    base=RedditTask,
    queue='spam_detection',
)
def collect_suspended_accounts(self, limit: int = 100, days: int = 30) -> dict:
    """
    Collect suspended accounts from top reposters.

    Runs as scheduled task or on-demand.
    """
    collector = TrainingDataCollector(self.reddit, self.uowm)
    result = collector.collect_from_top_reposters(limit=limit, days=days)

    return {
        'source': result.source,
        'processed': result.total_processed,
        'new_labels': result.new_labels_added,
        'skipped': result.skipped_existing + result.skipped_no_data,
        'errors': result.errors,
    }


@shared_task(
    bind=True,
    base=RedditTask,
    queue='spam_detection',
)
def collect_from_tfa(self, limit: int = 100) -> dict:
    """
    Collect spam reports from r/TheseFuckingAccounts.
    """
    collector = TrainingDataCollector(self.reddit, self.uowm)
    result = collector.collect_from_thesefuckingaccounts(limit=limit)

    return {
        'source': result.source,
        'processed': result.total_processed,
        'new_labels': result.new_labels_added,
        'errors': result.errors,
    }


@shared_task(
    bind=True,
    base=RedditTask,
    queue='spam_detection',
)
def collect_legitimate_users(self, limit: int = 100) -> dict:
    """
    Collect long-term legitimate users.
    """
    collector = TrainingDataCollector(self.reddit, self.uowm)
    result = collector.collect_longterm_legitimate_users(limit=limit)

    return {
        'source': result.source,
        'processed': result.total_processed,
        'new_labels': result.new_labels_added,
        'errors': result.errors,
    }


@shared_task(
    bind=True,
    base=RedditTask,
    queue='spam_detection',
)
def collect_moderators(self, limit: int = 50) -> dict:
    """
    Collect moderators as legitimate users.
    """
    # Use subreddits we're active in
    subreddits = [
        'pics', 'funny', 'aww', 'memes', 'gaming',
        'askreddit', 'todayilearned', 'movies', 'music',
    ]

    collector = TrainingDataCollector(self.reddit, self.uowm)
    result = collector.collect_moderator_users(subreddits=subreddits, limit=limit)

    return {
        'source': result.source,
        'processed': result.total_processed,
        'new_labels': result.new_labels_added,
        'errors': result.errors,
    }


@shared_task(
    bind=True,
    base=SqlAlchemyTask,
    queue='spam_detection',
)
def get_training_data_stats(self) -> dict:
    """
    Get current training data statistics.
    """
    collector = TrainingDataCollector(None, self.uowm)  # Reddit not needed
    return collector.get_dataset_stats()


# Add to Celery beat schedule
CELERYBEAT_SCHEDULE.update({
    'collect-suspended-weekly': {
        'task': 'redditrepostsleuth.core.celery.tasks.spam_detection_tasks.collect_suspended_accounts',
        'schedule': crontab(day_of_week=1, hour=2, minute=0),  # Monday 2 AM
        'kwargs': {'limit': 200, 'days': 7},
        'options': {'queue': 'spam_detection'},
    },

    'collect-tfa-weekly': {
        'task': 'redditrepostsleuth.core.celery.tasks.spam_detection_tasks.collect_from_tfa',
        'schedule': crontab(day_of_week=2, hour=2, minute=0),  # Tuesday 2 AM
        'kwargs': {'limit': 100},
        'options': {'queue': 'spam_detection'},
    },

    'collect-legitimate-weekly': {
        'task': 'redditrepostsleuth.core.celery.tasks.spam_detection_tasks.collect_legitimate_users',
        'schedule': crontab(day_of_week=3, hour=2, minute=0),  # Wednesday 2 AM
        'kwargs': {'limit': 200},
        'options': {'queue': 'spam_detection'},
    },
})
```

---

## 6. Manual Labeling Interface

### Admin API Endpoint (Extended)

**File**: `redditrepostsleuth/adminsvc/endpoints/spam_admin.py`

Add to existing endpoints:

```python
class SpamReviewQueueEndpoint:
    """Endpoint to get users pending manual review."""

    def __init__(self, uowm: UnitOfWorkManager):
        self.uowm = uowm

    def on_get(self, req, resp):
        """
        GET /api/admin/spam/review-queue?limit=50

        Returns users that need manual review:
        - High spam score but not yet verified
        - Not already labeled in training data
        """
        limit = int(req.params.get('limit', 50))

        with self.uowm.start() as uow:
            # Get high-risk unverified users
            candidates = uow.user_review.get_users_needing_review(limit=limit * 2)

            # Filter out already labeled
            labeled_usernames = set(
                u.username for u in uow.spam_training_labels.get_all()
            )

            review_queue = [
                c for c in candidates
                if c.username not in labeled_usernames
            ][:limit]

        resp.media = {
            'queue': [
                {
                    'username': u.username,
                    'spam_score': u.spam_score,
                    'risk_level': u.risk_level,
                    'notes': u.notes,
                }
                for u in review_queue
            ],
            'total': len(review_queue),
        }


class SpamBulkLabelEndpoint:
    """Endpoint for bulk labeling users."""

    def __init__(self, uowm: UnitOfWorkManager):
        self.uowm = uowm

    def on_post(self, req, resp):
        """
        POST /api/admin/spam/bulk-label

        Body: {
            "labels": [
                {"username": "user1", "label": "SPAM"},
                {"username": "user2", "label": "LEGITIMATE"},
            ]
        }
        """
        data = req.media
        labels = data.get('labels', [])

        results = {'success': 0, 'failed': 0, 'errors': []}

        with self.uowm.start() as uow:
            for item in labels:
                username = item.get('username')
                label = item.get('label')

                if not username or label not in ['SPAM', 'LEGITIMATE']:
                    results['failed'] += 1
                    results['errors'].append(f"Invalid: {username}")
                    continue

                try:
                    uow.spam_training_labels.add(SpamTrainingLabels(
                        username=username,
                        label=label,
                        labeled_by='manual_bulk',
                        labeled_at=datetime.utcnow(),
                        confidence=1.0,
                    ))
                    results['success'] += 1
                except Exception as e:
                    results['failed'] += 1
                    results['errors'].append(f"{username}: {str(e)}")

            uow.commit()

        resp.media = results


class SpamTrainingDataExportEndpoint:
    """Endpoint to export training data."""

    def __init__(self, uowm: UnitOfWorkManager):
        self.uowm = uowm

    def on_get(self, req, resp):
        """
        GET /api/admin/spam/export-training-data?format=json

        Export labeled training data with features.
        """
        format_type = req.params.get('format', 'json')

        with self.uowm.start() as uow:
            # Get all labels
            labels = uow.spam_training_labels.get_all()

            # Get features for each labeled user
            export_data = []
            for label in labels:
                features = uow.spam_features.get_latest_by_username(label.username)

                if features:
                    export_data.append({
                        'username': label.username,
                        'label': label.label,
                        'label_confidence': label.confidence,
                        'label_source': label.labeled_by,
                        'features': features.to_dict() if features else None,
                    })

        if format_type == 'csv':
            # Return CSV format
            resp.content_type = 'text/csv'
            resp.text = self._to_csv(export_data)
        else:
            resp.media = {
                'data': export_data,
                'total': len(export_data),
                'exported_at': datetime.utcnow().isoformat(),
            }

    def _to_csv(self, data: list) -> str:
        """Convert to CSV format."""
        import csv
        import io

        output = io.StringIO()
        if not data:
            return ""

        # Flatten features into columns
        fieldnames = ['username', 'label', 'label_confidence', 'label_source']
        if data[0].get('features'):
            fieldnames.extend(data[0]['features'].keys())

        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()

        for row in data:
            flat_row = {
                'username': row['username'],
                'label': row['label'],
                'label_confidence': row['label_confidence'],
                'label_source': row['label_source'],
            }
            if row.get('features'):
                flat_row.update(row['features'])
            writer.writerow(flat_row)

        return output.getvalue()


# Register additional endpoints
def register_training_endpoints(app, uowm):
    """Register training data endpoints."""
    app.add_route('/api/admin/spam/review-queue', SpamReviewQueueEndpoint(uowm))
    app.add_route('/api/admin/spam/bulk-label', SpamBulkLabelEndpoint(uowm))
    app.add_route('/api/admin/spam/export-training-data', SpamTrainingDataExportEndpoint(uowm))
```

---

## 7. Data Quality Assurance

### Validation Rules

```python
class TrainingDataValidator:
    """Validates training data quality."""

    def __init__(self, uowm: UnitOfWorkManager):
        self.uowm = uowm

    def validate_dataset(self) -> dict:
        """
        Run validation checks on training dataset.

        Returns dict with validation results and issues found.
        """
        issues = []

        with self.uowm.start() as uow:
            labels = uow.spam_training_labels.get_all()

            # Check 1: Minimum dataset size
            label_counts = {}
            for label in labels:
                label_counts[label.label] = label_counts.get(label.label, 0) + 1

            if label_counts.get('SPAM', 0) < 500:
                issues.append({
                    'severity': 'error',
                    'check': 'min_spam_count',
                    'message': f"Need 500 SPAM labels, have {label_counts.get('SPAM', 0)}",
                })

            if label_counts.get('LEGITIMATE', 0) < 500:
                issues.append({
                    'severity': 'error',
                    'check': 'min_legitimate_count',
                    'message': f"Need 500 LEGITIMATE labels, have {label_counts.get('LEGITIMATE', 0)}",
                })

            # Check 2: Class balance
            spam_count = label_counts.get('SPAM', 0)
            legit_count = label_counts.get('LEGITIMATE', 0)
            if spam_count > 0 and legit_count > 0:
                ratio = spam_count / legit_count
                if ratio < 0.5 or ratio > 2.0:
                    issues.append({
                        'severity': 'warning',
                        'check': 'class_balance',
                        'message': f"Class imbalance: {spam_count} SPAM vs {legit_count} LEGITIMATE",
                    })

            # Check 3: Feature coverage
            labels_without_features = 0
            for label in labels:
                features = uow.spam_features.get_latest_by_username(label.username)
                if not features:
                    labels_without_features += 1

            if labels_without_features > 0:
                issues.append({
                    'severity': 'warning',
                    'check': 'feature_coverage',
                    'message': f"{labels_without_features} labeled users missing features",
                })

            # Check 4: Low confidence labels
            low_confidence = [l for l in labels if l.confidence < 0.7]
            if len(low_confidence) > len(labels) * 0.2:
                issues.append({
                    'severity': 'warning',
                    'check': 'label_confidence',
                    'message': f"{len(low_confidence)} labels have confidence < 0.7",
                })

        return {
            'valid': len([i for i in issues if i['severity'] == 'error']) == 0,
            'issues': issues,
            'label_counts': label_counts,
            'total_labels': len(labels),
        }
```

---

## 8. Dataset Export

### Export Formats

**JSON Export** (Default):
```json
{
    "metadata": {
        "exported_at": "2026-01-23T12:00:00",
        "total_records": 1500,
        "label_distribution": {"SPAM": 750, "LEGITIMATE": 750}
    },
    "data": [
        {
            "username": "example_user",
            "label": "SPAM",
            "confidence": 0.95,
            "features": {
                "repost_ratio": 0.85,
                "posts_per_day_avg": 15.2,
                ...
            }
        }
    ]
}
```

**CSV Export**:
```csv
username,label,confidence,repost_ratio,posts_per_day_avg,...
example_user,SPAM,0.95,0.85,15.2,...
```

---

## 9. Testing Strategy

### Unit Tests

```python
"""Tests for TrainingDataCollector."""
import unittest
from unittest.mock import MagicMock, patch

from redditrepostsleuth.core.services.spam.training_data_collector import (
    TrainingDataCollector,
    CollectionResult,
)


class TestTrainingDataCollector(unittest.TestCase):

    def setUp(self):
        self.mock_reddit = MagicMock()
        self.mock_uowm = MagicMock()
        self.collector = TrainingDataCollector(
            self.mock_reddit,
            self.mock_uowm,
            min_posts_for_label=5,
        )

    def test_extract_usernames(self):
        """Test username extraction from text."""
        text = "Check out u/spammer123 and /u/another_spam. Also user: badactor"
        usernames = self.collector._extract_usernames(text)

        self.assertIn('spammer123', usernames)
        self.assertIn('another_spam', usernames)
        self.assertIn('badactor', usernames)

    def test_extract_usernames_filters_bots(self):
        """Test that bot accounts are filtered."""
        text = "u/AutoModerator removed u/spammer post"
        usernames = self.collector._extract_usernames(text)

        self.assertNotIn('AutoModerator', usernames)
        self.assertNotIn('automoderator', usernames)

    def test_check_user_suspended_returns_true(self):
        """Test suspended user detection."""
        from prawcore.exceptions import Forbidden
        self.mock_reddit.redditor.return_value.created_utc = property(
            lambda self: (_ for _ in ()).throw(Forbidden(MagicMock()))
        )
        self.mock_reddit.redditor.side_effect = Forbidden(MagicMock())

        # Need to adjust based on actual implementation
        # is_suspended, _ = self.collector.check_user_suspended('suspendeduser')
        # self.assertTrue(is_suspended)
```

---

## 10. Verification Checklist

### Pre-Implementation
- [ ] Phase 4 completed and verified
- [ ] API rate limits understood
- [ ] admin API endpoints working

### Data Collection
- [ ] Suspended account collection working
- [ ] r/TheseFuckingAccounts scraping working
- [ ] Legitimate user collection working
- [ ] Moderator collection working

### Data Quality
- [ ] Minimum 500 SPAM labels collected
- [ ] Minimum 500 LEGITIMATE labels collected
- [ ] Class balance within 0.5-2.0 ratio
- [ ] >90% of labels have features

### Manual Labeling
- [ ] Review queue endpoint working
- [ ] Single label endpoint working
- [ ] Bulk label endpoint working

### Export
- [ ] JSON export working
- [ ] CSV export working
- [ ] Features included in export

---

## Dependencies

### Python Packages
- `csv` (standard library)

### External
- r/TheseFuckingAccounts access (public subreddit)

---

## Estimated Effort

| Task | Estimate |
|------|----------|
| TrainingDataCollector service | 6 hours |
| Automated collection tasks | 3 hours |
| Manual labeling endpoints | 3 hours |
| Data validation | 2 hours |
| Export functionality | 2 hours |
| Testing | 4 hours |
| Documentation | 2 hours |
| **Total** | ~22 hours |
