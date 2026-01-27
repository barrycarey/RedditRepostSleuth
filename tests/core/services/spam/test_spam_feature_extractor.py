"""
Tests for SpamFeatureExtractor service.
"""

from datetime import datetime, timedelta
from unittest import TestCase
from unittest.mock import MagicMock, patch, PropertyMock

from redditrepostsleuth.core.services.spam.spam_feature_extractor import (
    SpamFeatureExtractor,
    Tier1Features,
    MIN_POSTS_FOR_ANALYSIS,
)


class TestTier1Features(TestCase):
    """Test cases for Tier1Features dataclass."""

    def test__tier1_features__creation(self):
        """Test basic Tier1Features creation."""
        features = Tier1Features(username='test_user')
        self.assertEqual(features.username, 'test_user')
        self.assertEqual(features.total_posts_indexed, 0)
        self.assertEqual(features.repost_ratio, 0.0)
        self.assertFalse(features.username_suspicious_pattern)

    def test__tier1_features__to_dict(self):
        """Test conversion to dictionary."""
        features = Tier1Features(
            username='test_user',
            total_posts_indexed=10,
            repost_ratio=0.3,
            first_post_date=datetime(2024, 1, 1, 12, 0, 0),
            last_post_date=datetime(2024, 6, 1, 12, 0, 0),
        )
        result = features.to_dict()

        self.assertEqual(result['username'], 'test_user')
        self.assertEqual(result['total_posts_indexed'], 10)
        self.assertEqual(result['repost_ratio'], 0.3)
        # Dates should be ISO format strings
        self.assertEqual(result['first_post_date'], '2024-01-01T12:00:00')
        self.assertEqual(result['last_post_date'], '2024-06-01T12:00:00')

    def test__tier1_features__from_dict(self):
        """Test creation from dictionary."""
        data = {
            'username': 'test_user',
            'total_posts_indexed': 10,
            'repost_ratio': 0.3,
            'first_post_date': '2024-01-01T12:00:00',
            'last_post_date': '2024-06-01T12:00:00',
            'total_reposts_detected': 0,
            'unique_subreddits_posted': 0,
            'posts_per_day_avg': 0.0,
            'account_age_days': 0,
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
            'max_posts_per_day': 0,
            'posting_entropy': 0.0,
            'burst_posting_detected': False,
            'avg_time_between_posts_minutes': 0.0,
        }
        features = Tier1Features.from_dict(data)

        self.assertEqual(features.username, 'test_user')
        self.assertEqual(features.total_posts_indexed, 10)
        self.assertEqual(features.first_post_date, datetime(2024, 1, 1, 12, 0, 0))

    def test__tier1_features__to_dict_none_dates(self):
        """Test to_dict handles None dates."""
        features = Tier1Features(username='test_user')
        result = features.to_dict()
        self.assertIsNone(result['first_post_date'])
        self.assertIsNone(result['last_post_date'])


class TestSpamFeatureExtractor(TestCase):
    """Test cases for SpamFeatureExtractor."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_uowm = MagicMock()
        self.mock_uow = MagicMock()
        self.mock_uowm.start.return_value.__enter__ = MagicMock(return_value=self.mock_uow)
        self.mock_uowm.start.return_value.__exit__ = MagicMock(return_value=False)
        self.extractor = SpamFeatureExtractor(self.mock_uowm)

    def test__is_user_worth_analyzing__deleted_user(self):
        """Test that [deleted] users are not worth analyzing."""
        result = self.extractor.is_user_worth_analyzing('[deleted]')
        self.assertFalse(result)

    def test__is_user_worth_analyzing__empty_username(self):
        """Test that empty usernames are not worth analyzing."""
        result = self.extractor.is_user_worth_analyzing('')
        self.assertFalse(result)

    def test__is_user_worth_analyzing__none_username(self):
        """Test that None usernames are not worth analyzing."""
        result = self.extractor.is_user_worth_analyzing(None)
        self.assertFalse(result)

    def test__is_user_worth_analyzing__insufficient_posts(self):
        """Test user with too few posts."""
        self.mock_uow.author_activity.count_by_author.return_value = 2
        result = self.extractor.is_user_worth_analyzing('test_user')
        self.assertFalse(result)

    def test__is_user_worth_analyzing__sufficient_posts(self):
        """Test user with enough posts."""
        self.mock_uow.author_activity.count_by_author.return_value = MIN_POSTS_FOR_ANALYSIS
        result = self.extractor.is_user_worth_analyzing('test_user')
        self.assertTrue(result)

    def test__check_username_pattern__suspicious(self):
        """Test detection of suspicious username pattern."""
        is_suspicious, confidence, patterns = self.extractor.check_username_pattern('Prestigious_Hat_8937')
        self.assertTrue(is_suspicious)
        self.assertGreater(confidence, 0.5)
        self.assertTrue(len(patterns) > 0)

    def test__check_username_pattern__normal(self):
        """Test normal username is not suspicious."""
        is_suspicious, confidence, patterns = self.extractor.check_username_pattern('john_doe')
        self.assertFalse(is_suspicious)
        self.assertLess(confidence, 0.5)

    def test__extract_subreddit_behavior__empty(self):
        """Test subreddit behavior with no activity."""
        self.mock_uow.author_activity.get_author_subreddit_distribution.return_value = {}
        result = self.extractor.extract_subreddit_behavior('test_user')

        self.assertEqual(result['distribution'], {})
        self.assertEqual(result['concentration_hhi'], 0.0)
        self.assertEqual(result['unique_count'], 0)

    def test__extract_subreddit_behavior__single_subreddit(self):
        """Test subreddit behavior with single subreddit (max concentration)."""
        self.mock_uow.author_activity.get_author_subreddit_distribution.return_value = {
            'pics': 10
        }
        result = self.extractor.extract_subreddit_behavior('test_user')

        self.assertEqual(result['distribution'], {'pics': 10})
        self.assertEqual(result['concentration_hhi'], 1.0)  # 100% in one sub = HHI of 1.0
        self.assertEqual(result['unique_count'], 1)

    def test__extract_subreddit_behavior__multiple_subreddits(self):
        """Test subreddit behavior with multiple subreddits."""
        self.mock_uow.author_activity.get_author_subreddit_distribution.return_value = {
            'pics': 5,
            'funny': 5
        }
        result = self.extractor.extract_subreddit_behavior('test_user')

        self.assertEqual(result['unique_count'], 2)
        # 50% in each sub = HHI of 0.5 (0.5^2 + 0.5^2 = 0.25 + 0.25)
        self.assertAlmostEqual(result['concentration_hhi'], 0.5, places=2)

    def test__get_spam_subreddits__caching(self):
        """Test that spam subreddits are cached."""
        self.mock_uow.spam_subreddit.get_as_dict.return_value = {
            'freekarma4u': ('karma_farming', 1.0)
        }

        # First call
        result1 = self.extractor._get_spam_subreddits()
        # Second call should use cache
        result2 = self.extractor._get_spam_subreddits()

        self.assertEqual(result1, result2)
        # Should only call the database once
        self.assertEqual(self.mock_uow.spam_subreddit.get_as_dict.call_count, 1)

    def test__extract_tier1_features__insufficient_data(self):
        """Test extraction with insufficient data returns None."""
        self.mock_uow.author_activity.count_by_author.return_value = 1
        result = self.extractor.extract_tier1_features('test_user')
        self.assertIsNone(result)

    def test__extract_tier1_features__deleted_user(self):
        """Test extraction for deleted user returns None."""
        result = self.extractor.extract_tier1_features('[deleted]')
        self.assertIsNone(result)

    def test__extract_tier1_features__success(self):
        """Test successful feature extraction."""
        # Mock count check
        self.mock_uow.author_activity.count_by_author.return_value = 10

        # Mock author stats
        self.mock_uow.author_activity.get_author_stats.return_value = {
            'total_posts': 10,
            'nsfw_count': 2,
            'adult_link_count': 1,
            'short_link_count': 0,
            'unique_subreddits': 3
        }

        # Mock repost count
        self.mock_uow.repost.count_reposts_by_author.return_value = 3

        # Mock summons count
        self.mock_uow.summons.count_by_post_author.return_value = 1

        # Mock subreddit distribution
        self.mock_uow.author_activity.get_author_subreddit_distribution.return_value = {
            'pics': 5,
            'funny': 3,
            'test': 2
        }

        # Mock spam subreddits
        self.mock_uow.spam_subreddit.get_as_dict.return_value = {}

        # Mock activity timeline
        now = datetime.utcnow()
        mock_activities = []
        for i in range(10):
            mock_activity = MagicMock()
            mock_activity.created_at = now - timedelta(days=i)
            mock_activities.append(mock_activity)
        self.mock_uow.author_activity.get_by_author.return_value = mock_activities

        result = self.extractor.extract_tier1_features('normal_user')

        self.assertIsNotNone(result)
        self.assertEqual(result.username, 'normal_user')
        self.assertEqual(result.total_posts_indexed, 10)
        self.assertEqual(result.total_reposts_detected, 3)
        self.assertEqual(result.repost_ratio, 0.3)
        self.assertEqual(result.nsfw_post_count, 2)
        self.assertEqual(result.nsfw_post_ratio, 0.2)
        self.assertEqual(result.unique_subreddits_posted, 3)
        self.assertEqual(result.summons_received, 1)
        self.assertFalse(result.username_suspicious_pattern)

    def test__extract_tier1_features__with_spam_subreddits(self):
        """Test feature extraction counts spam subreddit posts."""
        self.mock_uow.author_activity.count_by_author.return_value = 10

        self.mock_uow.author_activity.get_author_stats.return_value = {
            'total_posts': 10,
            'nsfw_count': 0,
            'adult_link_count': 0,
            'short_link_count': 0,
            'unique_subreddits': 2
        }

        self.mock_uow.repost.count_reposts_by_author.return_value = 0
        self.mock_uow.summons.count_by_post_author.return_value = 0

        self.mock_uow.author_activity.get_author_subreddit_distribution.return_value = {
            'freekarma4u': 5,
            'pics': 5
        }

        # Mock spam subreddits - freekarma4u is karma farming
        self.mock_uow.spam_subreddit.get_as_dict.return_value = {
            'freekarma4u': ('karma_farming', 1.0)
        }

        now = datetime.utcnow()
        mock_activities = []
        for i in range(10):
            mock_activity = MagicMock()
            mock_activity.created_at = now - timedelta(days=i)
            mock_activities.append(mock_activity)
        self.mock_uow.author_activity.get_by_author.return_value = mock_activities

        result = self.extractor.extract_tier1_features('spammer_user')

        self.assertIsNotNone(result)
        self.assertEqual(result.spam_subreddit_posts, 5)
        self.assertEqual(result.karma_farming_sub_posts, 5)

    def test__store_features__success(self):
        """Test successful feature storage."""
        features = Tier1Features(
            username='test_user',
            total_posts_indexed=10,
            repost_ratio=0.3,
        )

        result = self.extractor.store_features(features)

        self.assertTrue(result)
        self.mock_uow.spam_features.update_or_create.assert_called_once()
        self.mock_uow.commit.assert_called_once()

    def test__store_features__failure(self):
        """Test feature storage failure."""
        self.mock_uow.spam_features.update_or_create.side_effect = Exception('DB error')

        features = Tier1Features(username='test_user')
        result = self.extractor.store_features(features)

        self.assertFalse(result)

    def test__extract_and_store__success(self):
        """Test extract and store combined operation."""
        # Mock successful extraction
        self.mock_uow.author_activity.count_by_author.return_value = 5

        self.mock_uow.author_activity.get_author_stats.return_value = {
            'total_posts': 5,
            'nsfw_count': 0,
            'adult_link_count': 0,
            'short_link_count': 0,
            'unique_subreddits': 2
        }

        self.mock_uow.repost.count_reposts_by_author.return_value = 1
        self.mock_uow.summons.count_by_post_author.return_value = 0

        self.mock_uow.author_activity.get_author_subreddit_distribution.return_value = {
            'pics': 3,
            'funny': 2
        }

        self.mock_uow.spam_subreddit.get_as_dict.return_value = {}

        now = datetime.utcnow()
        mock_activities = []
        for i in range(5):
            mock_activity = MagicMock()
            mock_activity.created_at = now - timedelta(days=i)
            mock_activities.append(mock_activity)
        self.mock_uow.author_activity.get_by_author.return_value = mock_activities

        result = self.extractor.extract_and_store('test_user')

        self.assertIsNotNone(result)
        self.assertEqual(result.username, 'test_user')
        self.mock_uow.commit.assert_called()

    def test__extract_and_store__insufficient_data(self):
        """Test extract and store with insufficient data."""
        self.mock_uow.author_activity.count_by_author.return_value = 1

        result = self.extractor.extract_and_store('test_user')

        self.assertIsNone(result)


class TestActivityTimeline(TestCase):
    """Test cases for activity timeline analysis."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_uowm = MagicMock()
        self.mock_uow = MagicMock()
        self.mock_uowm.start.return_value.__enter__ = MagicMock(return_value=self.mock_uow)
        self.mock_uowm.start.return_value.__exit__ = MagicMock(return_value=False)
        self.extractor = SpamFeatureExtractor(self.mock_uowm)

    def test__get_activity_timeline__no_activity(self):
        """Test timeline with no activity."""
        self.mock_uow.author_activity.get_by_author.return_value = []

        result = self.extractor.get_activity_timeline('test_user')

        self.assertIsNone(result['first_post_date'])
        self.assertIsNone(result['last_post_date'])
        self.assertEqual(result['account_age_days'], 0)
        self.assertEqual(result['posts_per_day_avg'], 0.0)

    def test__get_activity_timeline__single_day_activity(self):
        """Test timeline with activity on single day."""
        now = datetime.utcnow()
        mock_activities = []
        for i in range(5):
            mock_activity = MagicMock()
            mock_activity.created_at = now
            mock_activities.append(mock_activity)
        self.mock_uow.author_activity.get_by_author.return_value = mock_activities

        result = self.extractor.get_activity_timeline('test_user')

        self.assertEqual(result['account_age_days'], 1)  # Minimum 1 day
        self.assertEqual(result['max_posts_per_day'], 5)

    def test__get_activity_timeline__burst_detection(self):
        """Test detection of burst posting (>10 posts in an hour)."""
        now = datetime.utcnow()
        mock_activities = []
        # 15 posts in the same hour
        for i in range(15):
            mock_activity = MagicMock()
            mock_activity.created_at = now + timedelta(minutes=i)
            mock_activities.append(mock_activity)
        self.mock_uow.author_activity.get_by_author.return_value = mock_activities

        result = self.extractor.get_activity_timeline('test_user')

        self.assertTrue(result['burst_posting_detected'])

    def test__get_activity_timeline__no_burst(self):
        """Test no burst detected with normal posting."""
        now = datetime.utcnow()
        mock_activities = []
        # 5 posts spread across 5 hours
        for i in range(5):
            mock_activity = MagicMock()
            mock_activity.created_at = now + timedelta(hours=i)
            mock_activities.append(mock_activity)
        self.mock_uow.author_activity.get_by_author.return_value = mock_activities

        result = self.extractor.get_activity_timeline('test_user')

        self.assertFalse(result['burst_posting_detected'])

    def test__get_activity_timeline__posting_entropy(self):
        """Test posting entropy calculation."""
        now = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        mock_activities = []
        # Posts spread across different hours (higher entropy)
        for hour in range(24):
            mock_activity = MagicMock()
            mock_activity.created_at = now + timedelta(hours=hour)
            mock_activities.append(mock_activity)
        self.mock_uow.author_activity.get_by_author.return_value = mock_activities

        result = self.extractor.get_activity_timeline('test_user')

        # Perfect distribution across 24 hours should have high entropy (close to 1.0)
        self.assertGreater(result['posting_entropy'], 0.9)
