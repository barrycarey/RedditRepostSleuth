# Phase 2: Rule-Based Scoring Engine

## Overview
- **Duration**: Week 5-6
- **Dependencies**: Phase 1 (Feature extraction)
- **Goal**: Implement rule-based spam scoring using Tier 1 features

---

## Table of Contents
1. [Scoring Algorithm Design](#1-scoring-algorithm-design)
2. [SpamScorer Service](#2-spamscorer-service)
3. [Scoring Weights and Thresholds](#3-scoring-weights-and-thresholds)
4. [Risk Level Classification](#4-risk-level-classification)
5. [Celery Task Integration](#5-celery-task-integration)
6. [User Review Integration](#6-user-review-integration)
7. [Testing Strategy](#7-testing-strategy)
8. [Verification Checklist](#8-verification-checklist)

---

## 1. Scoring Algorithm Design

### Philosophy
The scoring system is designed to be:
1. **Conservative**: Minimize false positives at the cost of some false negatives
2. **Explainable**: Every score component has a clear reason
3. **Tunable**: Weights can be adjusted based on observed performance
4. **Additive**: Signals combine but cap at 1.0

### Signal Categories

| Category | Weight Range | Description |
|----------|--------------|-------------|
| **Repost Behavior** | 0.0 - 0.35 | Our most valuable signal |
| **Adult Platform Promotion** | 0.0 - 0.35 | OnlyFans/Fansly promo spam |
| **Username Patterns** | 0.0 - 0.15 | Auto-generated or bot-like names |
| **Posting Patterns** | 0.0 - 0.20 | High frequency, low diversity |
| **Karma Farming** | 0.0 - 0.30 | Participation in karma farm subs |
| **Supporting Signals** | 0.0 - 0.15 | Short links, NSFW ratio, etc. |

### Scoring Formula

```
final_score = min(1.0, Σ(signal_weight * signal_active))

Where each signal contributes:
- repost_score (0.0 - 0.35)
- adult_platform_score (0.0 - 0.35)
- username_score (0.0 - 0.15)
- posting_pattern_score (0.0 - 0.20)
- karma_farming_score (0.0 - 0.30)
- supporting_signals_score (0.0 - 0.15)
```

---

## 2. SpamScorer Service

### File: `redditrepostsleuth/core/services/spam/spam_scorer.py`

```python
"""
Spam Scoring Engine

Rule-based scoring system for spam detection.
Uses Tier 1 features (no API calls required).
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.core.services.spam.spam_feature_extractor import Tier1Features

log = logging.getLogger(__name__)


@dataclass
class ScoringResult:
    """Container for spam scoring results."""
    score: float  # 0.0 to 1.0
    confidence: float  # 0.0 to 1.0, based on data availability
    risk_level: str  # LOW, MEDIUM, HIGH, CRITICAL
    reasons: List[str] = field(default_factory=list)
    component_scores: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            'score': self.score,
            'confidence': self.confidence,
            'risk_level': self.risk_level,
            'reasons': self.reasons,
            'component_scores': self.component_scores,
        }


@dataclass
class ScoringConfig:
    """Configuration for scoring thresholds and weights."""

    # Repost behavior thresholds
    repost_ratio_critical: float = 0.70
    repost_ratio_high: float = 0.50
    repost_ratio_medium: float = 0.30

    # Repost behavior weights
    repost_weight_critical: float = 0.35
    repost_weight_high: float = 0.25
    repost_weight_medium: float = 0.15

    # Adult platform thresholds
    adult_ratio_critical: float = 0.50
    adult_ratio_high: float = 0.20
    adult_ratio_low: float = 0.01  # Any detection

    # Adult platform weights
    adult_weight_critical: float = 0.35
    adult_weight_high: float = 0.25
    adult_weight_low: float = 0.10

    # Posting pattern thresholds
    posts_per_day_critical: float = 15.0
    posts_per_day_high: float = 10.0
    posts_per_day_elevated: float = 5.0

    # Posting pattern weights
    posting_weight_critical: float = 0.20
    posting_weight_high: float = 0.15
    posting_weight_elevated: float = 0.08

    # Subreddit diversity thresholds
    low_diversity_threshold: int = 3  # Less than this is suspicious
    min_posts_for_diversity: int = 20  # Need this many posts to judge

    # Username pattern weight
    username_pattern_weight: float = 0.12

    # Karma farming weights
    karma_farm_weight_per_post: float = 0.05
    karma_farm_weight_max: float = 0.30

    # Short link weight
    short_link_weight: float = 0.08

    # NSFW + adult platform combo weight
    nsfw_adult_combo_weight: float = 0.15

    # Risk level thresholds
    risk_critical_threshold: float = 0.80
    risk_high_threshold: float = 0.60
    risk_medium_threshold: float = 0.30


class SpamScorer:
    """
    Rule-based spam scoring engine.

    Calculates spam scores from Tier 1 features using configurable rules.
    """

    def __init__(
        self,
        uowm: UnitOfWorkManager,
        config: Optional[ScoringConfig] = None
    ):
        """
        Initialize the spam scorer.

        Args:
            uowm: Unit of Work Manager for database access
            config: Optional scoring configuration (uses defaults if None)
        """
        self.uowm = uowm
        self.config = config or ScoringConfig()
        self._spam_subs_cache: Optional[Dict[str, Tuple[str, float]]] = None

    def _load_spam_subs(self) -> Dict[str, Tuple[str, float]]:
        """Load spam subreddit list with caching."""
        if self._spam_subs_cache is None:
            with self.uowm.start() as uow:
                self._spam_subs_cache = uow.spam_subreddits.get_as_dict()
        return self._spam_subs_cache

    def score_user(self, features: Tier1Features) -> ScoringResult:
        """
        Calculate spam score from Tier 1 features.

        Args:
            features: Extracted Tier 1 features for a user

        Returns:
            ScoringResult with score, confidence, risk level, and reasons
        """
        score = 0.0
        reasons = []
        component_scores = {}

        # =====================================================================
        # SIGNAL 1: Repost Behavior (our most valuable signal!)
        # =====================================================================
        repost_score = self._score_repost_behavior(features)
        score += repost_score['score']
        component_scores['repost_behavior'] = repost_score['score']
        if repost_score['reason']:
            reasons.append(repost_score['reason'])

        # =====================================================================
        # SIGNAL 2: Adult Platform Promotion
        # =====================================================================
        adult_score = self._score_adult_platform(features)
        score += adult_score['score']
        component_scores['adult_platform'] = adult_score['score']
        if adult_score['reason']:
            reasons.append(adult_score['reason'])

        # =====================================================================
        # SIGNAL 3: Posting Patterns (frequency, diversity)
        # =====================================================================
        posting_score = self._score_posting_patterns(features)
        score += posting_score['score']
        component_scores['posting_patterns'] = posting_score['score']
        reasons.extend(posting_score['reasons'])

        # =====================================================================
        # SIGNAL 4: Username Pattern
        # =====================================================================
        username_score = self._score_username_pattern(features)
        score += username_score['score']
        component_scores['username_pattern'] = username_score['score']
        if username_score['reason']:
            reasons.append(username_score['reason'])

        # =====================================================================
        # SIGNAL 5: Karma Farming Subreddit Participation
        # =====================================================================
        karma_score = self._score_karma_farming(features)
        score += karma_score['score']
        component_scores['karma_farming'] = karma_score['score']
        if karma_score['reason']:
            reasons.append(karma_score['reason'])

        # =====================================================================
        # SIGNAL 6: Supporting Signals (short links, NSFW combo)
        # =====================================================================
        support_score = self._score_supporting_signals(features)
        score += support_score['score']
        component_scores['supporting_signals'] = support_score['score']
        reasons.extend(support_score['reasons'])

        # Cap at 1.0
        final_score = min(1.0, score)

        # Calculate confidence based on data availability
        confidence = self._calculate_confidence(features)

        # Determine risk level
        risk_level = self._classify_risk(final_score)

        return ScoringResult(
            score=round(final_score, 3),
            confidence=round(confidence, 2),
            risk_level=risk_level,
            reasons=reasons,
            component_scores={k: round(v, 3) for k, v in component_scores.items()},
        )

    def _score_repost_behavior(self, features: Tier1Features) -> dict:
        """Score based on repost ratio."""
        cfg = self.config
        ratio = features.repost_ratio

        if ratio >= cfg.repost_ratio_critical:
            return {
                'score': cfg.repost_weight_critical,
                'reason': f"Critical repost ratio: {ratio:.1%} of posts are reposts"
            }
        elif ratio >= cfg.repost_ratio_high:
            return {
                'score': cfg.repost_weight_high,
                'reason': f"High repost ratio: {ratio:.1%} of posts are reposts"
            }
        elif ratio >= cfg.repost_ratio_medium:
            return {
                'score': cfg.repost_weight_medium,
                'reason': f"Elevated repost ratio: {ratio:.1%}"
            }

        return {'score': 0.0, 'reason': None}

    def _score_adult_platform(self, features: Tier1Features) -> dict:
        """Score based on adult platform link detection."""
        cfg = self.config
        ratio = features.adult_platform_ratio
        platforms = features.detected_platforms

        if ratio >= cfg.adult_ratio_critical:
            platform_str = ', '.join(platforms) if platforms else 'unknown'
            return {
                'score': cfg.adult_weight_critical,
                'reason': f"High adult platform promotion: {ratio:.1%} ({platform_str})"
            }
        elif ratio >= cfg.adult_ratio_high:
            platform_str = ', '.join(platforms) if platforms else 'unknown'
            return {
                'score': cfg.adult_weight_high,
                'reason': f"Adult platform links detected: {ratio:.1%} ({platform_str})"
            }
        elif features.adult_platform_post_count > 0:
            return {
                'score': cfg.adult_weight_low,
                'reason': f"Adult platform links found: {features.adult_platform_post_count} posts"
            }

        return {'score': 0.0, 'reason': None}

    def _score_posting_patterns(self, features: Tier1Features) -> dict:
        """Score based on posting frequency and diversity."""
        cfg = self.config
        score = 0.0
        reasons = []

        # Posting frequency
        ppd = features.posts_per_day_avg
        if ppd >= cfg.posts_per_day_critical:
            score += cfg.posting_weight_critical
            reasons.append(f"Very high posting frequency: {ppd:.1f} posts/day")
        elif ppd >= cfg.posts_per_day_high:
            score += cfg.posting_weight_high
            reasons.append(f"High posting frequency: {ppd:.1f} posts/day")
        elif ppd >= cfg.posts_per_day_elevated:
            score += cfg.posting_weight_elevated
            reasons.append(f"Elevated posting frequency: {ppd:.1f} posts/day")

        # Subreddit diversity (only meaningful with enough posts)
        if features.total_posts_indexed >= cfg.min_posts_for_diversity:
            if features.unique_subreddits_posted < cfg.low_diversity_threshold:
                score += 0.12
                reasons.append(
                    f"Low subreddit diversity: {features.unique_subreddits_posted} subs "
                    f"for {features.total_posts_indexed} posts"
                )

        return {'score': score, 'reasons': reasons}

    def _score_username_pattern(self, features: Tier1Features) -> dict:
        """Score based on suspicious username patterns."""
        if features.username_suspicious_pattern:
            # Get most significant matched pattern
            matches = features.username_pattern_matches
            if matches.get('reddit_autogenerated'):
                pattern_desc = "Reddit auto-generated format"
            elif matches.get('word_word_numbers'):
                pattern_desc = "WordWordNumbers format"
            elif matches.get('random_alphanumeric'):
                pattern_desc = "Random alphanumeric string"
            else:
                pattern_desc = "Suspicious pattern"

            return {
                'score': self.config.username_pattern_weight,
                'reason': f"Suspicious username pattern: {pattern_desc}"
            }

        return {'score': 0.0, 'reason': None}

    def _score_karma_farming(self, features: Tier1Features) -> dict:
        """Score based on karma farming subreddit participation."""
        cfg = self.config
        karma_posts = features.karma_farming_sub_posts

        if karma_posts > 0:
            # Scale score by number of karma farm posts, capped
            score = min(
                cfg.karma_farm_weight_max,
                karma_posts * cfg.karma_farm_weight_per_post
            )
            return {
                'score': score,
                'reason': f"Karma farming subreddit posts: {karma_posts}"
            }

        return {'score': 0.0, 'reason': None}

    def _score_supporting_signals(self, features: Tier1Features) -> dict:
        """Score supporting signals like short links and NSFW combos."""
        cfg = self.config
        score = 0.0
        reasons = []

        # Short/promo links
        if features.short_link_ratio > 0.3:
            score += cfg.short_link_weight
            reasons.append(f"High promo link ratio: {features.short_link_ratio:.1%}")
        elif features.short_link_post_count > 2:
            score += cfg.short_link_weight * 0.6
            reasons.append(f"Multiple promo short links: {features.short_link_post_count}")

        # NSFW + adult platform combination (strong indicator)
        if features.nsfw_post_ratio > 0.5 and features.adult_platform_ratio > 0.1:
            score += cfg.nsfw_adult_combo_weight
            reasons.append("NSFW content + adult platform promotion pattern")

        return {'score': score, 'reasons': reasons}

    def _calculate_confidence(self, features: Tier1Features) -> float:
        """
        Calculate confidence score based on data availability.

        More data = higher confidence in the score.
        """
        posts = features.total_posts_indexed

        # Confidence tiers
        if posts >= 100:
            base_confidence = 0.95
        elif posts >= 50:
            base_confidence = 0.85
        elif posts >= 20:
            base_confidence = 0.70
        elif posts >= 10:
            base_confidence = 0.55
        elif posts >= 5:
            base_confidence = 0.40
        else:
            base_confidence = 0.25

        # Boost confidence if we have repost data
        if features.total_reposts_detected > 0:
            base_confidence = min(0.98, base_confidence + 0.05)

        return base_confidence

    def _classify_risk(self, score: float) -> str:
        """Classify score into risk level."""
        cfg = self.config

        if score >= cfg.risk_critical_threshold:
            return 'CRITICAL'
        elif score >= cfg.risk_high_threshold:
            return 'HIGH'
        elif score >= cfg.risk_medium_threshold:
            return 'MEDIUM'
        else:
            return 'LOW'

    def score_from_username(self, username: str) -> Optional[ScoringResult]:
        """
        Convenience method to extract features and score a user.

        Args:
            username: Reddit username

        Returns:
            ScoringResult or None if user has insufficient data
        """
        from redditrepostsleuth.core.services.spam.spam_feature_extractor import (
            SpamFeatureExtractor
        )

        extractor = SpamFeatureExtractor(self.uowm)
        features = extractor.extract_tier1_features(username)

        if not features:
            return None

        return self.score_user(features)


class SpamScorerWithTier2:
    """
    Extended scorer that incorporates Tier 2 (API-sourced) features.

    This is used after Tier 2 enrichment to produce a more accurate score.
    """

    def __init__(self, uowm: UnitOfWorkManager, config: Optional[ScoringConfig] = None):
        self.uowm = uowm
        self.config = config or ScoringConfig()
        self.base_scorer = SpamScorer(uowm, config)

    def score_with_tier2(
        self,
        tier1_features: Tier1Features,
        tier2_features: dict
    ) -> ScoringResult:
        """
        Score user using both Tier 1 and Tier 2 features.

        Args:
            tier1_features: Extracted Tier 1 features
            tier2_features: Dict of Tier 2 features from Reddit API

        Returns:
            Enhanced ScoringResult
        """
        # Start with base Tier 1 score
        result = self.base_scorer.score_user(tier1_features)

        # Enhance with Tier 2 signals
        tier2_adjustments = self._score_tier2_signals(tier2_features)

        # Combine scores
        combined_score = min(1.0, result.score + tier2_adjustments['score'])
        result.score = round(combined_score, 3)
        result.reasons.extend(tier2_adjustments['reasons'])
        result.component_scores['tier2_signals'] = tier2_adjustments['score']

        # Boost confidence with Tier 2 data
        result.confidence = min(0.98, result.confidence + 0.10)

        # Reclassify risk
        result.risk_level = self.base_scorer._classify_risk(combined_score)

        return result

    def _score_tier2_signals(self, tier2: dict) -> dict:
        """Score Tier 2 (API-sourced) signals."""
        score = 0.0
        reasons = []

        # Account suspended = confirmed spam
        if tier2.get('account_suspended'):
            score += 0.50
            reasons.append("Account suspended by Reddit (confirmed spam)")

        # Very new account with high activity
        age_days = tier2.get('account_age_days', 365)
        if age_days < 30:
            score += 0.15
            reasons.append(f"Very new account: {age_days} days old")
        elif age_days < 90:
            score += 0.08
            reasons.append(f"New account: {age_days} days old")

        # Low karma ratio (karma much lower than expected for activity)
        karma = tier2.get('total_karma', 0)
        karma_per_day = tier2.get('karma_per_day', 0)

        if age_days > 30 and karma < 100:
            score += 0.10
            reasons.append(f"Very low karma for account age: {karma}")
        elif karma_per_day < 0.5 and age_days > 90:
            score += 0.05
            reasons.append(f"Low karma accumulation rate: {karma_per_day:.1f}/day")

        # No verified email (suspicious for promotional accounts)
        if not tier2.get('has_verified_email', True):
            score += 0.05
            reasons.append("No verified email")

        # Default avatar (low effort account)
        if not tier2.get('has_custom_avatar', True):
            score += 0.03
            reasons.append("Default avatar (no customization)")

        return {'score': score, 'reasons': reasons}
```

---

## 3. Scoring Weights and Thresholds

### Default Weight Configuration

| Signal | Threshold | Weight | Rationale |
|--------|-----------|--------|-----------|
| **Repost ratio ≥70%** | Critical | 0.35 | Most reliable signal - we have unique data |
| **Repost ratio ≥50%** | High | 0.25 | Strong indicator |
| **Repost ratio ≥30%** | Medium | 0.15 | Elevated but not conclusive |
| **Adult platform ratio ≥50%** | Critical | 0.35 | Clear promotional intent |
| **Adult platform ratio ≥20%** | High | 0.25 | Significant promotion |
| **Any adult platform link** | Low | 0.10 | Supporting signal |
| **Posts/day ≥15** | Critical | 0.20 | Bot-like activity |
| **Posts/day ≥10** | High | 0.15 | High volume |
| **Posts/day ≥5** | Elevated | 0.08 | Above average |
| **Suspicious username** | - | 0.12 | Supporting signal |
| **Karma farm posts** | Per post | 0.05 | Up to 0.30 max |
| **Short link ratio >30%** | - | 0.08 | Promo behavior |
| **NSFW + adult combo** | - | 0.15 | Strong combined signal |

### Tuning Guidelines

When adjusting weights:

1. **Increase repost weights** if false negative rate is too high among known spammers
2. **Decrease username weights** if false positives occur on legitimate users with auto-generated names
3. **Adjust adult platform threshold** based on subreddit context (lower for SFW subs)
4. **Monitor karma farm list** and update as new subreddits emerge

---

## 4. Risk Level Classification

### Risk Levels

| Level | Score Range | Interpretation | Recommended Action |
|-------|-------------|----------------|-------------------|
| **CRITICAL** | ≥0.80 | Almost certainly spam | Auto-action (if enabled) |
| **HIGH** | 0.60-0.79 | Very likely spam | Priority manual review |
| **MEDIUM** | 0.30-0.59 | Possibly spam | Queue for review |
| **LOW** | <0.30 | Likely legitimate | No action needed |

### Confidence Levels

| Posts Indexed | Confidence | Interpretation |
|---------------|------------|----------------|
| ≥100 | 0.95 | Very confident |
| 50-99 | 0.85 | Confident |
| 20-49 | 0.70 | Moderately confident |
| 10-19 | 0.55 | Somewhat confident |
| 5-9 | 0.40 | Low confidence |
| <5 | 0.25 | Very low confidence |

---

## 4.5. Redis-Based Shared Caching

To support cross-worker cache invalidation and prevent race conditions, implement Redis for shared caching rather than in-memory caches.

### Redis Cache Implementation

**File**: `redditrepostsleuth/core/services/spam/spam_cache.py`

```python
"""
Shared spam detection cache using Redis.

Enables cross-worker cache invalidation and distributed caching.
"""
import json
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

import redis

log = logging.getLogger(__name__)


class SpamDetectionCache:
    """Redis-based cache for spam detection results and feature data."""

    def __init__(self, redis_client: redis.Redis, ttl_seconds: int = 3600):
        """
        Initialize cache.

        Args:
            redis_client: Redis client instance
            ttl_seconds: Default TTL (1 hour for user spam features)
        """
        self.redis = redis_client
        self.ttl = ttl_seconds
        self.version = 1  # Increment to invalidate all cached data

    def get_user_features(self, username: str) -> Optional[Dict[str, Any]]:
        """
        Get cached spam features for a user.

        Cache key format: spam:features:v{version}:{username}

        Args:
            username: Reddit username

        Returns:
            Cached features dict or None if not found or expired
        """
        key = f"spam:features:v{self.version}:{username.lower()}"
        try:
            cached = self.redis.get(key)
            if cached:
                log.debug(f"Cache hit for {username}")
                return json.loads(cached)
        except Exception as e:
            log.warning(f"Cache read error: {e}")
        return None

    def set_user_features(
        self,
        username: str,
        features: Dict[str, Any],
        ttl_seconds: Optional[int] = None
    ) -> bool:
        """
        Cache spam features for a user.

        Args:
            username: Reddit username
            features: Feature dict to cache
            ttl_seconds: Custom TTL (uses default if None)

        Returns:
            True if successful
        """
        key = f"spam:features:v{self.version}:{username.lower()}"
        ttl = ttl_seconds or self.ttl

        try:
            self.redis.setex(
                key,
                ttl,
                json.dumps(features, default=str)  # Handle datetime
            )
            log.debug(f"Cached features for {username}")
            return True
        except Exception as e:
            log.warning(f"Cache write error: {e}")
            return False

    def get_user_score(self, username: str) -> Optional[Dict[str, Any]]:
        """
        Get cached spam score result for a user.

        Cache key format: spam:score:v{version}:{username}

        Args:
            username: Reddit username

        Returns:
            Cached score dict or None
        """
        key = f"spam:score:v{self.version}:{username.lower()}"
        try:
            cached = self.redis.get(key)
            if cached:
                return json.loads(cached)
        except Exception as e:
            log.warning(f"Cache read error: {e}")
        return None

    def set_user_score(
        self,
        username: str,
        score_result: Dict[str, Any],
        ttl_seconds: Optional[int] = None
    ) -> bool:
        """
        Cache spam score for a user.

        Args:
            username: Reddit username
            score_result: Score result dict
            ttl_seconds: Custom TTL

        Returns:
            True if successful
        """
        key = f"spam:score:v{self.version}:{username.lower()}"
        ttl = ttl_seconds or self.ttl

        try:
            self.redis.setex(
                key,
                ttl,
                json.dumps(score_result, default=str)
            )
            return True
        except Exception as e:
            log.warning(f"Cache write error: {e}")
            return False

    def invalidate_user(self, username: str) -> bool:
        """
        Invalidate all cached data for a user.

        Useful when user data changes (score threshold updated, etc).

        Args:
            username: Reddit username

        Returns:
            True if successful
        """
        try:
            # Delete both features and score caches
            self.redis.delete(
                f"spam:features:v{self.version}:{username.lower()}",
                f"spam:score:v{self.version}:{username.lower()}"
            )
            log.debug(f"Invalidated cache for {username}")
            return True
        except Exception as e:
            log.warning(f"Cache invalidation error: {e}")
            return False

    def invalidate_all(self) -> bool:
        """
        Invalidate all spam detection cached data.

        Call this when scoring weights are updated or model changes.
        Incrementing version is preferable to clearing Redis.

        Returns:
            True if successful
        """
        try:
            log.info("Incrementing cache version to invalidate all data")
            self.version += 1
            return True
        except Exception as e:
            log.warning(f"Cache invalidation error: {e}")
            return False

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics (for monitoring)."""
        try:
            info = self.redis.info('stats')
            return {
                'total_connections_received': info.get('total_connections_received'),
                'total_commands_processed': info.get('total_commands_processed'),
                'version': self.version,
            }
        except Exception as e:
            log.warning(f"Stats error: {e}")
            return {}
```

### Integration with SpamScorer

```python
# In SpamScorer.__init__
def __init__(self, uowm: UnitOfWorkManager, cache: Optional[SpamDetectionCache] = None):
    self.cache = cache
    self.uowm = uowm

# In score_user method
def score_user(self, features: Tier1Features, username: str) -> ScoringResult:
    """Score user, using cache if available."""
    if self.cache:
        cached = self.cache.get_user_score(username)
        if cached:
            log.debug(f"Using cached score for {username}")
            return ScoringResult(**cached)

    # Compute score
    result = self._compute_score(features)

    # Store in cache
    if self.cache:
        self.cache.set_user_score(username, result.to_dict())

    return result
```

### Cache Versioning Strategy

| Scenario | Action | Impact |
|----------|--------|--------|
| Scoring weight change | Increment `version` | All cached scores invalidated |
| Threshold adjustment | Increment `version` | Re-scoring required |
| Bug fix in extraction | Increment `version` | All features re-extracted |
| Daily operations | No change | Cache stable across workers |

### Monitoring Cache Health

```python
# Add Prometheus metrics
cache_hit_rate = Gauge('spam_detection_cache_hit_rate', 'Cache hit percentage')
cache_size = Gauge('spam_detection_cache_size', 'Approximate cached items')
cache_evictions = Counter('spam_detection_cache_evictions', 'Items evicted from cache')

# Sample every minute
if counter % 60 == 0:
    stats = cache.get_stats()
    cache_size.set(redis_client.dbsize())
```

---

## 5. Celery Task Integration

### File: `redditrepostsleuth/core/celery/tasks/spam_detection_tasks.py`

Add these tasks to the existing file from Phase 1:

```python
from redditrepostsleuth.core.services.spam.spam_scorer import SpamScorer, ScoringResult


@shared_task(bind=True, base=SqlAlchemyTask, queue='spam_detection')
def score_user_spam(self, username: str) -> Optional[dict]:
    """
    Score a user for spam likelihood.

    This task extracts Tier 1 features and calculates a spam score.
    Results are stored in user_spam_features table.

    Args:
        username: Reddit username to score

    Returns:
        Dict with scoring results or None if insufficient data
    """
    log.info(f"Scoring user for spam: {username}")

    try:
        # Extract features
        extractor = SpamFeatureExtractor(self.uowm)
        features = extractor.extract_tier1_features(username)

        if not features:
            log.debug(f"Insufficient data to score user: {username}")
            return None

        # Score the user
        scorer = SpamScorer(self.uowm)
        result = scorer.score_user(features)

        # Store results
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

                # Scoring results
                rule_score=result.score,
                final_score=result.score,  # No ML score yet
                risk_level=result.risk_level,
                top_contributing_factors=result.reasons,
            )
            uow.spam_features.add(feature_record)
            uow.commit()

        log.info(
            f"Scored user {username}: {result.score:.2f} ({result.risk_level})"
        )
        return result.to_dict()

    except Exception as e:
        log.error(f"Error scoring user {username}: {e}", exc_info=True)
        raise


@shared_task(bind=True, base=SqlAlchemyTask, queue='spam_detection')
def score_and_flag_user(
    self,
    username: str,
    update_user_review: bool = True
) -> Optional[dict]:
    """
    Score a user and optionally update user_review table.

    This is the main entry point for spam detection, combining
    feature extraction, scoring, and flagging.

    Args:
        username: Reddit username to analyze
        update_user_review: Whether to update user_review table

    Returns:
        Dict with scoring results or None if insufficient data
    """
    # Score the user
    result_dict = score_user_spam(username)

    if not result_dict:
        return None

    # Update user_review if requested
    if update_user_review:
        with self.uowm.start() as uow:
            review = uow.user_review.get_by_username(username)

            if review:
                # Update existing review
                review.spam_score = result_dict['score']
                review.spam_score_confidence = result_dict['confidence']
                review.spam_score_updated_at = datetime.utcnow()
                review.risk_level = result_dict['risk_level']
            else:
                # Create new review entry
                from redditrepostsleuth.core.db.databasemodels import UserReview
                review = UserReview(
                    username=username,
                    spam_score=result_dict['score'],
                    spam_score_confidence=result_dict['confidence'],
                    spam_score_updated_at=datetime.utcnow(),
                    risk_level=result_dict['risk_level'],
                )
                uow.user_review.add(review)

            uow.commit()

        log.info(f"Updated user_review for {username}")

    return result_dict


@shared_task(bind=True, base=SqlAlchemyTask, queue='spam_detection')
def batch_score_users(self, usernames: List[str]) -> dict:
    """
    Score multiple users in batch.

    Args:
        usernames: List of Reddit usernames to score

    Returns:
        Dict with results summary
    """
    log.info(f"Batch scoring {len(usernames)} users")

    results = {
        'total': len(usernames),
        'scored': 0,
        'skipped': 0,
        'failed': 0,
        'high_risk': 0,
        'critical_risk': 0,
    }

    for username in usernames:
        try:
            result = score_and_flag_user(username, update_user_review=True)

            if result:
                results['scored'] += 1
                if result['risk_level'] == 'CRITICAL':
                    results['critical_risk'] += 1
                elif result['risk_level'] == 'HIGH':
                    results['high_risk'] += 1
            else:
                results['skipped'] += 1

        except Exception as e:
            log.error(f"Failed to score {username}: {e}")
            results['failed'] += 1

    log.info(f"Batch scoring complete: {results}")
    return results


@shared_task(bind=True, base=SqlAlchemyTask, queue='spam_detection')
def score_top_reposters(
    self,
    limit: int = 100,
    days: int = 30,
    min_reposts: int = 5
) -> dict:
    """
    Score top reposters for spam detection.

    Retrieves users with most reposts and scores them.

    Args:
        limit: Maximum users to analyze
        days: Look back period
        min_reposts: Minimum reposts to qualify

    Returns:
        Dict with results summary
    """
    log.info(f"Scoring top {limit} reposters from past {days} days")

    with self.uowm.start() as uow:
        top_reposters = uow.stat_top_reposter.get_top_reposters(
            days=days,
            limit=limit,
            min_reposts=min_reposts
        )

    if not top_reposters:
        return {'analyzed': 0}

    # Filter out recently analyzed
    usernames_to_score = []
    with self.uowm.start() as uow:
        for reposter in top_reposters:
            if not uow.spam_features.user_was_recently_analyzed(
                reposter.author,
                within_days=7
            ):
                usernames_to_score.append(reposter.author)

    log.info(f"Found {len(usernames_to_score)} users needing scoring")

    return batch_score_users(usernames_to_score)
```

---

## 6. User Review Integration

### Updating user_review Table

The spam detection system updates the `user_review` table to flag users:

```python
# In user_review_repo.py, add these methods:

def get_high_risk_users(
    self,
    min_score: float = 0.6,
    limit: int = 100
) -> List[UserReview]:
    """Get users with high spam scores for review."""
    return self.session.query(UserReview).filter(
        UserReview.spam_score >= min_score
    ).order_by(
        desc(UserReview.spam_score)
    ).limit(limit).all()


def get_users_needing_review(self, limit: int = 100) -> List[UserReview]:
    """Get users flagged for review but not yet verified."""
    return self.session.query(UserReview).filter(
        UserReview.spam_score >= 0.6,
        UserReview.is_verified_spam == False,
        UserReview.is_verified_legit == False
    ).order_by(
        desc(UserReview.spam_score)
    ).limit(limit).all()


def mark_verified_spam(self, username: str) -> bool:
    """Mark a user as verified spam after manual review."""
    updated = self.session.query(UserReview).filter(
        UserReview.username == username
    ).update({
        'is_verified_spam': True,
        'is_verified_legit': False
    })
    return updated > 0


def mark_verified_legit(self, username: str) -> bool:
    """Mark a user as verified legitimate after manual review."""
    updated = self.session.query(UserReview).filter(
        UserReview.username == username
    ).update({
        'is_verified_spam': False,
        'is_verified_legit': True
    })
    return updated > 0
```

---

## 7. Testing Strategy

### Unit Tests

**File**: `tests/core/services/spam/test_spam_scorer.py`

```python
"""Tests for SpamScorer."""
import unittest
from datetime import datetime, timedelta
from unittest.mock import MagicMock

from redditrepostsleuth.core.services.spam.spam_feature_extractor import Tier1Features
from redditrepostsleuth.core.services.spam.spam_scorer import (
    SpamScorer,
    ScoringConfig,
    ScoringResult,
)


class TestSpamScorer(unittest.TestCase):

    def setUp(self):
        self.mock_uowm = MagicMock()
        self.scorer = SpamScorer(self.mock_uowm)

    def _make_features(self, **kwargs) -> Tier1Features:
        """Helper to create test features with defaults."""
        defaults = {
            'total_posts_indexed': 50,
            'total_reposts_detected': 0,
            'repost_ratio': 0.0,
            'unique_subreddits_posted': 10,
            'posts_per_day_avg': 2.0,
            'first_post_date': datetime.utcnow() - timedelta(days=30),
            'last_post_date': datetime.utcnow(),
            'nsfw_post_ratio': 0.0,
            'summons_received': 0,
            'adult_platform_post_count': 0,
            'adult_platform_ratio': 0.0,
            'short_link_post_count': 0,
            'short_link_ratio': 0.0,
            'detected_platforms': [],
            'username_suspicious_pattern': False,
            'username_pattern_matches': {},
            'subreddit_distribution': {},
            'karma_farming_sub_posts': 0,
            'easy_karma_sub_posts': 0,
        }
        defaults.update(kwargs)
        return Tier1Features(**defaults)

    def test_score_clean_user(self):
        """Test that clean user gets low score."""
        features = self._make_features()
        result = self.scorer.score_user(features)

        self.assertLess(result.score, 0.3)
        self.assertEqual(result.risk_level, 'LOW')

    def test_score_high_repost_ratio(self):
        """Test that high repost ratio triggers high score."""
        features = self._make_features(
            total_reposts_detected=40,
            repost_ratio=0.80
        )
        result = self.scorer.score_user(features)

        self.assertGreaterEqual(result.score, 0.35)
        self.assertIn('repost ratio', result.reasons[0].lower())

    def test_score_adult_platform_promotion(self):
        """Test that adult platform links trigger score."""
        features = self._make_features(
            adult_platform_post_count=30,
            adult_platform_ratio=0.60,
            detected_platforms=['onlyfans', 'fansly']
        )
        result = self.scorer.score_user(features)

        self.assertGreaterEqual(result.score, 0.35)
        self.assertTrue(any('adult platform' in r.lower() for r in result.reasons))

    def test_score_high_posting_frequency(self):
        """Test that high posting frequency triggers score."""
        features = self._make_features(
            posts_per_day_avg=20.0
        )
        result = self.scorer.score_user(features)

        self.assertGreater(result.score, 0.15)
        self.assertTrue(any('posting frequency' in r.lower() for r in result.reasons))

    def test_score_suspicious_username(self):
        """Test that suspicious username triggers score."""
        features = self._make_features(
            username_suspicious_pattern=True,
            username_pattern_matches={'reddit_autogenerated': True}
        )
        result = self.scorer.score_user(features)

        self.assertGreater(result.score, 0.1)
        self.assertTrue(any('username' in r.lower() for r in result.reasons))

    def test_score_karma_farming(self):
        """Test that karma farming posts trigger score."""
        features = self._make_features(
            karma_farming_sub_posts=10
        )
        result = self.scorer.score_user(features)

        self.assertGreater(result.score, 0.2)
        self.assertTrue(any('karma farming' in r.lower() for r in result.reasons))

    def test_score_combined_signals(self):
        """Test that combined signals produce high score."""
        features = self._make_features(
            total_reposts_detected=30,
            repost_ratio=0.60,
            posts_per_day_avg=12.0,
            username_suspicious_pattern=True,
            username_pattern_matches={'word_word_numbers': True},
            karma_farming_sub_posts=5,
        )
        result = self.scorer.score_user(features)

        self.assertGreaterEqual(result.score, 0.6)
        self.assertIn(result.risk_level, ['HIGH', 'CRITICAL'])

    def test_confidence_increases_with_more_data(self):
        """Test that confidence increases with more posts."""
        # Few posts
        features_low = self._make_features(total_posts_indexed=5)
        result_low = self.scorer.score_user(features_low)

        # Many posts
        features_high = self._make_features(total_posts_indexed=100)
        result_high = self.scorer.score_user(features_high)

        self.assertGreater(result_high.confidence, result_low.confidence)

    def test_risk_level_classification(self):
        """Test risk level classification boundaries."""
        # LOW
        features = self._make_features()
        result = self.scorer.score_user(features)
        self.assertEqual(result.risk_level, 'LOW')

        # Create features that push into CRITICAL
        features_critical = self._make_features(
            repost_ratio=0.80,
            adult_platform_ratio=0.60,
            posts_per_day_avg=15.0,
        )
        result_critical = self.scorer.score_user(features_critical)
        self.assertEqual(result_critical.risk_level, 'CRITICAL')

    def test_score_capped_at_one(self):
        """Test that score never exceeds 1.0."""
        # Create extreme spam features
        features = self._make_features(
            repost_ratio=0.90,
            adult_platform_ratio=0.70,
            posts_per_day_avg=25.0,
            username_suspicious_pattern=True,
            username_pattern_matches={'reddit_autogenerated': True},
            karma_farming_sub_posts=20,
            short_link_ratio=0.50,
            nsfw_post_ratio=0.80,
        )
        result = self.scorer.score_user(features)

        self.assertLessEqual(result.score, 1.0)

    def test_nsfw_adult_platform_combo(self):
        """Test that NSFW + adult platform combo adds extra weight."""
        features = self._make_features(
            nsfw_post_ratio=0.60,
            adult_platform_ratio=0.15,
        )
        result = self.scorer.score_user(features)

        self.assertTrue(any('nsfw' in r.lower() and 'adult' in r.lower() for r in result.reasons))


class TestScoringConfig(unittest.TestCase):
    """Test scoring configuration."""

    def test_custom_config(self):
        """Test that custom config overrides defaults."""
        config = ScoringConfig(
            repost_ratio_critical=0.90,
            repost_weight_critical=0.50,
        )

        self.assertEqual(config.repost_ratio_critical, 0.90)
        self.assertEqual(config.repost_weight_critical, 0.50)

    def test_default_config_reasonable(self):
        """Test that default config has reasonable values."""
        config = ScoringConfig()

        # Thresholds should be between 0 and 1
        self.assertTrue(0 < config.repost_ratio_critical <= 1)
        self.assertTrue(0 < config.risk_critical_threshold <= 1)

        # Weights should be positive but not excessive
        self.assertTrue(0 < config.repost_weight_critical <= 0.5)
```

### Integration Tests

**File**: `tests/core/services/spam/test_scoring_integration.py`

```python
"""Integration tests for spam scoring."""
import unittest


class TestScoringIntegration(unittest.TestCase):
    """Integration tests with real database."""

    def test_score_known_spam_account(self):
        """Test scoring a known spam account produces high score."""
        pass

    def test_score_known_legitimate_account(self):
        """Test scoring a known legitimate account produces low score."""
        pass

    def test_batch_scoring_performance(self):
        """Test batch scoring completes in reasonable time."""
        pass
```

---

## 8. Verification Checklist

### Pre-Implementation
- [ ] Phase 1 completed and verified
- [ ] Feature extraction working correctly
- [ ] user_spam_features table populated with test data

### Scorer Implementation
- [ ] SpamScorer instantiates correctly
- [ ] score_user returns valid ScoringResult
- [ ] All component scores calculated correctly
- [ ] Risk levels classified correctly
- [ ] Confidence calculated based on data availability

### Score Validation
- [ ] Known spam accounts score >0.6
- [ ] Known legitimate accounts score <0.3
- [ ] Score never exceeds 1.0
- [ ] Reasons are clear and accurate

### Celery Tasks
- [ ] score_user_spam executes successfully
- [ ] Results stored in user_spam_features
- [ ] user_review table updated correctly
- [ ] Batch scoring handles errors gracefully

### Performance
- [ ] Single user scoring <500ms
- [ ] Batch of 100 users <60 seconds
- [ ] No memory leaks in batch processing

---

## Dependencies

### Python Packages
No new packages required for Phase 2.

### Services
- Phase 1 feature extraction
- Celery worker with `spam_detection` queue

---

## Estimated Effort

| Task | Estimate |
|------|----------|
| SpamScorer service | 4 hours |
| Scoring algorithms | 3 hours |
| Celery tasks | 2 hours |
| User review integration | 2 hours |
| Unit tests | 4 hours |
| Integration tests | 3 hours |
| Tuning and validation | 4 hours |
| Documentation | 2 hours |
| **Total** | ~24 hours |
