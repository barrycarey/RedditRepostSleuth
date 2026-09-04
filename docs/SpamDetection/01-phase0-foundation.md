# Phase 0: Foundation & Database Schema

## Overview
- **Duration**: Week 1-2
- **Dependencies**: None
- **Goal**: Establish database schema and core infrastructure for spam detection

---

## Table of Contents
1. [Feature Flags](#1-feature-flags)
2. [Database Models](#2-database-models)
3. [Table Partitioning Strategy](#3-table-partitioning-strategy)
4. [Alembic Migration](#4-alembic-migration)
5. [Repository Classes](#5-repository-classes)
6. [Unit of Work Integration](#6-unit-of-work-integration)
7. [Ingest Pipeline Integration](#7-ingest-pipeline-integration)
8. [Database Connection Pool](#8-database-connection-pool)
9. [Celery Queue Configuration](#9-celery-queue-configuration)
10. [Phase 0.5 Infrastructure Validation](#10-phase-05-infrastructure-validation)
11. [Testing Strategy](#11-testing-strategy)
12. [Verification Checklist](#12-verification-checklist)

---

## 1. Feature Flags

Add these feature flags to your application configuration to control spam detection behavior safely:

### Primary Feature Flags

| Flag | Purpose | Default | Notes |
|------|---------|---------|-------|
| `SPAM_DETECTION_ENABLED` | Master toggle for entire system | False | Disable all spam detection if needed |
| `SPAM_AUTHOR_TRACKING_ENABLED` | Enable/disable author tracking in ingest | False | Must be True before Phase 1 starts |
| `SPAM_DETECTION_SHADOW_MODE` | Run detection without taking actions | True | During Phase 4.5, disable when moving to production |
| `SPAM_DETECTION_AUTO_ACTIONS_ENABLED` | Actually remove posts/ban users | False | Only enable after extensive validation |

### Configuration Implementation

**File**: `redditrepostsleuth/core/config.py`

```python
# Add to config class
SPAM_DETECTION_ENABLED = env_bool('SPAM_DETECTION_ENABLED', default=False)
SPAM_AUTHOR_TRACKING_ENABLED = env_bool('SPAM_AUTHOR_TRACKING_ENABLED', default=False)
SPAM_DETECTION_SHADOW_MODE = env_bool('SPAM_DETECTION_SHADOW_MODE', default=True)
SPAM_DETECTION_AUTO_ACTIONS_ENABLED = env_bool('SPAM_DETECTION_AUTO_ACTIONS_ENABLED', default=False)
```

**Usage in code**:

```python
from redditrepostsleuth.core.config import Config

config = Config()

if config.SPAM_AUTHOR_TRACKING_ENABLED:
    # Track author activity in ingest pipeline
    track_author_activity(post)

if config.SPAM_DETECTION_ENABLED:
    # Run spam detection
    detect_spam(post.author)

if not config.SPAM_DETECTION_SHADOW_MODE:
    # Actually take actions
    remove_post_or_ban_user(...)
```

---

## 2. Database Models

### File: `redditrepostsleuth/core/db/databasemodels.py`

Add the following models to the existing file.

### 1.1 AuthorActivityTracking Model

This table exists as a **workaround** for the missing `author` index on the `post` table (2B rows, can't add index without weeks of downtime). It provides fast author lookups for spam detection.

```python
class AuthorActivityTracking(Base):
    """
    Lightweight author activity tracking for spam detection.

    This table exists because the main `post` table (2B rows) has no index on `author`.
    All spam detection queries should use this table instead of querying `post` directly.

    Populated by the ingest pipeline alongside normal post ingestion.
    """
    __tablename__ = 'author_activity_tracking'
    __table_args__ = (
        Index('idx_aat_author', 'author'),
        Index('idx_aat_author_created', 'author', 'created_at'),
        Index('idx_aat_subreddit', 'subreddit'),
        Index('idx_aat_created_at', 'created_at'),
        Index('idx_aat_adult_platform', 'has_adult_platform_link'),
        Index('idx_aat_post_id', 'post_id', unique=True),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    post_id = Column(String(9), nullable=False, unique=True)
    author = Column(String(25), nullable=False)
    subreddit = Column(String(25), nullable=False)
    created_at = Column(DateTime, nullable=False)
    nsfw = Column(Boolean, default=False)
    post_type_id = Column(TINYINT())
    ingested_at = Column(DateTime, default=func.utc_timestamp())

    # Adult platform/promo detection (computed at ingest time)
    has_adult_platform_link = Column(Boolean, default=False)
    has_short_link = Column(Boolean, default=False)
    detected_platform = Column(String(50), default=None)
```

**Key Design Decisions**:
- `BigInteger` primary key for high volume
- All indexes defined upfront (unlike post table)
- `post_id` is unique to prevent duplicates
- Link detection computed at ingest time (not query time)

---

### 1.2 UserSpamFeatures Model

Stores computed feature snapshots for ML training and scoring.

```python
class UserSpamFeatures(Base):
    """
    Computed spam detection features for a user at a point in time.

    Features are grouped by tier:
    - Tier 1: From existing data (no API calls)
    - Tier 2: From single Reddit API call
    - Tier 3: From multiple API calls (expensive)
    """
    __tablename__ = 'user_spam_features'
    __table_args__ = (
        Index('idx_usf_username', 'username'),
        Index('idx_usf_computed', 'computed_at'),
        Index('idx_usf_score', 'final_score'),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(25), nullable=False)
    computed_at = Column(DateTime, nullable=False)

    # =========================================================================
    # TIER 1: From existing data (no API calls required)
    # =========================================================================
    total_posts_indexed = Column(Integer)
    total_reposts_detected = Column(Integer)
    repost_ratio = Column(Float)
    unique_subreddits_posted = Column(Integer)
    posts_per_day_avg = Column(Float)
    first_post_date = Column(DateTime)
    last_post_date = Column(DateTime)
    nsfw_post_ratio = Column(Float)
    summons_received = Column(Integer)

    # Adult platform/promo detection (from author_activity_tracking)
    adult_platform_post_count = Column(Integer, default=0)
    adult_platform_ratio = Column(Float, default=0)
    short_link_post_count = Column(Integer, default=0)
    short_link_ratio = Column(Float, default=0)
    detected_platforms = Column(JSON)  # List of platforms detected

    # Username pattern analysis
    username_suspicious_pattern = Column(Boolean, default=False)
    username_pattern_matches = Column(JSON)  # Dict of pattern matches

    # =========================================================================
    # TIER 2: From single Reddit API call (redditor object)
    # =========================================================================
    account_age_days = Column(Integer)
    total_karma = Column(Integer)
    post_karma = Column(Integer)
    comment_karma = Column(Integer)
    karma_per_day = Column(Float)
    has_verified_email = Column(Boolean)
    is_gold = Column(Boolean)
    has_custom_avatar = Column(Boolean)
    account_suspended = Column(Boolean, default=False)

    # =========================================================================
    # TIER 3: From multiple API calls (expensive, selective)
    # =========================================================================
    karma_farming_sub_posts = Column(Integer, default=None)
    easy_karma_sub_posts = Column(Integer, default=None)
    posting_hour_entropy = Column(Float, default=None)
    comment_length_avg = Column(Float, default=None)
    comment_length_stddev = Column(Float, default=None)
    generic_comment_ratio = Column(Float, default=None)

    # =========================================================================
    # SCORING RESULTS
    # =========================================================================
    rule_score = Column(Float)
    ml_score = Column(Float, default=None)
    final_score = Column(Float)
    risk_level = Column(String(20))  # LOW, MEDIUM, HIGH, CRITICAL
    top_contributing_factors = Column(JSON)  # List of reason strings

    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'computed_at': self.computed_at.isoformat() if self.computed_at else None,
            'total_posts_indexed': self.total_posts_indexed,
            'total_reposts_detected': self.total_reposts_detected,
            'repost_ratio': self.repost_ratio,
            'unique_subreddits_posted': self.unique_subreddits_posted,
            'posts_per_day_avg': self.posts_per_day_avg,
            'nsfw_post_ratio': self.nsfw_post_ratio,
            'adult_platform_ratio': self.adult_platform_ratio,
            'account_age_days': self.account_age_days,
            'total_karma': self.total_karma,
            'final_score': self.final_score,
            'risk_level': self.risk_level,
            'top_contributing_factors': self.top_contributing_factors,
        }
```

---

### 1.3 SpamSubredditList Model

Reference table for known spam/karma farm subreddits.

```python
class SpamSubredditList(Base):
    """
    Reference list of subreddits associated with spam behavior.

    Categories:
    - KARMA_FARM: Explicit karma farming subs (r/FreeKarma4U)
    - EASY_TARGET: High-traffic subs commonly targeted by spammers
    - NSFW_PROMO: NSFW subs used for adult content promotion
    """
    __tablename__ = 'spam_subreddit_list'

    subreddit = Column(String(50), primary_key=True)
    risk_category = Column(String(20), nullable=False)  # KARMA_FARM, EASY_TARGET, NSFW_PROMO
    weight = Column(Float, default=1.0)  # How much this affects score (0.0-1.0)
    added_at = Column(DateTime, default=func.utc_timestamp())
    notes = Column(String(500))

    def to_dict(self):
        return {
            'subreddit': self.subreddit,
            'risk_category': self.risk_category,
            'weight': self.weight,
            'notes': self.notes,
        }
```

---

### 1.4 SpamTrainingLabels Model

Labeled data for ML model training.

```python
class SpamTrainingLabels(Base):
    """
    Labeled training data for spam detection ML model.

    Labels:
    - SPAM: Confirmed spam account
    - LEGITIMATE: Confirmed legitimate account
    - UNKNOWN: Not yet labeled

    Sources:
    - manual: Human labeled
    - reddit_suspended: Account was suspended by Reddit
    - community_report: Reported via r/TheseFuckingAccounts or similar
    - longevity_heuristic: Long-term active user (auto-labeled)
    """
    __tablename__ = 'spam_training_labels'
    __table_args__ = (
        Index('idx_stl_label', 'label'),
        Index('idx_stl_labeled_by', 'labeled_by'),
    )

    username = Column(String(25), primary_key=True)
    label = Column(String(20), nullable=False)  # SPAM, LEGITIMATE, UNKNOWN
    labeled_by = Column(String(50))  # manual, reddit_suspended, community_report, longevity_heuristic
    labeled_at = Column(DateTime, default=func.utc_timestamp())
    confidence = Column(Float)  # 0.0-1.0, how confident we are in this label
    source_url = Column(String(500))  # Link to evidence
    notes = Column(String(500))

    def to_dict(self):
        return {
            'username': self.username,
            'label': self.label,
            'labeled_by': self.labeled_by,
            'labeled_at': self.labeled_at.isoformat() if self.labeled_at else None,
            'confidence': self.confidence,
            'source_url': self.source_url,
            'notes': self.notes,
        }
```

---

### 1.5 Extend UserReview Model

Add spam detection columns to existing model.

**Current UserReview** (lines 756-765 in databasemodels.py):
```python
class UserReview(Base):
    __tablename__ = 'user_review'
    __table_args__ = (
        Index('idx_last_checked', 'last_checked'),
    )
    username = Column(String(25), nullable=False, primary_key=True, unique=True)
    content_links_found = Column(Boolean, default=False)
    added_at = Column(DateTime, default=func.utc_timestamp(), nullable=False)
    notes = Column(String(150))
    last_checked = Column(DateTime, default=func.utc_timestamp())
```

**Add these columns**:
```python
    # Spam detection fields
    spam_score = Column(Float, default=None)
    spam_score_confidence = Column(Float, default=None)
    spam_score_updated_at = Column(DateTime, default=None)
    risk_level = Column(String(20), default=None)  # LOW, MEDIUM, HIGH, CRITICAL
    is_verified_spam = Column(Boolean, default=False)
    is_verified_legit = Column(Boolean, default=False)
```

---

### 1.6 Extend MonitoredSub Model

Add spam detection configuration following the adult promoter pattern.

**Add these columns after the existing adult_promoter_* columns** (around line 365):
```python
    # Spam detection configuration (follows adult_promoter pattern)
    spam_detection_enabled = Column(Boolean, default=False)
    spam_detection_remove_post = Column(Boolean, default=False)
    spam_detection_ban_user = Column(Boolean, default=False)
    spam_detection_notify_mod_mail = Column(Boolean, default=False)
    spam_detection_score_threshold = Column(Float, default=0.7)
    spam_detection_removal_reason = Column(String(300))
    spam_detection_ban_reason = Column(String(300))
```

**Update the `to_dict()` method** to include:
```python
    'spam_detection_enabled': self.spam_detection_enabled,
    'spam_detection_remove_post': self.spam_detection_remove_post,
    'spam_detection_ban_user': self.spam_detection_ban_user,
    'spam_detection_notify_mod_mail': self.spam_detection_notify_mod_mail,
    'spam_detection_score_threshold': self.spam_detection_score_threshold,
    'spam_detection_removal_reason': self.spam_detection_removal_reason,
    'spam_detection_ban_reason': self.spam_detection_ban_reason,
```

---

## 3. Table Partitioning Strategy

### author_activity_tracking Partitioning

The `author_activity_tracking` table is expected to grow to ~50M rows/year. To manage this growth and maintain query performance, implement monthly partitions:

**Strategy**: Range partitioning by `created_at` (monthly)

**Benefits**:
- Older partitions can be archived after 6-12 months
- Queries on recent data are faster (fewer rows to scan)
- Maintenance operations (VACUUM, INDEX) can run per-partition
- Easy archival without deleting data

**Implementation**:

```sql
-- Create base table as partitioned
CREATE TABLE author_activity_tracking (
    id BIGINT AUTO_INCREMENT,
    post_id VARCHAR(9) UNIQUE NOT NULL,
    author VARCHAR(25) NOT NULL,
    subreddit VARCHAR(25) NOT NULL,
    created_at DATETIME NOT NULL,
    nsfw BOOLEAN DEFAULT FALSE,
    post_type_id TINYINT,
    ingested_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    has_adult_platform_link BOOLEAN DEFAULT FALSE,
    has_short_link BOOLEAN DEFAULT FALSE,
    detected_platform VARCHAR(50),
    PRIMARY KEY (id, created_at),
    KEY idx_aat_author (author, created_at),
    KEY idx_aat_subreddit (subreddit, created_at),
    KEY idx_aat_post_id (post_id)
) ENGINE=InnoDB
PARTITION BY RANGE (YEAR_MONTH(created_at)) (
    PARTITION p202601 VALUES LESS THAN (202602),
    PARTITION p202602 VALUES LESS THAN (202603),
    -- ... add partitions for future months
    PARTITION pmax VALUES LESS THAN MAXVALUE
);
```

**Maintenance**:

Run monthly to add new partitions:

```sql
-- Add next month's partition
ALTER TABLE author_activity_tracking
ADD PARTITION (PARTITION p202604 VALUES LESS THAN (202605));

-- Drop old partitions (after 6+ months)
ALTER TABLE author_activity_tracking
DROP PARTITION p202507;  -- For example, drop 7+ month old partition
```

**Archival Process**:

```python
# Before dropping partition, export data
SELECT * INTO OUTFILE '/backup/author_activity_2025_07.csv'
FROM author_activity_tracking
WHERE YEAR_MONTH(created_at) = 202507;

# Then drop partition (safe if data is backed up)
ALTER TABLE author_activity_tracking DROP PARTITION p202507;
```

---

## 4. Alembic Migration

### File: `alembic/versions/YYYYMMDD_spam_detection_schema.py`

```python
"""Add spam detection tables and columns

Revision ID: spam_detection_001
Revises: <previous_revision>
Create Date: 2026-01-XX

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.mysql import BIGINT, TINYINT, JSON

# revision identifiers, used by Alembic.
revision = 'spam_detection_001'
down_revision = '<previous_revision>'  # Fill in actual previous revision
branch_labels = None
depends_on = None


def upgrade():
    # =========================================================================
    # NEW TABLE: author_activity_tracking
    # =========================================================================
    op.create_table(
        'author_activity_tracking',
        sa.Column('id', BIGINT, primary_key=True, autoincrement=True),
        sa.Column('post_id', sa.String(9), nullable=False, unique=True),
        sa.Column('author', sa.String(25), nullable=False),
        sa.Column('subreddit', sa.String(25), nullable=False),
        sa.Column('created_at', sa.DateTime, nullable=False),
        sa.Column('nsfw', sa.Boolean, default=False),
        sa.Column('post_type_id', TINYINT),
        sa.Column('ingested_at', sa.DateTime, server_default=sa.func.utc_timestamp()),
        sa.Column('has_adult_platform_link', sa.Boolean, default=False),
        sa.Column('has_short_link', sa.Boolean, default=False),
        sa.Column('detected_platform', sa.String(50), default=None),
    )

    op.create_index('idx_aat_author', 'author_activity_tracking', ['author'])
    op.create_index('idx_aat_author_created', 'author_activity_tracking', ['author', 'created_at'])
    op.create_index('idx_aat_subreddit', 'author_activity_tracking', ['subreddit'])
    op.create_index('idx_aat_created_at', 'author_activity_tracking', ['created_at'])
    op.create_index('idx_aat_adult_platform', 'author_activity_tracking', ['has_adult_platform_link'])

    # =========================================================================
    # NEW TABLE: user_spam_features
    # =========================================================================
    op.create_table(
        'user_spam_features',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('username', sa.String(25), nullable=False),
        sa.Column('computed_at', sa.DateTime, nullable=False),

        # Tier 1 features
        sa.Column('total_posts_indexed', sa.Integer),
        sa.Column('total_reposts_detected', sa.Integer),
        sa.Column('repost_ratio', sa.Float),
        sa.Column('unique_subreddits_posted', sa.Integer),
        sa.Column('posts_per_day_avg', sa.Float),
        sa.Column('first_post_date', sa.DateTime),
        sa.Column('last_post_date', sa.DateTime),
        sa.Column('nsfw_post_ratio', sa.Float),
        sa.Column('summons_received', sa.Integer),
        sa.Column('adult_platform_post_count', sa.Integer, default=0),
        sa.Column('adult_platform_ratio', sa.Float, default=0),
        sa.Column('short_link_post_count', sa.Integer, default=0),
        sa.Column('short_link_ratio', sa.Float, default=0),
        sa.Column('detected_platforms', JSON),
        sa.Column('username_suspicious_pattern', sa.Boolean, default=False),
        sa.Column('username_pattern_matches', JSON),

        # Tier 2 features
        sa.Column('account_age_days', sa.Integer),
        sa.Column('total_karma', sa.Integer),
        sa.Column('post_karma', sa.Integer),
        sa.Column('comment_karma', sa.Integer),
        sa.Column('karma_per_day', sa.Float),
        sa.Column('has_verified_email', sa.Boolean),
        sa.Column('is_gold', sa.Boolean),
        sa.Column('has_custom_avatar', sa.Boolean),
        sa.Column('account_suspended', sa.Boolean, default=False),

        # Tier 3 features
        sa.Column('karma_farming_sub_posts', sa.Integer),
        sa.Column('easy_karma_sub_posts', sa.Integer),
        sa.Column('posting_hour_entropy', sa.Float),
        sa.Column('comment_length_avg', sa.Float),
        sa.Column('comment_length_stddev', sa.Float),
        sa.Column('generic_comment_ratio', sa.Float),

        # Scoring
        sa.Column('rule_score', sa.Float),
        sa.Column('ml_score', sa.Float),
        sa.Column('final_score', sa.Float),
        sa.Column('risk_level', sa.String(20)),
        sa.Column('top_contributing_factors', JSON),
    )

    op.create_index('idx_usf_username', 'user_spam_features', ['username'])
    op.create_index('idx_usf_computed', 'user_spam_features', ['computed_at'])
    op.create_index('idx_usf_score', 'user_spam_features', ['final_score'])

    # =========================================================================
    # NEW TABLE: spam_subreddit_list
    # =========================================================================
    op.create_table(
        'spam_subreddit_list',
        sa.Column('subreddit', sa.String(50), primary_key=True),
        sa.Column('risk_category', sa.String(20), nullable=False),
        sa.Column('weight', sa.Float, default=1.0),
        sa.Column('added_at', sa.DateTime, server_default=sa.func.utc_timestamp()),
        sa.Column('notes', sa.String(500)),
    )

    # =========================================================================
    # NEW TABLE: spam_training_labels
    # =========================================================================
    op.create_table(
        'spam_training_labels',
        sa.Column('username', sa.String(25), primary_key=True),
        sa.Column('label', sa.String(20), nullable=False),
        sa.Column('labeled_by', sa.String(50)),
        sa.Column('labeled_at', sa.DateTime, server_default=sa.func.utc_timestamp()),
        sa.Column('confidence', sa.Float),
        sa.Column('source_url', sa.String(500)),
        sa.Column('notes', sa.String(500)),
    )

    op.create_index('idx_stl_label', 'spam_training_labels', ['label'])
    op.create_index('idx_stl_labeled_by', 'spam_training_labels', ['labeled_by'])

    # =========================================================================
    # EXTEND TABLE: user_review
    # =========================================================================
    op.add_column('user_review', sa.Column('spam_score', sa.Float, default=None))
    op.add_column('user_review', sa.Column('spam_score_confidence', sa.Float, default=None))
    op.add_column('user_review', sa.Column('spam_score_updated_at', sa.DateTime, default=None))
    op.add_column('user_review', sa.Column('risk_level', sa.String(20), default=None))
    op.add_column('user_review', sa.Column('is_verified_spam', sa.Boolean, default=False))
    op.add_column('user_review', sa.Column('is_verified_legit', sa.Boolean, default=False))

    # =========================================================================
    # EXTEND TABLE: monitored_sub
    # =========================================================================
    op.add_column('monitored_sub', sa.Column('spam_detection_enabled', sa.Boolean, default=False))
    op.add_column('monitored_sub', sa.Column('spam_detection_remove_post', sa.Boolean, default=False))
    op.add_column('monitored_sub', sa.Column('spam_detection_ban_user', sa.Boolean, default=False))
    op.add_column('monitored_sub', sa.Column('spam_detection_notify_mod_mail', sa.Boolean, default=False))
    op.add_column('monitored_sub', sa.Column('spam_detection_score_threshold', sa.Float, default=0.7))
    op.add_column('monitored_sub', sa.Column('spam_detection_removal_reason', sa.String(300)))
    op.add_column('monitored_sub', sa.Column('spam_detection_ban_reason', sa.String(300)))

    # =========================================================================
    # SEED DATA: spam_subreddit_list
    # =========================================================================
    op.execute("""
        INSERT INTO spam_subreddit_list (subreddit, risk_category, weight, notes) VALUES
        ('freekarma4u', 'KARMA_FARM', 1.0, 'Explicit karma farming subreddit'),
        ('freekarma4you', 'KARMA_FARM', 1.0, 'Explicit karma farming subreddit'),
        ('freekarmaforall', 'KARMA_FARM', 1.0, 'Explicit karma farming subreddit'),
        ('karmafarming4pros', 'KARMA_FARM', 1.0, 'Explicit karma farming subreddit'),
        ('karma4free', 'KARMA_FARM', 1.0, 'Explicit karma farming subreddit'),
        ('karmawhore', 'KARMA_FARM', 0.9, 'Karma farming subreddit'),
        ('aww', 'EASY_TARGET', 0.3, 'High-traffic sub commonly targeted'),
        ('pics', 'EASY_TARGET', 0.3, 'High-traffic sub commonly targeted'),
        ('funny', 'EASY_TARGET', 0.3, 'High-traffic sub commonly targeted'),
        ('memes', 'EASY_TARGET', 0.3, 'High-traffic sub commonly targeted'),
        ('todayilearned', 'EASY_TARGET', 0.2, 'High-traffic sub commonly targeted'),
        ('askreddit', 'EASY_TARGET', 0.2, 'High-traffic sub commonly targeted'),
        ('gaming', 'EASY_TARGET', 0.2, 'High-traffic sub commonly targeted'),
        ('oldschoolcool', 'EASY_TARGET', 0.3, 'Common repost target')
    """)


def downgrade():
    # Drop new columns from monitored_sub
    op.drop_column('monitored_sub', 'spam_detection_ban_reason')
    op.drop_column('monitored_sub', 'spam_detection_removal_reason')
    op.drop_column('monitored_sub', 'spam_detection_score_threshold')
    op.drop_column('monitored_sub', 'spam_detection_notify_mod_mail')
    op.drop_column('monitored_sub', 'spam_detection_ban_user')
    op.drop_column('monitored_sub', 'spam_detection_remove_post')
    op.drop_column('monitored_sub', 'spam_detection_enabled')

    # Drop new columns from user_review
    op.drop_column('user_review', 'is_verified_legit')
    op.drop_column('user_review', 'is_verified_spam')
    op.drop_column('user_review', 'risk_level')
    op.drop_column('user_review', 'spam_score_updated_at')
    op.drop_column('user_review', 'spam_score_confidence')
    op.drop_column('user_review', 'spam_score')

    # Drop new tables
    op.drop_table('spam_training_labels')
    op.drop_table('spam_subreddit_list')
    op.drop_table('user_spam_features')
    op.drop_table('author_activity_tracking')
```

---

## 3. Repository Classes

### 3.1 AuthorActivityRepo

**File**: `redditrepostsleuth/core/db/repository/author_activity_repo.py`

```python
"""
Repository for author_activity_tracking table.

This table exists because the main post table (2B rows) has no author index.
All spam detection queries should use this table, not the post table.
"""
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from redditrepostsleuth.core.db.databasemodels import AuthorActivityTracking


class AuthorActivityRepo:
    """Repository for author activity tracking queries."""

    def __init__(self, session: Session):
        self.session = session

    def add(self, activity: AuthorActivityTracking) -> None:
        """Add a new activity record."""
        self.session.add(activity)

    def get_by_id(self, activity_id: int) -> Optional[AuthorActivityTracking]:
        """Get activity record by ID."""
        return self.session.query(AuthorActivityTracking).filter(
            AuthorActivityTracking.id == activity_id
        ).first()

    def get_by_post_id(self, post_id: str) -> Optional[AuthorActivityTracking]:
        """Get activity record by post ID."""
        return self.session.query(AuthorActivityTracking).filter(
            AuthorActivityTracking.post_id == post_id
        ).first()

    def get_by_author(
        self,
        author: str,
        limit: int = 1000,
        since: Optional[datetime] = None
    ) -> List[AuthorActivityTracking]:
        """
        Get activity records for an author.

        Fast due to author index on this table.

        Args:
            author: Reddit username
            limit: Maximum records to return
            since: Only return records after this datetime

        Returns:
            List of activity records ordered by created_at ascending
        """
        query = self.session.query(AuthorActivityTracking).filter(
            AuthorActivityTracking.author == author
        )

        if since:
            query = query.filter(AuthorActivityTracking.created_at >= since)

        return query.order_by(
            AuthorActivityTracking.created_at.asc()
        ).limit(limit).all()

    def get_author_count(self, author: str) -> int:
        """Get total post count for an author."""
        return self.session.query(func.count(AuthorActivityTracking.id)).filter(
            AuthorActivityTracking.author == author
        ).scalar() or 0

    def get_author_subreddit_distribution(self, author: str) -> Dict[str, int]:
        """
        Get count of posts per subreddit for an author.

        Args:
            author: Reddit username

        Returns:
            Dict mapping subreddit name to post count
        """
        results = self.session.query(
            AuthorActivityTracking.subreddit,
            func.count(AuthorActivityTracking.id)
        ).filter(
            AuthorActivityTracking.author == author
        ).group_by(
            AuthorActivityTracking.subreddit
        ).all()

        return {sub: count for sub, count in results}

    def get_author_date_range(self, author: str) -> Optional[tuple]:
        """
        Get first and last post dates for an author.

        Returns:
            Tuple of (first_post_date, last_post_date) or None if no posts
        """
        result = self.session.query(
            func.min(AuthorActivityTracking.created_at),
            func.max(AuthorActivityTracking.created_at)
        ).filter(
            AuthorActivityTracking.author == author
        ).first()

        if result and result[0]:
            return (result[0], result[1])
        return None

    def get_author_adult_platform_stats(self, author: str) -> Dict[str, any]:
        """
        Get adult platform detection stats for an author.

        Returns:
            Dict with counts and platforms detected
        """
        total = self.session.query(func.count(AuthorActivityTracking.id)).filter(
            AuthorActivityTracking.author == author
        ).scalar() or 0

        adult_count = self.session.query(func.count(AuthorActivityTracking.id)).filter(
            AuthorActivityTracking.author == author,
            AuthorActivityTracking.has_adult_platform_link == True
        ).scalar() or 0

        short_link_count = self.session.query(func.count(AuthorActivityTracking.id)).filter(
            AuthorActivityTracking.author == author,
            AuthorActivityTracking.has_short_link == True
        ).scalar() or 0

        platforms = self.session.query(
            AuthorActivityTracking.detected_platform
        ).filter(
            AuthorActivityTracking.author == author,
            AuthorActivityTracking.detected_platform != None
        ).distinct().all()

        return {
            'total_posts': total,
            'adult_platform_count': adult_count,
            'adult_platform_ratio': adult_count / total if total > 0 else 0,
            'short_link_count': short_link_count,
            'short_link_ratio': short_link_count / total if total > 0 else 0,
            'detected_platforms': [p[0] for p in platforms],
        }

    def get_author_nsfw_stats(self, author: str) -> Dict[str, any]:
        """Get NSFW posting stats for an author."""
        total = self.session.query(func.count(AuthorActivityTracking.id)).filter(
            AuthorActivityTracking.author == author
        ).scalar() or 0

        nsfw_count = self.session.query(func.count(AuthorActivityTracking.id)).filter(
            AuthorActivityTracking.author == author,
            AuthorActivityTracking.nsfw == True
        ).scalar() or 0

        return {
            'total_posts': total,
            'nsfw_count': nsfw_count,
            'nsfw_ratio': nsfw_count / total if total > 0 else 0,
        }

    def purge_old_records(self, days: int = 180) -> int:
        """
        Remove records older than specified days.

        Should be run as a nightly maintenance task to keep table size manageable.

        Args:
            days: Delete records older than this many days

        Returns:
            Number of records deleted
        """
        cutoff = datetime.utcnow() - timedelta(days=days)
        deleted = self.session.query(AuthorActivityTracking).filter(
            AuthorActivityTracking.created_at < cutoff
        ).delete()
        return deleted

    def exists_for_post(self, post_id: str) -> bool:
        """Check if activity record exists for a post ID."""
        return self.session.query(
            self.session.query(AuthorActivityTracking).filter(
                AuthorActivityTracking.post_id == post_id
            ).exists()
        ).scalar()
```

---

### 3.2 SpamFeaturesRepo

**File**: `redditrepostsleuth/core/db/repository/spam_features_repo.py`

```python
"""Repository for user_spam_features table."""
from datetime import datetime, timedelta
from typing import List, Optional

from sqlalchemy import desc
from sqlalchemy.orm import Session

from redditrepostsleuth.core.db.databasemodels import UserSpamFeatures


class SpamFeaturesRepo:
    """Repository for spam feature queries."""

    def __init__(self, session: Session):
        self.session = session

    def add(self, features: UserSpamFeatures) -> None:
        """Add a new feature record."""
        self.session.add(features)

    def get_by_id(self, feature_id: int) -> Optional[UserSpamFeatures]:
        """Get feature record by ID."""
        return self.session.query(UserSpamFeatures).filter(
            UserSpamFeatures.id == feature_id
        ).first()

    def get_latest_by_username(self, username: str) -> Optional[UserSpamFeatures]:
        """Get most recent feature record for a user."""
        return self.session.query(UserSpamFeatures).filter(
            UserSpamFeatures.username == username
        ).order_by(
            desc(UserSpamFeatures.computed_at)
        ).first()

    def get_by_username(
        self,
        username: str,
        limit: int = 10
    ) -> List[UserSpamFeatures]:
        """Get feature records for a user, most recent first."""
        return self.session.query(UserSpamFeatures).filter(
            UserSpamFeatures.username == username
        ).order_by(
            desc(UserSpamFeatures.computed_at)
        ).limit(limit).all()

    def get_high_risk_users(
        self,
        min_score: float = 0.6,
        limit: int = 100
    ) -> List[UserSpamFeatures]:
        """Get users with high spam scores."""
        return self.session.query(UserSpamFeatures).filter(
            UserSpamFeatures.final_score >= min_score
        ).order_by(
            desc(UserSpamFeatures.final_score)
        ).limit(limit).all()

    def get_users_needing_update(
        self,
        older_than_days: int = 7,
        limit: int = 100
    ) -> List[str]:
        """Get usernames that haven't been analyzed recently."""
        cutoff = datetime.utcnow() - timedelta(days=older_than_days)

        # Subquery to get latest computed_at per user
        from sqlalchemy import func
        subquery = self.session.query(
            UserSpamFeatures.username,
            func.max(UserSpamFeatures.computed_at).label('latest')
        ).group_by(UserSpamFeatures.username).subquery()

        results = self.session.query(subquery.c.username).filter(
            subquery.c.latest < cutoff
        ).limit(limit).all()

        return [r[0] for r in results]

    def user_was_recently_analyzed(
        self,
        username: str,
        within_days: int = 7
    ) -> bool:
        """Check if user was analyzed within the specified time window."""
        cutoff = datetime.utcnow() - timedelta(days=within_days)
        return self.session.query(
            self.session.query(UserSpamFeatures).filter(
                UserSpamFeatures.username == username,
                UserSpamFeatures.computed_at >= cutoff
            ).exists()
        ).scalar()

    def delete_old_records(
        self,
        username: str,
        keep_count: int = 5
    ) -> int:
        """
        Delete old feature records for a user, keeping most recent.

        Args:
            username: Reddit username
            keep_count: Number of most recent records to keep

        Returns:
            Number of records deleted
        """
        # Get IDs to keep
        keep_ids = [
            r.id for r in self.session.query(UserSpamFeatures.id).filter(
                UserSpamFeatures.username == username
            ).order_by(
                desc(UserSpamFeatures.computed_at)
            ).limit(keep_count).all()
        ]

        if not keep_ids:
            return 0

        deleted = self.session.query(UserSpamFeatures).filter(
            UserSpamFeatures.username == username,
            UserSpamFeatures.id.notin_(keep_ids)
        ).delete(synchronize_session=False)

        return deleted
```

---

### 3.3 SpamSubredditRepo

**File**: `redditrepostsleuth/core/db/repository/spam_subreddit_repo.py`

```python
"""Repository for spam_subreddit_list table."""
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from redditrepostsleuth.core.db.databasemodels import SpamSubredditList


class SpamSubredditRepo:
    """Repository for spam subreddit reference data."""

    def __init__(self, session: Session):
        self.session = session

    def add(self, subreddit: SpamSubredditList) -> None:
        """Add a new subreddit entry."""
        self.session.add(subreddit)

    def get_by_name(self, subreddit: str) -> Optional[SpamSubredditList]:
        """Get subreddit entry by name (case-insensitive)."""
        return self.session.query(SpamSubredditList).filter(
            SpamSubredditList.subreddit == subreddit.lower()
        ).first()

    def get_all(self) -> List[SpamSubredditList]:
        """Get all subreddit entries."""
        return self.session.query(SpamSubredditList).all()

    def get_by_category(self, category: str) -> List[SpamSubredditList]:
        """Get subreddits by risk category."""
        return self.session.query(SpamSubredditList).filter(
            SpamSubredditList.risk_category == category
        ).all()

    def get_as_dict(self) -> Dict[str, Tuple[str, float]]:
        """
        Get all subreddits as a dict for fast lookup.

        Returns:
            Dict mapping lowercase subreddit name to (category, weight) tuple
        """
        results = self.session.query(SpamSubredditList).all()
        return {
            s.subreddit.lower(): (s.risk_category, s.weight)
            for s in results
        }

    def get_karma_farm_subs(self) -> List[str]:
        """Get list of karma farming subreddit names."""
        results = self.session.query(SpamSubredditList.subreddit).filter(
            SpamSubredditList.risk_category == 'KARMA_FARM'
        ).all()
        return [r[0] for r in results]

    def delete(self, subreddit: str) -> bool:
        """Delete a subreddit entry."""
        deleted = self.session.query(SpamSubredditList).filter(
            SpamSubredditList.subreddit == subreddit.lower()
        ).delete()
        return deleted > 0

    def update_weight(self, subreddit: str, weight: float) -> bool:
        """Update the weight for a subreddit."""
        updated = self.session.query(SpamSubredditList).filter(
            SpamSubredditList.subreddit == subreddit.lower()
        ).update({'weight': weight})
        return updated > 0
```

---

### 3.4 SpamTrainingLabelsRepo

**File**: `redditrepostsleuth/core/db/repository/spam_training_labels_repo.py`

```python
"""Repository for spam_training_labels table."""
from typing import List, Optional

from sqlalchemy.orm import Session

from redditrepostsleuth.core.db.databasemodels import SpamTrainingLabels


class SpamTrainingLabelsRepo:
    """Repository for spam training label data."""

    def __init__(self, session: Session):
        self.session = session

    def add(self, label: SpamTrainingLabels) -> None:
        """Add or update a label entry."""
        existing = self.get_by_username(label.username)
        if existing:
            # Update existing
            existing.label = label.label
            existing.labeled_by = label.labeled_by
            existing.labeled_at = label.labeled_at
            existing.confidence = label.confidence
            existing.source_url = label.source_url
            existing.notes = label.notes
        else:
            self.session.add(label)

    def get_by_username(self, username: str) -> Optional[SpamTrainingLabels]:
        """Get label entry by username."""
        return self.session.query(SpamTrainingLabels).filter(
            SpamTrainingLabels.username == username
        ).first()

    def get_all(self) -> List[SpamTrainingLabels]:
        """Get all label entries."""
        return self.session.query(SpamTrainingLabels).all()

    def get_by_label(self, label: str) -> List[SpamTrainingLabels]:
        """Get entries by label type (SPAM, LEGITIMATE, UNKNOWN)."""
        return self.session.query(SpamTrainingLabels).filter(
            SpamTrainingLabels.label == label
        ).all()

    def get_spam_usernames(self) -> List[str]:
        """Get list of usernames labeled as SPAM."""
        results = self.session.query(SpamTrainingLabels.username).filter(
            SpamTrainingLabels.label == 'SPAM'
        ).all()
        return [r[0] for r in results]

    def get_legitimate_usernames(self) -> List[str]:
        """Get list of usernames labeled as LEGITIMATE."""
        results = self.session.query(SpamTrainingLabels.username).filter(
            SpamTrainingLabels.label == 'LEGITIMATE'
        ).all()
        return [r[0] for r in results]

    def get_label_counts(self) -> dict:
        """Get count of labels by type."""
        from sqlalchemy import func
        results = self.session.query(
            SpamTrainingLabels.label,
            func.count(SpamTrainingLabels.username)
        ).group_by(SpamTrainingLabels.label).all()
        return {label: count for label, count in results}

    def get_by_source(self, source: str) -> List[SpamTrainingLabels]:
        """Get entries by labeling source."""
        return self.session.query(SpamTrainingLabels).filter(
            SpamTrainingLabels.labeled_by == source
        ).all()

    def delete(self, username: str) -> bool:
        """Delete a label entry."""
        deleted = self.session.query(SpamTrainingLabels).filter(
            SpamTrainingLabels.username == username
        ).delete()
        return deleted > 0

    def get_high_confidence_labels(
        self,
        min_confidence: float = 0.8
    ) -> List[SpamTrainingLabels]:
        """Get labels with high confidence scores."""
        return self.session.query(SpamTrainingLabels).filter(
            SpamTrainingLabels.confidence >= min_confidence
        ).all()
```

---

## 4. Unit of Work Integration

### File: `redditrepostsleuth/core/db/uow/unitofworkmanager.py`

Add the new repositories to the Unit of Work pattern.

**Imports to add**:
```python
from redditrepostsleuth.core.db.repository.author_activity_repo import AuthorActivityRepo
from redditrepostsleuth.core.db.repository.spam_features_repo import SpamFeaturesRepo
from redditrepostsleuth.core.db.repository.spam_subreddit_repo import SpamSubredditRepo
from redditrepostsleuth.core.db.repository.spam_training_labels_repo import SpamTrainingLabelsRepo
```

**Properties to add in UnitOfWork class**:
```python
@property
def author_activity(self) -> AuthorActivityRepo:
    """Repository for author activity tracking."""
    if not hasattr(self, '_author_activity'):
        self._author_activity = AuthorActivityRepo(self.session)
    return self._author_activity

@property
def spam_features(self) -> SpamFeaturesRepo:
    """Repository for user spam features."""
    if not hasattr(self, '_spam_features'):
        self._spam_features = SpamFeaturesRepo(self.session)
    return self._spam_features

@property
def spam_subreddits(self) -> SpamSubredditRepo:
    """Repository for spam subreddit list."""
    if not hasattr(self, '_spam_subreddits'):
        self._spam_subreddits = SpamSubredditRepo(self.session)
    return self._spam_subreddits

@property
def spam_training_labels(self) -> SpamTrainingLabelsRepo:
    """Repository for spam training labels."""
    if not hasattr(self, '_spam_training_labels'):
        self._spam_training_labels = SpamTrainingLabelsRepo(self.session)
    return self._spam_training_labels
```

---

## 5. Ingest Pipeline Integration

### File: `redditrepostsleuth/ingestsvc/postingestor.py`

Add author activity tracking to the post ingest flow.

### 5.1 Link Detection Constants

Add at module level:
```python
# Adult platform patterns for spam detection
# Format: (pattern_to_match, platform_name)
ADULT_PLATFORM_PATTERNS = [
    ('onlyfans.com', 'onlyfans'),
    ('fansly.com', 'fansly'),
    ('fancentro.com', 'fancentro'),
    ('manyvids.com', 'manyvids'),
    ('pornhub.com/model', 'pornhub'),
    ('chaturbate.com', 'chaturbate'),
    ('stripchat.com', 'stripchat'),
    ('cam4.com', 'cam4'),
    ('bongacams.com', 'bongacams'),
    ('myfreecams.com', 'myfreecams'),
    ('camsoda.com', 'camsoda'),
    ('livejasmin.com', 'livejasmin'),
    ('ismygirl.com', 'ismygirl'),
    ('loyalfans.com', 'loyalfans'),
    ('justfor.fans', 'justforfans'),
    ('frisk.chat', 'frisk'),
    ('unfiltrd.com', 'unfiltrd'),
    ('patreon.com', 'patreon'),  # Lower confidence, many legitimate uses
]

# Short link / bio link patterns
SHORT_LINK_PATTERNS = [
    'linktr.ee',
    'beacons.ai',
    'allmylinks.com',
    'linkin.bio',
    'bio.link',
    'campsite.bio',
    'throne.me',
    'hoo.be',
    'solo.to',
    'carrd.co',
    'linktree.com',
    'stan.store',
    'snipfeed.co',
    'tap.bio',
    'lnk.bio',
    'withkoji.com',
    'flow.page',
    'link.space',
    'msha.ke',
    'shor.by',
    'many.link',
]
```

### 5.2 Detection Functions

```python
from typing import Optional, Tuple


def detect_adult_platform_link(url: str) -> Tuple[bool, Optional[str]]:
    """
    Check if URL contains an adult platform link.

    Args:
        url: URL to check

    Returns:
        Tuple of (found: bool, platform_name: Optional[str])
    """
    if not url:
        return False, None

    url_lower = url.lower()
    for pattern, platform in ADULT_PLATFORM_PATTERNS:
        if pattern in url_lower:
            return True, platform

    return False, None


def detect_short_link(url: str) -> bool:
    """
    Check if URL is a common promo/bio short link service.

    Args:
        url: URL to check

    Returns:
        True if URL matches a known short link pattern
    """
    if not url:
        return False

    url_lower = url.lower()
    return any(pattern in url_lower for pattern in SHORT_LINK_PATTERNS)
```

### 5.3 Modified Post Saving Logic

Find the method that saves posts and add tracking alongside it:

```python
def save_post_with_tracking(self, post: Post) -> None:
    """
    Save post and track author activity for spam detection.

    This method saves the post normally AND creates a lightweight
    tracking record in author_activity_tracking for spam detection queries.
    """
    # Detect adult platform and short links at ingest time
    has_adult_link, platform = detect_adult_platform_link(post.url)
    has_short_link = detect_short_link(post.url)

    with self.uowm.start() as uow:
        # Save the post as normal
        uow.posts.add(post)

        # Also track for spam detection (lightweight table with indexes)
        # Skip if already tracked (handles re-ingestion)
        if not uow.author_activity.exists_for_post(post.post_id):
            uow.author_activity.add(AuthorActivityTracking(
                post_id=post.post_id,
                author=post.author,
                subreddit=post.subreddit,
                created_at=post.created_at,
                nsfw=post.nsfw,
                post_type_id=post.post_type_id,
                has_adult_platform_link=has_adult_link,
                has_short_link=has_short_link,
                detected_platform=platform,
            ))

        uow.commit()
```

**Import to add**:
```python
from redditrepostsleuth.core.db.databasemodels import AuthorActivityTracking
```

---

## 8. Database Connection Pool

The spam detection system will add significant database load through parallel feature extraction and scoring tasks. Proper connection pool configuration is critical.

### Connection Pool Configuration

**File**: `redditrepostsleuth/core/db/databasemanager.py` or SQLAlchemy engine initialization

```python
from sqlalchemy import create_engine
from sqlalchemy.pool import QueuePool

# Current configuration (example)
engine = create_engine(
    DATABASE_URL,
    # Increase pool size for spam detection tasks
    poolclass=QueuePool,
    pool_size=20,           # Current connections to maintain
    max_overflow=10,        # Additional connections if needed
    pool_recycle=3600,      # Recycle connections after 1 hour (MySQL default)
    pool_pre_ping=True,     # Test connection before using (avoid "gone away" errors)
    echo_pool=False,        # Set to True to debug pool issues
    connect_args={
        'connect_timeout': 10,
        'autocommit': False,
    }
)
```

### Monitoring Connection Pool Health

Add monitoring to track pool usage:

```python
# Check pool status during operation
print(f"Pool size: {engine.pool.size()}")
print(f"Checked out connections: {engine.pool.checkedout()}")
print(f"Pool overflow: {engine.pool.overflow()}")
```

### Recommended Settings

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| `pool_size` | 20 | Base connections maintained |
| `max_overflow` | 10 | Emergency overflow capacity |
| `pool_recycle` | 3600 | MySQL wait_timeout default |
| `pool_pre_ping` | True | Avoid stale connection errors |

### Capacity Planning

With `pool_size=20` and `max_overflow=10`:
- **Normal load**: 15-18 concurrent connections
- **Peak load**: Up to 30 concurrent connections
- **Safe headroom**: 10 connections for other operations

### Read Replica Strategy

For large-scale deployments:

```python
# Create separate engine for read-only queries
read_engine = create_engine(
    READ_REPLICA_URL,  # Read-only database endpoint
    poolclass=QueuePool,
    pool_size=15,       # Smaller pool for read replica
    max_overflow=5,
    pool_pre_ping=True,
)

# Use read_engine for feature extraction queries
# Use main engine for writes
```

---

## 9. Celery Queue Configuration

### File: `redditrepostsleuth/core/celery/celeryconfig.py`

Add the new spam detection queue.

**Add to task_queues**:
```python
Queue('spam_detection', routing_key='spam_detection'),
```

**Add to task_routes**:
```python
'redditrepostsleuth.core.celery.tasks.spam_detection_tasks.*': {'queue': 'spam_detection'},
```

---

## 10. Phase 0.5: Infrastructure Validation Checklist

After Phase 0 database setup is complete, Phase 0.5 (1 week) validates infrastructure before moving to feature extraction.

### Infrastructure Validation Tasks

**Database Migrations**:
- [ ] Run `alembic upgrade head` successfully
- [ ] Verify all 4 new tables exist in database
- [ ] Verify all new columns added to existing tables
- [ ] Verify seed data in `spam_subreddit_list` (14 rows)
- [ ] Verify all indexes created
- [ ] Verify table partitioning strategy documented and ready

**Author Activity Tracking**:
- [ ] Simulate post ingest with `SPAM_AUTHOR_TRACKING_ENABLED=True`
- [ ] Verify `author_activity_tracking` records created
- [ ] Verify adult platform detection working (sample post with OnlyFans link)
- [ ] Verify short link detection working (sample post with linktr.ee)
- [ ] Check for duplicates on re-ingest (post_id unique constraint)

**Load Testing** (with test data):
- [ ] Ingest 10,000 posts with author tracking enabled
- [ ] Measure ingest pipeline latency impact
- [ ] Verify no performance degradation (should be <100ms per post)
- [ ] Check author_activity_tracking table size (expect ~10K rows)
- [ ] Verify indexes used (check query plans)

**Connection Pool Validation**:
- [ ] Increase `pool_size` to 20 as recommended
- [ ] Monitor pool connections during simulated load
- [ ] Verify no "Pool timeout" errors under normal load
- [ ] Test pool_pre_ping with network interruption simulation

**Repository Testing**:
- [ ] AuthorActivityRepo.get_by_author uses index (< 100ms for 1000 rows)
- [ ] AuthorActivityRepo.get_author_subreddit_distribution works
- [ ] SpamFeaturesRepo instantiates correctly
- [ ] SpamSubredditRepo.get_as_dict returns correct format (14 rows)
- [ ] SpamTrainingLabelsRepo instantiates correctly

**Unit of Work Integration**:
- [ ] All 4 new repositories available via UnitOfWork
- [ ] No initialization errors
- [ ] Test transaction handling (commit/rollback)

**Celery Queue Setup**:
- [ ] Spam detection queue configured in celeryconfig
- [ ] Queue visible in Celery monitoring tools
- [ ] Can route test task to spam_detection queue

**Documentation**:
- [ ] Update README with SPAM_AUTHOR_TRACKING_ENABLED flag
- [ ] Document table partitioning maintenance procedure
- [ ] Document connection pool configuration
- [ ] Team trained on Phase 0.5 validation procedures

### Success Criteria

- All database structures verified
- Ingest pipeline latency impact <100ms per post
- No errors under sustained load (100 posts/second)
- Connection pool stable under 20 concurrent connections
- All repositories tested and working

---

## 11. Testing Strategy

### 7.1 Unit Tests

**File**: `tests/core/db/repository/test_author_activity_repo.py`

```python
"""Tests for AuthorActivityRepo."""
import unittest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from redditrepostsleuth.core.db.databasemodels import AuthorActivityTracking
from redditrepostsleuth.core.db.repository.author_activity_repo import AuthorActivityRepo


class TestAuthorActivityRepo(unittest.TestCase):

    def setUp(self):
        self.mock_session = MagicMock()
        self.repo = AuthorActivityRepo(self.mock_session)

    def test_get_by_author_returns_ordered_results(self):
        """Test that results are ordered by created_at ascending."""
        # Setup mock query chain
        mock_query = MagicMock()
        self.mock_session.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query

        expected = [
            AuthorActivityTracking(author='testuser', created_at=datetime(2025, 1, 1)),
            AuthorActivityTracking(author='testuser', created_at=datetime(2025, 1, 2)),
        ]
        mock_query.all.return_value = expected

        result = self.repo.get_by_author('testuser')

        self.assertEqual(result, expected)
        mock_query.order_by.assert_called_once()

    def test_get_author_count_returns_zero_for_unknown_user(self):
        """Test count returns 0 for user with no activity."""
        mock_query = MagicMock()
        self.mock_session.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.scalar.return_value = None

        result = self.repo.get_author_count('unknownuser')

        self.assertEqual(result, 0)
```

### 7.2 Integration Tests

```python
"""Integration tests for spam detection database operations."""
import unittest
from datetime import datetime

from redditrepostsleuth.core.db.databasemodels import (
    AuthorActivityTracking,
    UserSpamFeatures,
    SpamSubredditList,
    SpamTrainingLabels,
)


class TestSpamDetectionIntegration(unittest.TestCase):
    """Integration tests using test database."""

    @classmethod
    def setUpClass(cls):
        # Setup test database connection
        pass

    def test_author_activity_tracking_roundtrip(self):
        """Test saving and retrieving author activity."""
        pass

    def test_spam_features_latest_retrieval(self):
        """Test getting latest features for a user."""
        pass
```

### 7.3 Link Detection Tests

```python
"""Tests for adult platform and short link detection."""
import unittest

from redditrepostsleuth.ingestsvc.postingestor import (
    detect_adult_platform_link,
    detect_short_link,
)


class TestLinkDetection(unittest.TestCase):

    def test_detect_onlyfans_link(self):
        """Test OnlyFans URL detection."""
        url = "https://onlyfans.com/someuser"
        found, platform = detect_adult_platform_link(url)
        self.assertTrue(found)
        self.assertEqual(platform, 'onlyfans')

    def test_detect_fansly_link(self):
        """Test Fansly URL detection."""
        url = "https://fansly.com/creator123"
        found, platform = detect_adult_platform_link(url)
        self.assertTrue(found)
        self.assertEqual(platform, 'fansly')

    def test_no_false_positive_on_regular_url(self):
        """Test that regular URLs don't trigger detection."""
        url = "https://reddit.com/r/pics"
        found, platform = detect_adult_platform_link(url)
        self.assertFalse(found)
        self.assertIsNone(platform)

    def test_detect_linktree(self):
        """Test linktr.ee detection."""
        url = "https://linktr.ee/someuser"
        self.assertTrue(detect_short_link(url))

    def test_detect_beacons(self):
        """Test beacons.ai detection."""
        url = "https://beacons.ai/creator"
        self.assertTrue(detect_short_link(url))

    def test_no_false_positive_short_link(self):
        """Test regular URLs don't trigger short link detection."""
        url = "https://imgur.com/gallery/abc123"
        self.assertFalse(detect_short_link(url))

    def test_case_insensitive_detection(self):
        """Test detection is case-insensitive."""
        url = "https://ONLYFANS.COM/User123"
        found, platform = detect_adult_platform_link(url)
        self.assertTrue(found)

    def test_empty_url_handling(self):
        """Test empty/None URL handling."""
        self.assertEqual(detect_adult_platform_link(None), (False, None))
        self.assertEqual(detect_adult_platform_link(''), (False, None))
        self.assertFalse(detect_short_link(None))
        self.assertFalse(detect_short_link(''))
```

---

## 12. Verification Checklist

### Pre-Implementation
- [ ] Backup existing database
- [ ] Review existing UserReview model usage
- [ ] Review existing MonitoredSub model usage
- [ ] Verify Alembic migration chain is intact

### Migration
- [ ] Run `alembic upgrade head` successfully
- [ ] Verify all new tables created
- [ ] Verify all new columns added
- [ ] Verify seed data inserted into spam_subreddit_list
- [ ] Verify indexes created

### Repository Testing
- [ ] AuthorActivityRepo.get_by_author works correctly
- [ ] AuthorActivityRepo.get_author_subreddit_distribution works
- [ ] SpamFeaturesRepo.get_latest_by_username works
- [ ] SpamSubredditRepo.get_as_dict returns correct format

### Ingest Integration
- [ ] New posts create author_activity_tracking records
- [ ] Adult platform detection triggers correctly
- [ ] Short link detection triggers correctly
- [ ] Duplicate post_id handling works (no errors on re-ingest)

### Performance
- [ ] Query on author_activity_tracking.author uses index
- [ ] No noticeable latency increase in post ingest
- [ ] Memory usage stable after 1000 ingested posts

---

## Rollback Procedure

If issues are encountered:

1. **Revert Alembic migration**:
   ```bash
   alembic downgrade -1
   ```

2. **Revert code changes**:
   - Remove new repository files
   - Revert changes to databasemodels.py
   - Revert changes to unitofworkmanager.py
   - Revert changes to postingestor.py

3. **Verify rollback**:
   - Confirm tables dropped
   - Confirm columns removed
   - Run existing test suite

---

## Dependencies

### Python Packages
No new packages required for Phase 0.

### Database
- MySQL 5.7+ (for JSON column support)
- Sufficient disk space for new table (~10GB initial allocation)

---

## Estimated Effort

| Task | Estimate |
|------|----------|
| Database models | 2 hours |
| Alembic migration | 1 hour |
| Repository classes | 4 hours |
| UoW integration | 1 hour |
| Ingest pipeline changes | 3 hours |
| Celery config | 30 minutes |
| Unit tests | 4 hours |
| Integration testing | 3 hours |
| Documentation | 2 hours |
| **Total** | ~20 hours |
