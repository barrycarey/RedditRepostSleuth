# Phase 1: Tier 1 Feature Extraction

## Overview
- **Duration**: Week 3-4
- **Dependencies**: Phase 0 (Database schema, repositories)
- **Goal**: Extract spam detection features from existing database data with zero API calls

---

## Table of Contents
1. [Feature Definitions](#1-feature-definitions)
2. [SpamFeatureExtractor Service](#2-spamfeatureextractor-service)
3. [Username Pattern Analysis](#3-username-pattern-analysis)
4. [Celery Tasks](#4-celery-tasks)
5. [Repost Data Integration](#5-repost-data-integration)
6. [Testing Strategy](#6-testing-strategy)
7. [Verification Checklist](#7-verification-checklist)

---

## 1. Feature Definitions

### Tier 1 Features (Zero API Cost)

These features are extracted entirely from existing database tables.

| Feature | Source Table | Description | Spam Indicator |
|---------|--------------|-------------|----------------|
| `total_posts_indexed` | `author_activity_tracking` | Total posts by this author in our index | High volume = suspicious |
| `total_reposts_detected` | `repost` | Number of posts flagged as reposts | High count = suspicious |
| `repost_ratio` | Calculated | `reposts / total_posts` | >0.5 suspicious, >0.7 very suspicious |
| `unique_subreddits_posted` | `author_activity_tracking` | Distinct subreddits posted to | Low diversity = suspicious |
| `posts_per_day_avg` | Calculated | Posts per day since first post | >10/day = suspicious |
| `first_post_date` | `author_activity_tracking` | Date of first indexed post | Recent + high volume = suspicious |
| `last_post_date` | `author_activity_tracking` | Date of most recent post | - |
| `nsfw_post_ratio` | `author_activity_tracking` | Ratio of NSFW posts | High + adult links = suspicious |
| `summons_received` | `summons` | Times bot was summoned on user's posts | High count = suspicious |
| `adult_platform_post_count` | `author_activity_tracking` | Posts with OnlyFans/Fansly/etc. links | >0 = suspicious |
| `adult_platform_ratio` | Calculated | Ratio of posts with adult links | >0.2 = suspicious |
| `short_link_post_count` | `author_activity_tracking` | Posts with linktr.ee/beacons.ai/etc. | Multiple = suspicious |
| `short_link_ratio` | Calculated | Ratio of posts with short links | >0.3 = suspicious |
| `detected_platforms` | `author_activity_tracking` | List of adult platforms detected | Multiple platforms = very suspicious |
| `username_suspicious_pattern` | Calculated | Username matches spam patterns | True = suspicious |
| `karma_farming_sub_posts` | `author_activity_tracking` + `spam_subreddit_list` | Posts to known karma farm subs | >0 = suspicious |

---

## 2. SpamFeatureExtractor Service

### File: `redditrepostsleuth/core/services/spam/spam_feature_extractor.py`

```python
"""
Spam Feature Extractor Service

Extracts spam detection features from existing database data.
Tier 1 features require zero Reddit API calls.
"""
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Set

from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager

log = logging.getLogger(__name__)


@dataclass
class Tier1Features:
    """Container for Tier 1 (zero API cost) features."""

    # Basic activity metrics
    total_posts_indexed: int
    total_reposts_detected: int
    repost_ratio: float
    unique_subreddits_posted: int
    posts_per_day_avg: float
    first_post_date: Optional[datetime]
    last_post_date: Optional[datetime]
    nsfw_post_ratio: float
    summons_received: int

    # Adult platform/promo detection
    adult_platform_post_count: int
    adult_platform_ratio: float
    short_link_post_count: int
    short_link_ratio: float
    detected_platforms: List[str]

    # Username analysis
    username_suspicious_pattern: bool
    username_pattern_matches: Dict[str, bool]

    # Subreddit analysis
    subreddit_distribution: Dict[str, int]
    karma_farming_sub_posts: int
    easy_karma_sub_posts: int

    def to_dict(self) -> dict:
        """Convert to dictionary for storage."""
        return {
            'total_posts_indexed': self.total_posts_indexed,
            'total_reposts_detected': self.total_reposts_detected,
            'repost_ratio': self.repost_ratio,
            'unique_subreddits_posted': self.unique_subreddits_posted,
            'posts_per_day_avg': self.posts_per_day_avg,
            'first_post_date': self.first_post_date,
            'last_post_date': self.last_post_date,
            'nsfw_post_ratio': self.nsfw_post_ratio,
            'summons_received': self.summons_received,
            'adult_platform_post_count': self.adult_platform_post_count,
            'adult_platform_ratio': self.adult_platform_ratio,
            'short_link_post_count': self.short_link_post_count,
            'short_link_ratio': self.short_link_ratio,
            'detected_platforms': self.detected_platforms,
            'username_suspicious_pattern': self.username_suspicious_pattern,
            'username_pattern_matches': self.username_pattern_matches,
            'subreddit_distribution': self.subreddit_distribution,
            'karma_farming_sub_posts': self.karma_farming_sub_posts,
            'easy_karma_sub_posts': self.easy_karma_sub_posts,
        }


class SpamFeatureExtractor:
    """
    Extracts spam detection features from existing database data.

    This service extracts Tier 1 features which require no Reddit API calls.
    All data comes from our existing database tables.
    """

    def __init__(self, uowm: UnitOfWorkManager):
        """
        Initialize the feature extractor.

        Args:
            uowm: Unit of Work Manager for database access
        """
        self.uowm = uowm
        self._spam_subs_cache: Optional[Dict[str, tuple]] = None
        self._spam_subs_cache_time: Optional[datetime] = None

    def _get_spam_subreddits(self) -> Dict[str, tuple]:
        """
        Get spam subreddit list with caching.

        Returns:
            Dict mapping lowercase subreddit name to (category, weight) tuple
        """
        # Cache for 1 hour
        now = datetime.utcnow()
        if (self._spam_subs_cache is None or
            self._spam_subs_cache_time is None or
            (now - self._spam_subs_cache_time).seconds > 3600):

            with self.uowm.start() as uow:
                self._spam_subs_cache = uow.spam_subreddits.get_as_dict()
            self._spam_subs_cache_time = now

        return self._spam_subs_cache

    def extract_tier1_features(self, username: str) -> Optional[Tier1Features]:
        """
        Extract Tier 1 features for a user.

        These features require no additional Reddit API calls - all data
        comes from the author_activity_tracking table and related tables.

        Args:
            username: Reddit username to analyze

        Returns:
            Tier1Features dataclass or None if user has no tracked activity
        """
        log.debug(f"Extracting Tier 1 features for user: {username}")

        with self.uowm.start() as uow:
            # Get activity from tracking table (indexed, fast)
            activity = uow.author_activity.get_by_author(username)

            if not activity:
                log.debug(f"No activity found for user: {username}")
                return None

            # Get repost data
            reposts = uow.repost.get_reposts_by_author(username)
            repost_count = len(reposts) if reposts else 0

            # Get summons data
            summons_count = uow.summons.count_by_requestor(username)

            # Calculate basic metrics
            total_posts = len(activity)
            repost_ratio = repost_count / total_posts if total_posts > 0 else 0

            # Subreddit distribution
            subreddit_distribution = {}
            nsfw_count = 0
            adult_platform_count = 0
            short_link_count = 0
            detected_platforms: Set[str] = set()

            for record in activity:
                sub = record.subreddit.lower()
                subreddit_distribution[sub] = subreddit_distribution.get(sub, 0) + 1

                if record.nsfw:
                    nsfw_count += 1

                if record.has_adult_platform_link:
                    adult_platform_count += 1
                    if record.detected_platform:
                        detected_platforms.add(record.detected_platform)

                if record.has_short_link:
                    short_link_count += 1

            # Date range calculation
            sorted_activity = sorted(activity, key=lambda a: a.created_at)
            first_post_date = sorted_activity[0].created_at
            last_post_date = sorted_activity[-1].created_at
            date_range_days = (last_post_date - first_post_date).days or 1

            # Spam subreddit analysis
            spam_subs = self._get_spam_subreddits()
            karma_farming_posts = 0
            easy_karma_posts = 0

            for sub, count in subreddit_distribution.items():
                if sub in spam_subs:
                    category, weight = spam_subs[sub]
                    if category == 'KARMA_FARM':
                        karma_farming_posts += count
                    elif category == 'EASY_TARGET':
                        easy_karma_posts += count

            # Username pattern analysis
            pattern_analysis = self.check_username_pattern(username)

            return Tier1Features(
                total_posts_indexed=total_posts,
                total_reposts_detected=repost_count,
                repost_ratio=repost_ratio,
                unique_subreddits_posted=len(subreddit_distribution),
                posts_per_day_avg=total_posts / date_range_days,
                first_post_date=first_post_date,
                last_post_date=last_post_date,
                nsfw_post_ratio=nsfw_count / total_posts if total_posts > 0 else 0,
                summons_received=summons_count,
                adult_platform_post_count=adult_platform_count,
                adult_platform_ratio=adult_platform_count / total_posts if total_posts > 0 else 0,
                short_link_post_count=short_link_count,
                short_link_ratio=short_link_count / total_posts if total_posts > 0 else 0,
                detected_platforms=list(detected_platforms),
                username_suspicious_pattern=pattern_analysis['suspicious'],
                username_pattern_matches=pattern_analysis['matches'],
                subreddit_distribution=subreddit_distribution,
                karma_farming_sub_posts=karma_farming_posts,
                easy_karma_sub_posts=easy_karma_posts,
            )

    def check_username_pattern(self, username: str) -> Dict[str, any]:
        """
        Check username against known spam patterns.

        Common spam username patterns:
        - WordWordNumbers (e.g., BrightSky1847)
        - Adjective-Noun-Numbers (e.g., Happy-Cat-2847)
        - Random alphanumeric strings (e.g., aj83hdk92lsm)
        - Default Reddit format (e.g., Prestigious_Hat_8937)

        Args:
            username: Reddit username to analyze

        Returns:
            Dict with 'suspicious' bool and 'matches' dict of pattern matches
        """
        patterns = {
            # Reddit auto-generated: Word_Word_Numbers
            'reddit_autogenerated': r'^[A-Z][a-z]+_[A-Z][a-z]+_\d{3,5}$',

            # PascalCase with trailing numbers: WordWordNumbers
            'word_word_numbers': r'^[A-Z][a-z]+[A-Z][a-z]+\d{2,4}$',

            # Hyphenated: Adjective-Noun-Numbers
            'adjective_noun_numbers': r'^[A-Z][a-z]+-[A-Z][a-z]+-\d{3,5}$',

            # Long random alphanumeric (12+ chars, mixed case/numbers)
            'random_alphanumeric': r'^[a-zA-Z0-9]{12,}$',

            # All lowercase word+numbers
            'lowercase_word_numbers': r'^[a-z]+\d{4,}$',

            # Underscore separated random-looking
            'underscore_random': r'^[a-z]+_[a-z]+_[a-z0-9]+$',

            # Repeated characters (bots often have patterns like aaa111)
            'repeated_pattern': r'(.)\1{2,}',
        }

        matches = {}
        for name, pattern in patterns.items():
            matches[name] = bool(re.match(pattern, username))

        # Special check: ends with exactly 4 digits (very common in spam)
        matches['ends_4_digits'] = bool(re.search(r'\d{4}$', username))

        # Special check: no vowels (often generated usernames)
        vowel_count = sum(1 for c in username.lower() if c in 'aeiou')
        letter_count = sum(1 for c in username if c.isalpha())
        matches['low_vowel_ratio'] = (vowel_count / letter_count < 0.15) if letter_count > 5 else False

        # Suspicious if any high-confidence pattern matches
        high_confidence_patterns = [
            'reddit_autogenerated',
            'word_word_numbers',
            'adjective_noun_numbers',
            'random_alphanumeric',
        ]
        suspicious = any(matches.get(p, False) for p in high_confidence_patterns)

        return {
            'suspicious': suspicious,
            'matches': matches,
        }

    def extract_subreddit_behavior(self, username: str) -> Dict[str, any]:
        """
        Analyze user's subreddit posting behavior.

        Looks for patterns like:
        - Concentrated posting in few subreddits
        - Heavy karma farming sub usage
        - NSFW sub concentration

        Args:
            username: Reddit username to analyze

        Returns:
            Dict with subreddit behavior analysis
        """
        with self.uowm.start() as uow:
            distribution = uow.author_activity.get_author_subreddit_distribution(username)

        if not distribution:
            return {'has_data': False}

        total_posts = sum(distribution.values())
        unique_subs = len(distribution)

        # Calculate concentration (Herfindahl index)
        # Higher = more concentrated in fewer subs
        hhi = sum((count / total_posts) ** 2 for count in distribution.values())

        # Top subreddit percentage
        max_sub_count = max(distribution.values())
        top_sub_pct = max_sub_count / total_posts

        # Get spam sub categorization
        spam_subs = self._get_spam_subreddits()
        karma_farm_posts = sum(
            count for sub, count in distribution.items()
            if sub.lower() in spam_subs and spam_subs[sub.lower()][0] == 'KARMA_FARM'
        )

        return {
            'has_data': True,
            'total_posts': total_posts,
            'unique_subreddits': unique_subs,
            'concentration_index': hhi,  # 0-1, higher = more concentrated
            'top_subreddit_percentage': top_sub_pct,
            'karma_farm_post_count': karma_farm_posts,
            'karma_farm_post_ratio': karma_farm_posts / total_posts if total_posts > 0 else 0,
            'top_subreddits': sorted(
                distribution.items(),
                key=lambda x: x[1],
                reverse=True
            )[:5],
        }

    def get_activity_timeline(self, username: str) -> Dict[str, any]:
        """
        Analyze user's posting timeline.

        Looks for patterns like:
        - Burst posting (many posts in short time)
        - Regular intervals (bot-like)
        - Time of day patterns

        Args:
            username: Reddit username to analyze

        Returns:
            Dict with timeline analysis
        """
        with self.uowm.start() as uow:
            activity = uow.author_activity.get_by_author(username, limit=500)

        if not activity or len(activity) < 2:
            return {'has_data': False}

        # Sort by timestamp
        sorted_activity = sorted(activity, key=lambda a: a.created_at)

        # Calculate intervals between posts (in minutes)
        intervals = []
        for i in range(1, len(sorted_activity)):
            delta = (sorted_activity[i].created_at - sorted_activity[i-1].created_at)
            intervals.append(delta.total_seconds() / 60)

        if not intervals:
            return {'has_data': False}

        # Basic interval statistics
        avg_interval = sum(intervals) / len(intervals)
        min_interval = min(intervals)

        # Count rapid-fire posts (less than 2 minutes apart)
        rapid_posts = sum(1 for i in intervals if i < 2)

        # Hour distribution (for entropy calculation)
        hour_counts = {}
        for record in activity:
            hour = record.created_at.hour
            hour_counts[hour] = hour_counts.get(hour, 0) + 1

        # Calculate posting hour entropy (low = concentrated in few hours)
        import math
        total = sum(hour_counts.values())
        entropy = 0
        for count in hour_counts.values():
            if count > 0:
                p = count / total
                entropy -= p * math.log2(p)

        # Max entropy for 24 hours is log2(24) ≈ 4.58
        # Normalize to 0-1
        normalized_entropy = entropy / math.log2(24) if entropy > 0 else 0

        return {
            'has_data': True,
            'post_count': len(activity),
            'avg_interval_minutes': avg_interval,
            'min_interval_minutes': min_interval,
            'rapid_fire_posts': rapid_posts,
            'rapid_fire_ratio': rapid_posts / len(intervals) if intervals else 0,
            'posting_hour_entropy': normalized_entropy,  # 0-1, low = suspicious
            'active_hours': len(hour_counts),
            'most_active_hour': max(hour_counts, key=hour_counts.get) if hour_counts else None,
        }

    def is_user_worth_analyzing(self, username: str) -> bool:
        """
        Quick check if user has enough data for meaningful analysis.

        Args:
            username: Reddit username

        Returns:
            True if user has sufficient activity for analysis
        """
        with self.uowm.start() as uow:
            count = uow.author_activity.get_author_count(username)
            return count >= 3  # Need at least 3 posts for patterns
```

---

## 3. Username Pattern Analysis

### Detailed Pattern Reference

The username pattern analyzer identifies common spam username formats.

#### Reddit Auto-Generated Usernames
Reddit offers auto-generated usernames in format: `Adjective_Noun_1234`
- Examples: `Prestigious_Hat_8937`, `Brilliant_Lake_3847`
- Pattern: `^[A-Z][a-z]+_[A-Z][a-z]+_\d{3,5}$`
- **High confidence spam indicator** when combined with other signals

#### Word+Word+Numbers (PascalCase)
Common in automated account creation.
- Examples: `BrightSky1847`, `HappyCat9283`
- Pattern: `^[A-Z][a-z]+[A-Z][a-z]+\d{2,4}$`
- **High confidence spam indicator**

#### Random Alphanumeric
Long strings of random characters, often from password generators.
- Examples: `aj83hdk92lsm`, `XkJ8mNpL2qRs`
- Pattern: `^[a-zA-Z0-9]{12,}$`
- **Medium-high confidence** - can also be legitimate privacy-conscious users

#### Low Vowel Ratio
Generated strings often have unnatural vowel distribution.
- Check: `vowels / letters < 0.15`
- **Medium confidence** - supporting signal only

### Extended Pattern Module

**File**: `redditrepostsleuth/core/services/spam/username_patterns.py`

```python
"""
Username Pattern Analysis Module

Detects suspicious username patterns commonly used by spam accounts.
"""
import re
from dataclasses import dataclass
from typing import Dict, List, Tuple


@dataclass
class UsernameAnalysis:
    """Results of username pattern analysis."""
    username: str
    is_suspicious: bool
    confidence: float  # 0.0 to 1.0
    matched_patterns: List[str]
    details: Dict[str, any]


# Pattern definitions with confidence weights
USERNAME_PATTERNS: List[Tuple[str, str, float]] = [
    # (name, regex, confidence_weight)
    ('reddit_autogenerated', r'^[A-Z][a-z]+_[A-Z][a-z]+_\d{3,5}$', 0.85),
    ('word_word_numbers', r'^[A-Z][a-z]+[A-Z][a-z]+\d{2,4}$', 0.75),
    ('adjective_noun_numbers', r'^[A-Z][a-z]+-[A-Z][a-z]+-\d{3,5}$', 0.80),
    ('random_alphanumeric_long', r'^[a-zA-Z0-9]{15,}$', 0.70),
    ('random_alphanumeric_medium', r'^[a-zA-Z0-9]{12,14}$', 0.50),
    ('lowercase_word_numbers', r'^[a-z]+\d{4,}$', 0.60),
    ('uppercase_start_numbers', r'^[A-Z]+\d{4,}$', 0.55),
]

# Common legitimate username patterns (reduce suspicion)
LEGITIMATE_PATTERNS: List[Tuple[str, str, float]] = [
    ('throwaway', r'^throwaway', -0.30),  # Throwaway accounts are usually legit
    ('alt_account', r'_alt$|Alt$', -0.20),
    ('year_suffix', r'(19|20)\d{2}$', -0.15),  # Birth year or join year
]

# Known spam username prefixes/suffixes
SPAM_INDICATORS: List[Tuple[str, str, float]] = [
    ('crypto_prefix', r'^(crypto|nft|web3|defi)', 0.40),
    ('promo_suffix', r'(promo|deals|offers|free)$', 0.50),
    ('repeated_chars', r'(.)\1{3,}', 0.30),  # aaaa or 1111
]


def analyze_username(username: str) -> UsernameAnalysis:
    """
    Comprehensive username analysis.

    Args:
        username: Reddit username to analyze

    Returns:
        UsernameAnalysis with suspicion score and matched patterns
    """
    matched_patterns = []
    total_confidence = 0.0
    details = {}

    # Check suspicious patterns
    for name, pattern, weight in USERNAME_PATTERNS:
        if re.match(pattern, username):
            matched_patterns.append(name)
            total_confidence += weight
            details[f'match_{name}'] = True

    # Check legitimate patterns (reduce suspicion)
    for name, pattern, weight in LEGITIMATE_PATTERNS:
        if re.search(pattern, username, re.IGNORECASE):
            matched_patterns.append(f'legitimate_{name}')
            total_confidence += weight  # Weight is negative
            details[f'legitimate_{name}'] = True

    # Check spam indicators
    for name, pattern, weight in SPAM_INDICATORS:
        if re.search(pattern, username, re.IGNORECASE):
            matched_patterns.append(f'indicator_{name}')
            total_confidence += weight
            details[f'indicator_{name}'] = True

    # Structural analysis
    details['length'] = len(username)
    details['digit_count'] = sum(1 for c in username if c.isdigit())
    details['digit_ratio'] = details['digit_count'] / len(username) if username else 0

    # High digit ratio is suspicious
    if details['digit_ratio'] > 0.4:
        total_confidence += 0.25
        matched_patterns.append('high_digit_ratio')

    # Vowel analysis
    vowels = sum(1 for c in username.lower() if c in 'aeiou')
    letters = sum(1 for c in username if c.isalpha())
    details['vowel_ratio'] = vowels / letters if letters > 0 else 0

    if letters > 5 and details['vowel_ratio'] < 0.12:
        total_confidence += 0.20
        matched_patterns.append('low_vowel_ratio')

    # Consecutive digits at end
    end_digits = re.search(r'\d+$', username)
    if end_digits:
        digit_len = len(end_digits.group())
        details['trailing_digits'] = digit_len
        if digit_len >= 4:
            total_confidence += 0.15
            matched_patterns.append('long_trailing_digits')

    # Normalize confidence to 0-1
    confidence = max(0.0, min(1.0, total_confidence))

    return UsernameAnalysis(
        username=username,
        is_suspicious=confidence >= 0.5,
        confidence=confidence,
        matched_patterns=matched_patterns,
        details=details,
    )


def batch_analyze_usernames(usernames: List[str]) -> Dict[str, UsernameAnalysis]:
    """
    Analyze multiple usernames.

    Args:
        usernames: List of Reddit usernames

    Returns:
        Dict mapping username to analysis result
    """
    return {
        username: analyze_username(username)
        for username in usernames
    }
```

---

## 3.5. Error Handling Specifications

All Phase 1 operations must handle errors gracefully without blocking the ingest or main bot operations.

### Retry Strategy

| Scenario | Retry Count | Backoff | Max Duration |
|----------|-------------|---------|--------------|
| Database connection error | 3 | exponential (1s, 2s, 4s) | 10 seconds |
| Missing required table | 0 | N/A | Fail fast |
| Query timeout | 2 | linear (5s, 10s) | 20 seconds |
| Out of memory | 0 | N/A | Fail fast, alert ops |

### Logging Requirements

Every error must log:
1. Error type and message
2. Username being analyzed (for debugging)
3. Stack trace (for critical errors)
4. Retry attempt number
5. Time elapsed

```python
log.error(
    f"Error extracting features for {username}: {e}",
    exc_info=True,  # Include full stack trace
    extra={
        'username': username,
        'phase': 'tier1_extraction',
        'retry_count': retry_count,
    }
)
```

### Dead Letter Queue Handling

For tasks that fail permanently:

```python
# In compute_user_spam_features_tier1 task
try:
    # extraction logic
except Exception as e:
    log.error(f"Permanent failure for {username}: {e}")
    # Send to dead letter queue for manual review
    send_to_dlq(
        task_name='compute_user_spam_features_tier1',
        args=[username],
        reason=str(e),
    )
    raise  # Let Celery handle the failure
```

### Connection Failures

Gracefully degrade when database is temporarily unavailable:

```python
def extract_tier1_features(self, username: str) -> Optional[Tier1Features]:
    """Extract Tier 1 features with connection retry."""
    for attempt in range(1, 4):  # 3 attempts
        try:
            with self.uowm.start() as uow:
                return self._do_extraction(uow, username)
        except DatabaseError as e:
            if attempt < 3:
                wait_time = 2 ** attempt  # 2s, 4s
                log.warning(f"DB error on attempt {attempt}, retrying in {wait_time}s: {e}")
                time.sleep(wait_time)
            else:
                log.error(f"Failed after 3 attempts: {e}")
                return None  # Return None, not raise
```

### Monitoring for Errors

Define metrics and alerts:

```python
# Prometheus metrics
error_counter = Counter(
    'spam_detection_errors_total',
    'Total errors in spam detection',
    ['error_type', 'phase']
)

# In error handlers
error_counter.labels(error_type='database_error', phase='tier1').inc()
error_counter.labels(error_type='timeout_error', phase='tier1').inc()
```

---

## 4. Celery Tasks

### File: `redditrepostsleuth/core/celery/tasks/spam_detection_tasks.py`

```python
"""
Celery tasks for spam detection.

These tasks handle background spam detection processing.
"""
import logging
from datetime import datetime
from typing import Optional

from celery import shared_task

from redditrepostsleuth.core.celery.basetasks import SqlAlchemyTask
from redditrepostsleuth.core.db.databasemodels import UserSpamFeatures
from redditrepostsleuth.core.services.spam.spam_feature_extractor import SpamFeatureExtractor

log = logging.getLogger(__name__)


@shared_task(bind=True, base=SqlAlchemyTask, queue='spam_detection')
def compute_user_spam_features_tier1(self, username: str) -> Optional[dict]:
    """
    Compute and store Tier 1 spam features for a user.

    Tier 1 features require no Reddit API calls - all data comes from
    existing database tables.

    Args:
        username: Reddit username to analyze

    Returns:
        Dict with computed features or None if insufficient data
    """
    log.info(f"Computing Tier 1 spam features for user: {username}")

    try:
        extractor = SpamFeatureExtractor(self.uowm)

        # Check if worth analyzing
        if not extractor.is_user_worth_analyzing(username):
            log.debug(f"User {username} has insufficient data for analysis")
            return None

        # Extract features
        features = extractor.extract_tier1_features(username)
        if not features:
            log.debug(f"No features extracted for user: {username}")
            return None

        # Store features
        with self.uowm.start() as uow:
            feature_record = UserSpamFeatures(
                username=username,
                computed_at=datetime.utcnow(),

                # Tier 1 features
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
                detected_platforms=features.detected_platforms,
                username_suspicious_pattern=features.username_suspicious_pattern,
                username_pattern_matches=features.username_pattern_matches,
                karma_farming_sub_posts=features.karma_farming_sub_posts,
                easy_karma_sub_posts=features.easy_karma_sub_posts,
            )
            uow.spam_features.add(feature_record)
            uow.commit()

        log.info(f"Stored Tier 1 features for user: {username}")
        return features.to_dict()

    except Exception as e:
        log.error(f"Error computing features for {username}: {e}", exc_info=True)
        raise


@shared_task(bind=True, base=SqlAlchemyTask, queue='spam_detection')
def batch_compute_spam_features(self, usernames: list) -> dict:
    """
    Compute Tier 1 features for multiple users.

    Args:
        usernames: List of Reddit usernames to analyze

    Returns:
        Dict with success/failure counts
    """
    log.info(f"Batch computing features for {len(usernames)} users")

    results = {
        'total': len(usernames),
        'success': 0,
        'skipped': 0,
        'failed': 0,
    }

    for username in usernames:
        try:
            result = compute_user_spam_features_tier1(username)
            if result:
                results['success'] += 1
            else:
                results['skipped'] += 1
        except Exception as e:
            log.error(f"Failed to compute features for {username}: {e}")
            results['failed'] += 1

    log.info(f"Batch complete: {results}")
    return results


@shared_task(bind=True, base=SqlAlchemyTask, queue='spam_detection')
def analyze_top_reposters(self, limit: int = 100, days: int = 30) -> dict:
    """
    Analyze spam features for top reposters.

    Retrieves users with most reposts in the time period and
    computes their spam features.

    Args:
        limit: Maximum users to analyze
        days: Look back period in days

    Returns:
        Dict with analysis results
    """
    log.info(f"Analyzing top {limit} reposters from past {days} days")

    with self.uowm.start() as uow:
        # Get top reposters from existing stats
        top_reposters = uow.stat_top_reposter.get_top_reposters(
            days=days,
            limit=limit
        )

    if not top_reposters:
        log.info("No top reposters found")
        return {'analyzed': 0}

    usernames = [r.author for r in top_reposters]

    # Filter out recently analyzed users
    extractor = SpamFeatureExtractor(self.uowm)
    with self.uowm.start() as uow:
        to_analyze = [
            u for u in usernames
            if not uow.spam_features.user_was_recently_analyzed(u, within_days=7)
        ]

    log.info(f"Found {len(to_analyze)} users needing analysis (of {len(usernames)} total)")

    if not to_analyze:
        return {'analyzed': 0, 'skipped': len(usernames)}

    # Compute features
    return batch_compute_spam_features(to_analyze)


@shared_task(bind=True, base=SqlAlchemyTask, queue='spam_detection')
def cleanup_old_feature_records(self, keep_per_user: int = 5) -> dict:
    """
    Clean up old feature records, keeping most recent per user.

    Args:
        keep_per_user: Number of records to keep per user

    Returns:
        Dict with cleanup results
    """
    log.info(f"Cleaning up old feature records, keeping {keep_per_user} per user")

    with self.uowm.start() as uow:
        # Get distinct usernames
        from sqlalchemy import distinct
        usernames = uow.session.query(
            distinct(UserSpamFeatures.username)
        ).all()

        total_deleted = 0
        for (username,) in usernames:
            deleted = uow.spam_features.delete_old_records(username, keep_per_user)
            total_deleted += deleted

        uow.commit()

    log.info(f"Deleted {total_deleted} old feature records")
    return {'deleted': total_deleted}
```

---

## 5. Repost Data Integration

### Required Repository Method

The feature extractor needs to query reposts by author. Add this method to the repost repository.

**File**: `redditrepostsleuth/core/db/repository/repost_repo.py`

**Important Note**: The `Repost` table has an `author` column indexed directly, so we no longer need to join through `Post`. This is much simpler and faster.

```python
def get_reposts_by_author(self, author: str, limit: int = 1000) -> List[Repost]:
    """
    Get all reposts posted by the specified author.

    Note: Uses Repost.author directly (no join needed - much faster).
    This queries where the REPOST was posted by the author.

    Args:
        author: Reddit username
        limit: Maximum reposts to return

    Returns:
        List of Repost records
    """
    return self.session.query(Repost).filter(
        Repost.author == author
    ).limit(limit).all()


def count_reposts_by_author(self, author: str) -> int:
    """
    Count reposts posted by the specified author.

    More efficient than fetching all records when only count is needed.
    Uses Repost.author directly (no join).

    Args:
        author: Reddit username

    Returns:
        Count of reposts
    """
    from sqlalchemy import func
    return self.session.query(func.count(Repost.id)).filter(
        Repost.author == author
    ).scalar() or 0
```

### Required Summons Repository Method

**File**: `redditrepostsleuth/core/db/repository/summonsrepository.py`

```python
def count_by_requestor(self, requestor: str) -> int:
    """
    Count summons where the post author is the requestor.

    Note: 'requestor' in summons context is who triggered the summons,
    but for spam detection we want posts where the author was checked.

    Args:
        requestor: Reddit username

    Returns:
        Count of summons
    """
    from sqlalchemy import func
    # Actually we need summons on posts by this author
    # Summons.post -> Post.author
    return self.session.query(func.count(Summons.id)).join(
        Post, Summons.post_id == Post.id
    ).filter(
        Post.author == requestor
    ).scalar() or 0
```

---

## 6. Testing Strategy

### Unit Tests

**File**: `tests/core/services/spam/test_spam_feature_extractor.py`

```python
"""Tests for SpamFeatureExtractor."""
import unittest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from redditrepostsleuth.core.services.spam.spam_feature_extractor import (
    SpamFeatureExtractor,
    Tier1Features,
)


class TestSpamFeatureExtractor(unittest.TestCase):

    def setUp(self):
        self.mock_uowm = MagicMock()
        self.extractor = SpamFeatureExtractor(self.mock_uowm)

    def test_check_username_pattern_reddit_autogenerated(self):
        """Test detection of Reddit auto-generated usernames."""
        result = self.extractor.check_username_pattern('Prestigious_Hat_8937')
        self.assertTrue(result['suspicious'])
        self.assertTrue(result['matches']['reddit_autogenerated'])

    def test_check_username_pattern_word_word_numbers(self):
        """Test detection of WordWordNumbers pattern."""
        result = self.extractor.check_username_pattern('BrightSky1847')
        self.assertTrue(result['suspicious'])
        self.assertTrue(result['matches']['word_word_numbers'])

    def test_check_username_pattern_normal_username(self):
        """Test that normal usernames are not flagged."""
        result = self.extractor.check_username_pattern('john_doe')
        self.assertFalse(result['suspicious'])

    def test_check_username_pattern_random_string(self):
        """Test detection of random alphanumeric strings."""
        result = self.extractor.check_username_pattern('aj83hdk92lsm74')
        self.assertTrue(result['suspicious'])
        self.assertTrue(result['matches']['random_alphanumeric'])

    def test_check_username_pattern_ends_with_4_digits(self):
        """Test detection of usernames ending in 4 digits."""
        result = self.extractor.check_username_pattern('someuser2847')
        self.assertTrue(result['matches']['ends_4_digits'])

    def test_extract_tier1_features_no_activity(self):
        """Test feature extraction when user has no activity."""
        mock_uow = MagicMock()
        mock_uow.author_activity.get_by_author.return_value = []
        self.mock_uowm.start.return_value.__enter__.return_value = mock_uow

        result = self.extractor.extract_tier1_features('unknownuser')
        self.assertIsNone(result)

    def test_extract_tier1_features_with_activity(self):
        """Test feature extraction with user activity data."""
        # Setup mock activity data
        mock_activity = [
            MagicMock(
                subreddit='pics',
                nsfw=False,
                has_adult_platform_link=False,
                has_short_link=False,
                detected_platform=None,
                created_at=datetime.utcnow() - timedelta(days=5),
            ),
            MagicMock(
                subreddit='funny',
                nsfw=False,
                has_adult_platform_link=False,
                has_short_link=False,
                detected_platform=None,
                created_at=datetime.utcnow() - timedelta(days=3),
            ),
            MagicMock(
                subreddit='pics',
                nsfw=True,
                has_adult_platform_link=True,
                has_short_link=True,
                detected_platform='onlyfans',
                created_at=datetime.utcnow(),
            ),
        ]

        mock_uow = MagicMock()
        mock_uow.author_activity.get_by_author.return_value = mock_activity
        mock_uow.repost.get_reposts_by_author.return_value = [MagicMock()]  # 1 repost
        mock_uow.summons.count_by_requestor.return_value = 2
        mock_uow.spam_subreddits.get_as_dict.return_value = {}

        self.mock_uowm.start.return_value.__enter__.return_value = mock_uow

        result = self.extractor.extract_tier1_features('testuser')

        self.assertIsNotNone(result)
        self.assertEqual(result.total_posts_indexed, 3)
        self.assertEqual(result.total_reposts_detected, 1)
        self.assertAlmostEqual(result.repost_ratio, 1/3)
        self.assertEqual(result.unique_subreddits_posted, 2)
        self.assertEqual(result.adult_platform_post_count, 1)
        self.assertEqual(len(result.detected_platforms), 1)
        self.assertIn('onlyfans', result.detected_platforms)


class TestUsernamePatterns(unittest.TestCase):
    """Test cases for various username patterns."""

    def setUp(self):
        self.mock_uowm = MagicMock()
        self.extractor = SpamFeatureExtractor(self.mock_uowm)

    def test_known_spam_patterns(self):
        """Test known spam username patterns are detected."""
        spam_usernames = [
            'Prestigious_Hat_8937',
            'BrightSky1847',
            'Happy-Cat-2847',
            'ak48djf92ksl83hd',
            'user12345678',
        ]
        for username in spam_usernames:
            result = self.extractor.check_username_pattern(username)
            self.assertTrue(
                result['suspicious'],
                f"Expected {username} to be flagged as suspicious"
            )

    def test_known_legitimate_patterns(self):
        """Test known legitimate patterns are not flagged."""
        legit_usernames = [
            'john_doe',
            'the_real_user',
            'MovieFan2023',
            'throwaway_account',
            'PM_ME_YOUR_CATS',
        ]
        for username in legit_usernames:
            result = self.extractor.check_username_pattern(username)
            # Note: Some may still match patterns but should have lower confidence
            # The important thing is major spam patterns don't match
            self.assertFalse(
                result['matches'].get('reddit_autogenerated', False),
                f"Legit username {username} should not match autogenerated"
            )
```

### Integration Tests

**File**: `tests/core/services/spam/test_spam_feature_integration.py`

```python
"""Integration tests for spam feature extraction."""
import unittest
from datetime import datetime, timedelta

# These tests require a test database
# Skip if not available


class TestSpamFeatureIntegration(unittest.TestCase):
    """Integration tests using test database."""

    @classmethod
    def setUpClass(cls):
        """Set up test database connection."""
        # Setup test DB connection
        pass

    def test_full_feature_extraction_flow(self):
        """Test complete feature extraction flow."""
        pass

    def test_spam_subreddit_categorization(self):
        """Test categorization of karma farm subreddits."""
        pass
```

---

## 7. Verification Checklist

### Pre-Implementation
- [ ] Phase 0 completed and verified
- [ ] All new repositories available via UoW
- [ ] author_activity_tracking table populated with test data

### Service Implementation
- [ ] SpamFeatureExtractor instantiates correctly
- [ ] check_username_pattern returns expected results for known patterns
- [ ] extract_tier1_features returns Tier1Features dataclass
- [ ] Spam subreddit caching works correctly

### Repository Methods
- [ ] repost_repo.get_reposts_by_author works
- [ ] repost_repo.count_reposts_by_author works
- [ ] summons_repo.count_by_requestor works

### Celery Tasks
- [ ] compute_user_spam_features_tier1 executes successfully
- [ ] Features are stored in user_spam_features table
- [ ] batch_compute_spam_features handles multiple users
- [ ] analyze_top_reposters queries correctly

### Performance
- [ ] Feature extraction completes in <1 second per user
- [ ] Batch processing handles 100 users without timeout
- [ ] Database queries use appropriate indexes

### Edge Cases
- [ ] User with no activity returns None gracefully
- [ ] User with only 1 post handled correctly
- [ ] Empty subreddit distribution handled
- [ ] Unicode usernames handled correctly

---

## Dependencies

### Python Packages
No new packages required for Phase 1.

### Services
- Phase 0 database schema
- Celery worker with `spam_detection` queue

---

## Estimated Effort

| Task | Estimate |
|------|----------|
| SpamFeatureExtractor service | 4 hours |
| Username pattern module | 2 hours |
| Celery tasks | 2 hours |
| Repost repo methods | 1 hour |
| Summons repo methods | 1 hour |
| Unit tests | 4 hours |
| Integration tests | 3 hours |
| Documentation | 2 hours |
| **Total** | ~19 hours |
