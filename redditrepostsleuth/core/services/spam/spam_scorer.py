"""
Spam Scoring Engine

Rule-based scoring system for spam detection.
Uses Tier 1 features (no API calls required) with optional Tier 2 enhancement.
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
        """Convert to dictionary for JSON serialization."""
        return {
            'score': self.score,
            'confidence': self.confidence,
            'risk_level': self.risk_level,
            'reasons': self.reasons,
            'component_scores': self.component_scores,
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'ScoringResult':
        """Create from dictionary."""
        return cls(
            score=data['score'],
            confidence=data['confidence'],
            risk_level=data['risk_level'],
            reasons=data.get('reasons', []),
            component_scores=data.get('component_scores', {}),
        )


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
                self._spam_subs_cache = uow.spam_subreddit.get_as_dict()
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
            if isinstance(matches, dict):
                if matches.get('reddit_autogenerated'):
                    pattern_desc = "Reddit auto-generated format"
                elif matches.get('word_word_numbers'):
                    pattern_desc = "WordWordNumbers format"
                elif matches.get('random_alphanumeric'):
                    pattern_desc = "Random alphanumeric string"
                else:
                    pattern_desc = "Suspicious pattern"
            elif isinstance(matches, list) and len(matches) > 0:
                if 'reddit_autogenerated' in matches:
                    pattern_desc = "Reddit auto-generated format"
                elif 'word_word_numbers' in matches:
                    pattern_desc = "WordWordNumbers format"
                elif 'random_alphanumeric' in matches:
                    pattern_desc = "Random alphanumeric string"
                else:
                    pattern_desc = f"Suspicious pattern: {matches[0]}"
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

        # Adult links found in profile/comments (Tier 2 enrichment)
        if tier2.get('has_adult_profile_links'):
            score += 0.20
            reasons.append("Adult platform links in profile/comments")

        # Telegram links found (off-platform promo)
        if tier2.get('has_telegram_links'):
            score += 0.15
            reasons.append("Telegram links for off-platform communication")

        return {'score': score, 'reasons': reasons}
