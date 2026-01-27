"""
Tests for SpamScorer service.
"""

from datetime import datetime, timedelta
from unittest import TestCase
from unittest.mock import MagicMock

from redditrepostsleuth.core.services.spam.spam_feature_extractor import Tier1Features
from redditrepostsleuth.core.services.spam.spam_scorer import (
    SpamScorer,
    SpamScorerWithTier2,
    ScoringConfig,
    ScoringResult,
)


class TestScoringResult(TestCase):
    """Test cases for ScoringResult dataclass."""

    def test__scoring_result__creation(self):
        """Test basic ScoringResult creation."""
        result = ScoringResult(
            score=0.75,
            confidence=0.85,
            risk_level='HIGH',
            reasons=['Test reason'],
            component_scores={'test': 0.5}
        )
        self.assertEqual(result.score, 0.75)
        self.assertEqual(result.confidence, 0.85)
        self.assertEqual(result.risk_level, 'HIGH')
        self.assertEqual(result.reasons, ['Test reason'])
        self.assertEqual(result.component_scores, {'test': 0.5})

    def test__scoring_result__to_dict(self):
        """Test conversion to dictionary."""
        result = ScoringResult(
            score=0.65,
            confidence=0.90,
            risk_level='HIGH',
            reasons=['Reason 1', 'Reason 2'],
            component_scores={'repost': 0.3, 'adult': 0.2}
        )
        result_dict = result.to_dict()

        self.assertEqual(result_dict['score'], 0.65)
        self.assertEqual(result_dict['confidence'], 0.90)
        self.assertEqual(result_dict['risk_level'], 'HIGH')
        self.assertEqual(len(result_dict['reasons']), 2)
        self.assertEqual(result_dict['component_scores']['repost'], 0.3)

    def test__scoring_result__from_dict(self):
        """Test creation from dictionary."""
        data = {
            'score': 0.55,
            'confidence': 0.70,
            'risk_level': 'MEDIUM',
            'reasons': ['Test'],
            'component_scores': {'karma': 0.1}
        }
        result = ScoringResult.from_dict(data)

        self.assertEqual(result.score, 0.55)
        self.assertEqual(result.confidence, 0.70)
        self.assertEqual(result.risk_level, 'MEDIUM')

    def test__scoring_result__default_values(self):
        """Test default values for optional fields."""
        result = ScoringResult(score=0.5, confidence=0.5, risk_level='MEDIUM')
        self.assertEqual(result.reasons, [])
        self.assertEqual(result.component_scores, {})


class TestScoringConfig(TestCase):
    """Test cases for ScoringConfig dataclass."""

    def test__scoring_config__defaults(self):
        """Test default configuration values."""
        config = ScoringConfig()

        # Verify key defaults
        self.assertEqual(config.repost_ratio_critical, 0.70)
        self.assertEqual(config.repost_weight_critical, 0.35)
        self.assertEqual(config.risk_critical_threshold, 0.80)
        self.assertEqual(config.risk_high_threshold, 0.60)
        self.assertEqual(config.risk_medium_threshold, 0.30)

    def test__scoring_config__custom_values(self):
        """Test custom configuration values."""
        config = ScoringConfig(
            repost_ratio_critical=0.90,
            repost_weight_critical=0.50,
            risk_critical_threshold=0.85
        )

        self.assertEqual(config.repost_ratio_critical, 0.90)
        self.assertEqual(config.repost_weight_critical, 0.50)
        self.assertEqual(config.risk_critical_threshold, 0.85)

    def test__scoring_config__reasonable_defaults(self):
        """Test that default config has reasonable values."""
        config = ScoringConfig()

        # Thresholds should be between 0 and 1
        self.assertTrue(0 < config.repost_ratio_critical <= 1)
        self.assertTrue(0 < config.risk_critical_threshold <= 1)

        # Weights should be positive but not excessive
        self.assertTrue(0 < config.repost_weight_critical <= 0.5)
        self.assertTrue(0 < config.adult_weight_critical <= 0.5)


class TestSpamScorer(TestCase):
    """Test cases for SpamScorer."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_uowm = MagicMock()
        self.mock_uow = MagicMock()
        self.mock_uowm.start.return_value.__enter__ = MagicMock(return_value=self.mock_uow)
        self.mock_uowm.start.return_value.__exit__ = MagicMock(return_value=False)
        self.scorer = SpamScorer(self.mock_uowm)

    def _make_features(self, **kwargs) -> Tier1Features:
        """Helper to create test features with defaults."""
        defaults = {
            'username': 'test_user',
            'total_posts_indexed': 50,
            'total_reposts_detected': 0,
            'repost_ratio': 0.0,
            'unique_subreddits_posted': 10,
            'posts_per_day_avg': 2.0,
            'first_post_date': datetime.utcnow() - timedelta(days=30),
            'last_post_date': datetime.utcnow(),
            'account_age_days': 30,
            'nsfw_post_count': 0,
            'nsfw_post_ratio': 0.0,
            'summons_received': 0,
            'adult_platform_post_count': 0,
            'adult_platform_ratio': 0.0,
            'short_link_post_count': 0,
            'short_link_ratio': 0.0,
            'detected_platforms': [],
            'username_suspicious_pattern': False,
            'username_pattern_confidence': 0.0,
            'username_pattern_matches': [],
            'subreddit_distribution': {},
            'subreddit_concentration_hhi': 0.0,
            'karma_farming_sub_posts': 0,
            'easy_karma_sub_posts': 0,
            'spam_subreddit_posts': 0,
            'max_posts_per_day': 5,
            'posting_entropy': 0.7,
            'burst_posting_detected': False,
            'avg_time_between_posts_minutes': 100.0,
        }
        defaults.update(kwargs)
        return Tier1Features(**defaults)

    def test__score_user__clean_user(self):
        """Test that clean user gets low score."""
        features = self._make_features()
        result = self.scorer.score_user(features)

        self.assertLess(result.score, 0.3)
        self.assertEqual(result.risk_level, 'LOW')

    def test__score_user__high_repost_ratio(self):
        """Test that high repost ratio triggers high score."""
        features = self._make_features(
            total_reposts_detected=40,
            repost_ratio=0.80
        )
        result = self.scorer.score_user(features)

        self.assertGreaterEqual(result.score, 0.35)
        self.assertTrue(any('repost ratio' in r.lower() for r in result.reasons))
        self.assertEqual(result.component_scores['repost_behavior'], 0.35)

    def test__score_user__medium_repost_ratio(self):
        """Test that medium repost ratio triggers appropriate score."""
        features = self._make_features(
            total_reposts_detected=20,
            repost_ratio=0.40
        )
        result = self.scorer.score_user(features)

        self.assertGreaterEqual(result.component_scores['repost_behavior'], 0.15)
        self.assertLess(result.component_scores['repost_behavior'], 0.35)

    def test__score_user__adult_platform_promotion(self):
        """Test that adult platform links trigger score."""
        features = self._make_features(
            adult_platform_post_count=30,
            adult_platform_ratio=0.60,
            detected_platforms=['onlyfans', 'fansly']
        )
        result = self.scorer.score_user(features)

        self.assertGreaterEqual(result.score, 0.35)
        self.assertTrue(any('adult platform' in r.lower() for r in result.reasons))

    def test__score_user__any_adult_platform_link(self):
        """Test that any adult platform link adds score."""
        features = self._make_features(
            adult_platform_post_count=1,
            adult_platform_ratio=0.02,
            detected_platforms=['onlyfans']
        )
        result = self.scorer.score_user(features)

        self.assertGreater(result.component_scores['adult_platform'], 0)
        self.assertTrue(any('adult platform' in r.lower() for r in result.reasons))

    def test__score_user__high_posting_frequency(self):
        """Test that high posting frequency triggers score."""
        features = self._make_features(
            posts_per_day_avg=20.0
        )
        result = self.scorer.score_user(features)

        self.assertGreater(result.score, 0.15)
        self.assertTrue(any('posting frequency' in r.lower() for r in result.reasons))

    def test__score_user__elevated_posting_frequency(self):
        """Test that elevated posting frequency triggers smaller score."""
        features = self._make_features(
            posts_per_day_avg=6.0
        )
        result = self.scorer.score_user(features)

        self.assertGreater(result.component_scores['posting_patterns'], 0)
        self.assertLess(result.component_scores['posting_patterns'], 0.20)

    def test__score_user__suspicious_username_list(self):
        """Test that suspicious username triggers score (list format)."""
        features = self._make_features(
            username_suspicious_pattern=True,
            username_pattern_matches=['reddit_autogenerated']
        )
        result = self.scorer.score_user(features)

        self.assertGreater(result.score, 0.1)
        self.assertTrue(any('username' in r.lower() for r in result.reasons))

    def test__score_user__suspicious_username_dict(self):
        """Test that suspicious username triggers score (dict format)."""
        features = self._make_features(
            username_suspicious_pattern=True,
            username_pattern_matches={'reddit_autogenerated': True}
        )
        result = self.scorer.score_user(features)

        self.assertGreater(result.score, 0.1)
        self.assertTrue(any('username' in r.lower() for r in result.reasons))

    def test__score_user__karma_farming(self):
        """Test that karma farming posts trigger score."""
        features = self._make_features(
            karma_farming_sub_posts=10
        )
        result = self.scorer.score_user(features)

        self.assertGreater(result.score, 0.2)
        self.assertTrue(any('karma farming' in r.lower() for r in result.reasons))

    def test__score_user__karma_farming_capped(self):
        """Test that karma farming score is capped."""
        features = self._make_features(
            karma_farming_sub_posts=100  # Very high
        )
        result = self.scorer.score_user(features)

        # Should be capped at 0.30
        self.assertEqual(result.component_scores['karma_farming'], 0.30)

    def test__score_user__combined_signals(self):
        """Test that combined signals produce high score."""
        features = self._make_features(
            total_reposts_detected=30,
            repost_ratio=0.60,
            posts_per_day_avg=12.0,
            username_suspicious_pattern=True,
            username_pattern_matches=['word_word_numbers'],
            karma_farming_sub_posts=5,
        )
        result = self.scorer.score_user(features)

        self.assertGreaterEqual(result.score, 0.6)
        self.assertIn(result.risk_level, ['HIGH', 'CRITICAL'])

    def test__score_user__confidence_increases_with_data(self):
        """Test that confidence increases with more posts."""
        # Few posts
        features_low = self._make_features(total_posts_indexed=5)
        result_low = self.scorer.score_user(features_low)

        # Many posts
        features_high = self._make_features(total_posts_indexed=100)
        result_high = self.scorer.score_user(features_high)

        self.assertGreater(result_high.confidence, result_low.confidence)

    def test__score_user__confidence_boost_with_reposts(self):
        """Test that having repost data boosts confidence."""
        features_no_reposts = self._make_features(
            total_posts_indexed=20,
            total_reposts_detected=0
        )
        result_no = self.scorer.score_user(features_no_reposts)

        features_with_reposts = self._make_features(
            total_posts_indexed=20,
            total_reposts_detected=5
        )
        result_with = self.scorer.score_user(features_with_reposts)

        self.assertGreater(result_with.confidence, result_no.confidence)

    def test__score_user__risk_level_low(self):
        """Test LOW risk level classification."""
        features = self._make_features()
        result = self.scorer.score_user(features)
        self.assertEqual(result.risk_level, 'LOW')

    def test__score_user__risk_level_medium(self):
        """Test MEDIUM risk level classification."""
        features = self._make_features(
            repost_ratio=0.35,
            karma_farming_sub_posts=5,  # Adds more weight to push into MEDIUM
            posts_per_day_avg=6.0  # Elevated posting adds weight
        )
        result = self.scorer.score_user(features)
        self.assertEqual(result.risk_level, 'MEDIUM')

    def test__score_user__risk_level_high(self):
        """Test HIGH risk level classification."""
        features = self._make_features(
            repost_ratio=0.55,  # Gives 0.25
            adult_platform_ratio=0.25,
            adult_platform_post_count=10,  # Gives 0.25
            karma_farming_sub_posts=3  # Gives 0.15
        )
        result = self.scorer.score_user(features)
        self.assertEqual(result.risk_level, 'HIGH')

    def test__score_user__risk_level_critical(self):
        """Test CRITICAL risk level classification."""
        features = self._make_features(
            repost_ratio=0.80,
            adult_platform_ratio=0.60,
            posts_per_day_avg=15.0,
        )
        result = self.scorer.score_user(features)
        self.assertEqual(result.risk_level, 'CRITICAL')

    def test__score_user__capped_at_one(self):
        """Test that score never exceeds 1.0."""
        # Create extreme spam features
        features = self._make_features(
            repost_ratio=0.90,
            adult_platform_ratio=0.70,
            adult_platform_post_count=50,
            posts_per_day_avg=25.0,
            username_suspicious_pattern=True,
            username_pattern_matches=['reddit_autogenerated'],
            karma_farming_sub_posts=20,
            short_link_ratio=0.50,
            short_link_post_count=20,
            nsfw_post_ratio=0.80,
        )
        result = self.scorer.score_user(features)

        self.assertLessEqual(result.score, 1.0)

    def test__score_user__nsfw_adult_platform_combo(self):
        """Test that NSFW + adult platform combo adds extra weight."""
        features = self._make_features(
            nsfw_post_ratio=0.60,
            adult_platform_ratio=0.15,
            adult_platform_post_count=5
        )
        result = self.scorer.score_user(features)

        self.assertTrue(any('nsfw' in r.lower() and 'adult' in r.lower() for r in result.reasons))
        self.assertGreater(result.component_scores['supporting_signals'], 0)

    def test__score_user__short_links_high_ratio(self):
        """Test that high short link ratio triggers score."""
        features = self._make_features(
            short_link_ratio=0.40,
            short_link_post_count=20
        )
        result = self.scorer.score_user(features)

        self.assertGreater(result.component_scores['supporting_signals'], 0)
        self.assertTrue(any('promo link' in r.lower() for r in result.reasons))

    def test__score_user__short_links_few_posts(self):
        """Test that multiple short links trigger score."""
        features = self._make_features(
            short_link_ratio=0.10,
            short_link_post_count=3
        )
        result = self.scorer.score_user(features)

        self.assertGreater(result.component_scores['supporting_signals'], 0)

    def test__score_user__low_subreddit_diversity(self):
        """Test that low subreddit diversity triggers score."""
        features = self._make_features(
            total_posts_indexed=50,
            unique_subreddits_posted=2
        )
        result = self.scorer.score_user(features)

        self.assertTrue(any('diversity' in r.lower() for r in result.reasons))
        self.assertGreater(result.component_scores['posting_patterns'], 0)

    def test__score_user__component_scores_present(self):
        """Test that all component scores are present in result."""
        features = self._make_features()
        result = self.scorer.score_user(features)

        expected_components = [
            'repost_behavior',
            'adult_platform',
            'posting_patterns',
            'username_pattern',
            'karma_farming',
            'supporting_signals'
        ]
        for component in expected_components:
            self.assertIn(component, result.component_scores)

    def test__score_user__custom_config(self):
        """Test scoring with custom configuration."""
        config = ScoringConfig(
            repost_ratio_critical=0.50,
            repost_weight_critical=0.40
        )
        scorer = SpamScorer(self.mock_uowm, config)

        features = self._make_features(repost_ratio=0.55)
        result = scorer.score_user(features)

        # With custom config, 55% repost ratio should trigger critical weight
        self.assertEqual(result.component_scores['repost_behavior'], 0.40)


class TestSpamScorerWithTier2(TestCase):
    """Test cases for SpamScorerWithTier2."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_uowm = MagicMock()
        self.mock_uow = MagicMock()
        self.mock_uowm.start.return_value.__enter__ = MagicMock(return_value=self.mock_uow)
        self.mock_uowm.start.return_value.__exit__ = MagicMock(return_value=False)
        self.scorer = SpamScorerWithTier2(self.mock_uowm)

    def _make_features(self, **kwargs) -> Tier1Features:
        """Helper to create test features with defaults."""
        defaults = {
            'username': 'test_user',
            'total_posts_indexed': 50,
            'total_reposts_detected': 0,
            'repost_ratio': 0.0,
            'unique_subreddits_posted': 10,
            'posts_per_day_avg': 2.0,
            'first_post_date': datetime.utcnow() - timedelta(days=30),
            'last_post_date': datetime.utcnow(),
            'account_age_days': 30,
            'nsfw_post_count': 0,
            'nsfw_post_ratio': 0.0,
            'summons_received': 0,
            'adult_platform_post_count': 0,
            'adult_platform_ratio': 0.0,
            'short_link_post_count': 0,
            'short_link_ratio': 0.0,
            'detected_platforms': [],
            'username_suspicious_pattern': False,
            'username_pattern_confidence': 0.0,
            'username_pattern_matches': [],
            'subreddit_distribution': {},
            'subreddit_concentration_hhi': 0.0,
            'karma_farming_sub_posts': 0,
            'easy_karma_sub_posts': 0,
            'spam_subreddit_posts': 0,
            'max_posts_per_day': 5,
            'posting_entropy': 0.7,
            'burst_posting_detected': False,
            'avg_time_between_posts_minutes': 100.0,
        }
        defaults.update(kwargs)
        return Tier1Features(**defaults)

    def test__score_with_tier2__suspended_account(self):
        """Test that suspended account adds major score."""
        tier1 = self._make_features()
        tier2 = {'account_suspended': True}

        result = self.scorer.score_with_tier2(tier1, tier2)

        self.assertGreaterEqual(result.score, 0.50)
        self.assertTrue(any('suspended' in r.lower() for r in result.reasons))

    def test__score_with_tier2__new_account(self):
        """Test that very new account adds score."""
        tier1 = self._make_features()
        tier2 = {'account_age_days': 15}

        result = self.scorer.score_with_tier2(tier1, tier2)

        self.assertGreater(result.score, 0)
        self.assertTrue(any('new account' in r.lower() for r in result.reasons))

    def test__score_with_tier2__low_karma(self):
        """Test that low karma adds score."""
        tier1 = self._make_features()
        tier2 = {'account_age_days': 100, 'total_karma': 50}

        result = self.scorer.score_with_tier2(tier1, tier2)

        self.assertTrue(any('karma' in r.lower() for r in result.reasons))

    def test__score_with_tier2__no_verified_email(self):
        """Test that no verified email adds score."""
        tier1 = self._make_features()
        tier2 = {'has_verified_email': False}

        result = self.scorer.score_with_tier2(tier1, tier2)

        self.assertTrue(any('email' in r.lower() for r in result.reasons))

    def test__score_with_tier2__default_avatar(self):
        """Test that default avatar adds score."""
        tier1 = self._make_features()
        tier2 = {'has_custom_avatar': False}

        result = self.scorer.score_with_tier2(tier1, tier2)

        self.assertTrue(any('avatar' in r.lower() for r in result.reasons))

    def test__score_with_tier2__adult_profile_links(self):
        """Test that adult links in profile adds score."""
        tier1 = self._make_features()
        tier2 = {'has_adult_profile_links': True}

        result = self.scorer.score_with_tier2(tier1, tier2)

        self.assertGreater(result.component_scores['tier2_signals'], 0)
        self.assertTrue(any('adult' in r.lower() and 'profile' in r.lower() for r in result.reasons))

    def test__score_with_tier2__telegram_links(self):
        """Test that telegram links adds score."""
        tier1 = self._make_features()
        tier2 = {'has_telegram_links': True}

        result = self.scorer.score_with_tier2(tier1, tier2)

        self.assertTrue(any('telegram' in r.lower() for r in result.reasons))

    def test__score_with_tier2__confidence_boost(self):
        """Test that Tier 2 data boosts confidence."""
        tier1 = self._make_features(total_posts_indexed=20)
        tier2 = {}

        result = self.scorer.score_with_tier2(tier1, tier2)

        # Base confidence for 20 posts is 0.70, tier2 should boost by 0.10
        # Use assertAlmostEqual to handle floating point precision
        self.assertAlmostEqual(result.confidence, 0.80, places=1)

    def test__score_with_tier2__combined_signals(self):
        """Test combining Tier 1 and Tier 2 signals."""
        tier1 = self._make_features(
            repost_ratio=0.50,
            karma_farming_sub_posts=5
        )
        tier2 = {
            'account_age_days': 20,
            'has_verified_email': False,
            'has_telegram_links': True
        }

        result = self.scorer.score_with_tier2(tier1, tier2)

        # Should have signals from both tiers
        self.assertIn('tier2_signals', result.component_scores)
        self.assertGreater(result.component_scores['tier2_signals'], 0)
        self.assertGreater(result.component_scores['repost_behavior'], 0)

    def test__score_with_tier2__reclassifies_risk(self):
        """Test that Tier 2 can change risk classification."""
        tier1 = self._make_features(repost_ratio=0.55)  # Would be HIGH alone
        tier2 = {'account_suspended': True}

        result = self.scorer.score_with_tier2(tier1, tier2)

        # With suspended account, should be CRITICAL
        self.assertEqual(result.risk_level, 'CRITICAL')

    def test__score_with_tier2__still_capped_at_one(self):
        """Test that combined score is still capped at 1.0."""
        tier1 = self._make_features(
            repost_ratio=0.90,
            adult_platform_ratio=0.70,
            adult_platform_post_count=50
        )
        tier2 = {
            'account_suspended': True,
            'account_age_days': 5,
            'has_telegram_links': True,
            'has_adult_profile_links': True
        }

        result = self.scorer.score_with_tier2(tier1, tier2)

        self.assertLessEqual(result.score, 1.0)
