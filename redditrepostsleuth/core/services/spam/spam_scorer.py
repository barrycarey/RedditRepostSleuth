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

    # Easy karma subreddit weights
    easy_karma_weight_per_post: float = 0.02
    easy_karma_weight_max: float = 0.15
    easy_karma_ratio_threshold: float = 0.50

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
        log.info('Starting spam scoring for user: %s', features.username)
        log.debug('Input features: posts=%d, reposts=%d, nsfw_ratio=%.2f, adult_ratio=%.2f',
                  features.total_posts_indexed, features.total_reposts_detected,
                  features.nsfw_post_ratio, features.adult_platform_ratio)

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
        log.debug('Signal 1 (repost_behavior): score=%.3f, reason=%s',
                  repost_score['score'], repost_score['reason'])

        # =====================================================================
        # SIGNAL 2: Adult Platform Promotion
        # =====================================================================
        adult_score = self._score_adult_platform(features)
        score += adult_score['score']
        component_scores['adult_platform'] = adult_score['score']
        if adult_score['reason']:
            reasons.append(adult_score['reason'])
        log.debug('Signal 2 (adult_platform): score=%.3f, reason=%s',
                  adult_score['score'], adult_score['reason'])

        # =====================================================================
        # SIGNAL 3: Posting Patterns (frequency, diversity)
        # =====================================================================
        posting_score = self._score_posting_patterns(features)
        score += posting_score['score']
        component_scores['posting_patterns'] = posting_score['score']
        reasons.extend(posting_score['reasons'])
        log.debug('Signal 3 (posting_patterns): score=%.3f, reasons=%s',
                  posting_score['score'], posting_score['reasons'])

        # =====================================================================
        # SIGNAL 4: Username Pattern
        # =====================================================================
        username_score = self._score_username_pattern(features)
        score += username_score['score']
        component_scores['username_pattern'] = username_score['score']
        if username_score['reason']:
            reasons.append(username_score['reason'])
        log.debug('Signal 4 (username_pattern): score=%.3f, reason=%s',
                  username_score['score'], username_score['reason'])

        # =====================================================================
        # SIGNAL 5: Karma Farming Subreddit Participation
        # =====================================================================
        karma_score = self._score_karma_farming(features)
        score += karma_score['score']
        component_scores['karma_farming'] = karma_score['score']
        if karma_score['reason']:
            reasons.append(karma_score['reason'])
        log.debug('Signal 5 (karma_farming): score=%.3f, reason=%s',
                  karma_score['score'], karma_score['reason'])

        # =====================================================================
        # SIGNAL 6: Supporting Signals (short links, NSFW combo)
        # =====================================================================
        support_score = self._score_supporting_signals(features)
        score += support_score['score']
        component_scores['supporting_signals'] = support_score['score']
        reasons.extend(support_score['reasons'])
        log.debug('Signal 6 (supporting_signals): score=%.3f, reasons=%s',
                  support_score['score'], support_score['reasons'])

        # Cap at 1.0
        final_score = min(1.0, score)
        log.debug('Raw score=%.3f, capped final_score=%.3f', score, final_score)

        # Calculate confidence based on data availability
        confidence = self._calculate_confidence(features)

        # Determine risk level
        risk_level = self._classify_risk(final_score)

        result = ScoringResult(
            score=round(final_score, 3),
            confidence=round(confidence, 2),
            risk_level=risk_level,
            reasons=reasons,
            component_scores={k: round(v, 3) for k, v in component_scores.items()},
        )

        log.info('Completed scoring for %s: score=%.3f, confidence=%.2f, risk=%s, reasons=%d',
                 features.username, result.score, result.confidence,
                 result.risk_level, len(result.reasons))

        return result

    def _score_repost_behavior(self, features: Tier1Features) -> dict:
        """Score based on repost ratio."""
        cfg = self.config
        ratio = features.repost_ratio

        log.debug('Evaluating repost behavior: ratio=%.3f (thresholds: critical=%.2f, high=%.2f, medium=%.2f)',
                  ratio, cfg.repost_ratio_critical, cfg.repost_ratio_high, cfg.repost_ratio_medium)

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

        log.debug('Evaluating adult platform: ratio=%.3f, platforms=%s, post_count=%d',
                  ratio, platforms, features.adult_platform_post_count)

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
        log.debug('Evaluating posting patterns: posts_per_day=%.2f (thresholds: critical=%.1f, high=%.1f, elevated=%.1f)',
                  ppd, cfg.posts_per_day_critical, cfg.posts_per_day_high, cfg.posts_per_day_elevated)

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
            log.debug('Evaluating subreddit diversity: unique_subs=%d, total_posts=%d, threshold=%d',
                      features.unique_subreddits_posted, features.total_posts_indexed, cfg.low_diversity_threshold)
            if features.unique_subreddits_posted < cfg.low_diversity_threshold:
                score += 0.12
                reasons.append(
                    f"Low subreddit diversity: {features.unique_subreddits_posted} subs "
                    f"for {features.total_posts_indexed} posts"
                )

        return {'score': score, 'reasons': reasons}

    def _score_username_pattern(self, features: Tier1Features) -> dict:
        """Score based on suspicious username patterns."""
        log.debug('Evaluating username pattern: suspicious=%s, matches=%s',
                  features.username_suspicious_pattern, features.username_pattern_matches)

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
        easy_posts = features.easy_karma_sub_posts

        log.debug('Evaluating karma farming: karma_farm_posts=%d, easy_karma_posts=%d',
                  karma_posts, easy_posts)

        score = 0.0
        reasons = []

        # Full weight for explicit karma farm subs (FreeKarma4You etc)
        if karma_posts > 0:
            karma_score = min(cfg.karma_farm_weight_max, karma_posts * cfg.karma_farm_weight_per_post)
            score += karma_score
            reasons.append(f"Karma farming subreddit posts: {karma_posts}")

        # Lower weight for easy karma subs, only if concentrated
        if easy_posts > 0 and features.total_posts_indexed > 0:
            easy_ratio = easy_posts / features.total_posts_indexed
            if easy_ratio > cfg.easy_karma_ratio_threshold:
                easy_score = min(cfg.easy_karma_weight_max, easy_posts * cfg.easy_karma_weight_per_post)
                score += easy_score
                reasons.append(f"Concentrated in easy karma subs: {easy_posts} posts ({easy_ratio:.0%})")

        if reasons:
            return {'score': score, 'reason': '; '.join(reasons)}
        return {'score': 0.0, 'reason': None}

    def _score_supporting_signals(self, features: Tier1Features) -> dict:
        """Score supporting signals like short links and NSFW combos."""
        cfg = self.config
        score = 0.0
        reasons = []

        log.debug('Evaluating supporting signals: short_link_ratio=%.3f, short_link_count=%d, '
                  'nsfw_ratio=%.3f, adult_ratio=%.3f',
                  features.short_link_ratio, features.short_link_post_count,
                  features.nsfw_post_ratio, features.adult_platform_ratio)

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

        log.debug('Calculated confidence: posts=%d, reposts=%d, confidence=%.2f',
                  posts, features.total_reposts_detected, base_confidence)

        return base_confidence

    def _classify_risk(self, score: float) -> str:
        """Classify score into risk level."""
        cfg = self.config

        if score >= cfg.risk_critical_threshold:
            risk = 'CRITICAL'
        elif score >= cfg.risk_high_threshold:
            risk = 'HIGH'
        elif score >= cfg.risk_medium_threshold:
            risk = 'MEDIUM'
        else:
            risk = 'LOW'

        log.debug('Classified risk: score=%.3f, thresholds=(critical=%.2f, high=%.2f, medium=%.2f) -> %s',
                  score, cfg.risk_critical_threshold, cfg.risk_high_threshold, cfg.risk_medium_threshold, risk)

        return risk

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

        log.info('Score from username called for: %s', username)

        extractor = SpamFeatureExtractor(self.uowm)
        features = extractor.extract_tier1_features(username)

        if not features:
            log.info('Cannot score %s: insufficient data for feature extraction', username)
            return None

        log.debug('Features extracted for %s, proceeding to score', username)
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
        log.info('Scoring with Tier 2 features for user: %s', tier1_features.username)
        log.debug('Tier 2 features: %s', tier2_features)

        # Start with base Tier 1 score
        result = self.base_scorer.score_user(tier1_features)
        log.debug('Base Tier 1 score: %.3f, risk=%s', result.score, result.risk_level)

        # Enhance with Tier 2 signals
        tier2_adjustments = self._score_tier2_signals(tier2_features)
        log.debug('Tier 2 adjustments: score=%.3f, reasons=%s',
                  tier2_adjustments['score'], tier2_adjustments['reasons'])

        # Combine scores
        combined_score = min(1.0, result.score + tier2_adjustments['score'])
        result.score = round(combined_score, 3)
        result.reasons.extend(tier2_adjustments['reasons'])
        result.component_scores['tier2_signals'] = tier2_adjustments['score']

        # Boost confidence with Tier 2 data
        old_confidence = result.confidence
        result.confidence = min(0.98, result.confidence + 0.10)
        log.debug('Confidence boosted: %.2f -> %.2f (Tier 2 data available)',
                  old_confidence, result.confidence)

        # Reclassify risk
        result.risk_level = self.base_scorer._classify_risk(combined_score)

        log.info('Tier 2 scoring complete for %s: score=%.3f (tier1=%.3f + tier2=%.3f), risk=%s',
                 tier1_features.username, combined_score,
                 combined_score - tier2_adjustments['score'], tier2_adjustments['score'],
                 result.risk_level)

        return result

    def _score_tier2_signals(self, tier2: dict) -> dict:
        """Score Tier 2 (API-sourced) signals."""
        score = 0.0
        reasons = []

        log.debug('Evaluating Tier 2 signals: suspended=%s, age_days=%s, karma=%s',
                  tier2.get('account_suspended'), tier2.get('account_age_days'),
                  tier2.get('total_karma'))

        # Account suspended = confirmed spam
        if tier2.get('account_suspended'):
            score += 0.50
            reasons.append("Account suspended by Reddit (confirmed spam)")
            log.debug('Signal: account suspended (+0.50)')

        # Very new account with high activity
        age_days = tier2.get('account_age_days', 365)
        if age_days < 30:
            score += 0.15
            reasons.append(f"Very new account: {age_days} days old")
            log.debug('Signal: very new account %d days (+0.15)', age_days)
        elif age_days < 90:
            score += 0.08
            reasons.append(f"New account: {age_days} days old")
            log.debug('Signal: new account %d days (+0.08)', age_days)

        # Low karma ratio (karma much lower than expected for activity)
        karma = tier2.get('total_karma', 0)
        karma_per_day = tier2.get('karma_per_day', 0)

        if age_days > 30 and karma < 100:
            score += 0.10
            reasons.append(f"Very low karma for account age: {karma}")
            log.debug('Signal: very low karma %d (+0.10)', karma)
        elif karma_per_day < 0.5 and age_days > 90:
            score += 0.05
            reasons.append(f"Low karma accumulation rate: {karma_per_day:.1f}/day")
            log.debug('Signal: low karma rate %.1f/day (+0.05)', karma_per_day)

        # No verified email (suspicious for promotional accounts)
        if not tier2.get('has_verified_email', True):
            score += 0.05
            reasons.append("No verified email")
            log.debug('Signal: no verified email (+0.05)')

        # Default avatar (low effort account)
        if not tier2.get('has_custom_avatar', True):
            score += 0.03
            reasons.append("Default avatar (no customization)")
            log.debug('Signal: default avatar (+0.03)')

        # Adult links found in profile/comments (Tier 2 enrichment)
        if tier2.get('has_adult_profile_links'):
            score += 0.20
            reasons.append("Adult platform links in profile/comments")
            log.debug('Signal: adult profile links (+0.20)')

        # Telegram links found (off-platform promo)
        if tier2.get('has_telegram_links'):
            score += 0.15
            reasons.append("Telegram links for off-platform communication")
            log.debug('Signal: telegram links (+0.15)')

        # Promotional links in posts (tiered by count)
        if tier2.get('has_promotional_post_links'):
            sources = tier2.get('profile_link_sources', {})
            promo_post_count = len(sources.get('promotional_posts', []))
            adult_post_count = len(sources.get('adult_posts', []))
            telegram_post_count = len(sources.get('telegram_posts', []))
            total_flagged_posts = promo_post_count + adult_post_count + telegram_post_count

            if total_flagged_posts >= 10:
                score += 0.18
                reasons.append(f"Many promotional links in posts ({total_flagged_posts} flagged posts)")
                log.debug('Signal: many promotional posts %d (+0.18)', total_flagged_posts)
            elif total_flagged_posts >= 5:
                score += 0.12
                reasons.append(f"Moderate promotional links in posts ({total_flagged_posts} flagged posts)")
                log.debug('Signal: moderate promotional posts %d (+0.12)', total_flagged_posts)
            else:
                score += 0.05
                reasons.append("Some promotional links in posts")
                log.debug('Signal: some promotional posts (+0.05)')

        # Cross-channel correlation: promotional activity in BOTH profile/comments AND posts
        has_profile_promo = tier2.get('has_adult_profile_links') or tier2.get('has_telegram_links')
        has_post_promo = tier2.get('has_promotional_post_links')

        if has_profile_promo and has_post_promo:
            score += 0.15
            reasons.append("Promotional activity in both profile and posts")
            log.debug('Signal: cross-channel promotional activity (+0.15)')

        log.debug('Tier 2 signal scoring complete: total=%.3f, reasons=%d', score, len(reasons))
        return {'score': score, 'reasons': reasons}
