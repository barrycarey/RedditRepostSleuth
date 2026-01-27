"""Tests for Tier2Features dataclass."""
import unittest
from datetime import datetime

from redditrepostsleuth.core.services.spam.tier2_features import Tier2Features


class TestTier2Features(unittest.TestCase):
    """Test cases for Tier2Features dataclass."""

    def test_default_values(self):
        """Test that default values are set correctly."""
        features = Tier2Features()

        self.assertEqual(features.account_age_days, 0)
        self.assertEqual(features.total_karma, 0)
        self.assertEqual(features.post_karma, 0)
        self.assertEqual(features.comment_karma, 0)
        self.assertEqual(features.karma_per_day, 0.0)
        self.assertFalse(features.has_verified_email)
        self.assertFalse(features.is_gold)
        self.assertFalse(features.has_custom_avatar)
        self.assertFalse(features.is_mod)
        self.assertFalse(features.account_suspended)
        self.assertFalse(features.has_adult_profile_links)
        self.assertFalse(features.has_telegram_links)
        self.assertEqual(features.profile_link_sources, {})
        self.assertIsNone(features.fetched_at)
        self.assertTrue(features.fetch_success)
        self.assertIsNone(features.error_message)

    def test_custom_values(self):
        """Test creating with custom values."""
        features = Tier2Features(
            account_age_days=365,
            total_karma=10000,
            post_karma=7000,
            comment_karma=3000,
            karma_per_day=27.4,
            has_verified_email=True,
            is_gold=True,
            has_custom_avatar=True,
            is_mod=True,
            account_suspended=False,
        )

        self.assertEqual(features.account_age_days, 365)
        self.assertEqual(features.total_karma, 10000)
        self.assertEqual(features.karma_per_day, 27.4)
        self.assertTrue(features.has_verified_email)
        self.assertTrue(features.is_gold)

    def test_to_dict(self):
        """Test to_dict serialization."""
        now = datetime.utcnow()
        features = Tier2Features(
            account_age_days=100,
            total_karma=5000,
            has_verified_email=True,
            fetched_at=now,
        )

        result = features.to_dict()

        self.assertEqual(result['account_age_days'], 100)
        self.assertEqual(result['total_karma'], 5000)
        self.assertTrue(result['has_verified_email'])
        self.assertEqual(result['fetched_at'], now.isoformat())
        self.assertTrue(result['fetch_success'])

    def test_to_dict_with_none_fetched_at(self):
        """Test to_dict with None fetched_at."""
        features = Tier2Features()
        result = features.to_dict()

        self.assertIsNone(result['fetched_at'])

    def test_from_dict(self):
        """Test from_dict deserialization."""
        data = {
            'account_age_days': 200,
            'total_karma': 8000,
            'post_karma': 5000,
            'comment_karma': 3000,
            'karma_per_day': 40.0,
            'has_verified_email': True,
            'is_gold': False,
            'has_custom_avatar': True,
            'is_mod': False,
            'account_suspended': False,
            'has_adult_profile_links': True,
            'has_telegram_links': True,
            'profile_link_sources': {'profile': ['bio']},
            'fetched_at': '2026-01-01T12:00:00',
            'fetch_success': True,
            'error_message': None,
        }

        features = Tier2Features.from_dict(data)

        self.assertEqual(features.account_age_days, 200)
        self.assertEqual(features.total_karma, 8000)
        self.assertTrue(features.has_verified_email)
        self.assertTrue(features.has_adult_profile_links)
        self.assertTrue(features.has_telegram_links)
        self.assertEqual(features.profile_link_sources, {'profile': ['bio']})
        self.assertIsInstance(features.fetched_at, datetime)

    def test_from_dict_with_missing_fields(self):
        """Test from_dict handles missing fields with defaults."""
        data = {'account_age_days': 50}

        features = Tier2Features.from_dict(data)

        self.assertEqual(features.account_age_days, 50)
        self.assertEqual(features.total_karma, 0)
        self.assertFalse(features.has_verified_email)

    def test_suspended_user_factory(self):
        """Test suspended_user factory method."""
        features = Tier2Features.suspended_user('testuser', 'User suspended by Reddit')

        self.assertTrue(features.account_suspended)
        self.assertEqual(features.account_age_days, 0)
        self.assertEqual(features.total_karma, 0)
        self.assertTrue(features.fetch_success)
        self.assertIsNotNone(features.fetched_at)
        self.assertIn('suspended', features.error_message)

    def test_failed_fetch_factory(self):
        """Test failed_fetch factory method."""
        features = Tier2Features.failed_fetch('Connection timeout')

        self.assertFalse(features.fetch_success)
        self.assertEqual(features.error_message, 'Connection timeout')
        self.assertIsNotNone(features.fetched_at)

    def test_is_suspicious_with_multiple_indicators(self):
        """Test is_suspicious returns True with multiple indicators."""
        features = Tier2Features(
            account_age_days=10,  # New account
            total_karma=50,  # Low karma
            has_verified_email=False,
            has_telegram_links=True,
        )

        self.assertTrue(features.is_suspicious())

    def test_is_suspicious_with_few_indicators(self):
        """Test is_suspicious returns False with few indicators."""
        features = Tier2Features(
            account_age_days=365,
            total_karma=10000,
            has_verified_email=True,
            is_gold=True,
        )

        self.assertFalse(features.is_suspicious())

    def test_is_suspicious_suspended_user(self):
        """Test is_suspicious returns True for suspended user."""
        features = Tier2Features(account_suspended=True)
        # May or may not be suspicious depending on other fields
        # Suspended user + no email + no avatar should be suspicious
        features.has_verified_email = False
        features.has_custom_avatar = False

        self.assertTrue(features.is_suspicious())

    def test_get_suspicion_reasons(self):
        """Test get_suspicion_reasons returns correct reasons."""
        features = Tier2Features(
            account_age_days=15,
            total_karma=10,
            has_verified_email=False,
            has_telegram_links=True,
        )

        reasons = features.get_suspicion_reasons()

        self.assertIn("New account (15 days old)", reasons)
        self.assertIn("No verified email", reasons)
        self.assertIn("Has Telegram links", reasons)

    def test_get_suspicion_reasons_suspended(self):
        """Test get_suspicion_reasons includes suspension."""
        features = Tier2Features(account_suspended=True)

        reasons = features.get_suspicion_reasons()

        self.assertIn("Account is suspended", reasons)

    def test_get_suspicion_reasons_low_karma_rate(self):
        """Test get_suspicion_reasons includes low karma rate."""
        features = Tier2Features(
            account_age_days=180,
            total_karma=50,
            karma_per_day=0.3,
        )

        reasons = features.get_suspicion_reasons()

        self.assertTrue(any("karma rate" in r.lower() for r in reasons))


class TestTier2FeaturesRoundTrip(unittest.TestCase):
    """Test round-trip serialization."""

    def test_to_dict_from_dict_roundtrip(self):
        """Test that to_dict and from_dict are inverses."""
        original = Tier2Features(
            account_age_days=500,
            total_karma=25000,
            post_karma=15000,
            comment_karma=10000,
            karma_per_day=50.0,
            has_verified_email=True,
            is_gold=True,
            has_custom_avatar=True,
            is_mod=True,
            has_adult_profile_links=True,
            has_telegram_links=True,
            profile_link_sources={'comments': ['abc123']},
            fetched_at=datetime(2026, 1, 15, 10, 30, 0),
            fetch_success=True,
        )

        # Round trip
        data = original.to_dict()
        restored = Tier2Features.from_dict(data)

        self.assertEqual(restored.account_age_days, original.account_age_days)
        self.assertEqual(restored.total_karma, original.total_karma)
        self.assertEqual(restored.has_verified_email, original.has_verified_email)
        self.assertEqual(restored.profile_link_sources, original.profile_link_sources)
        # Note: datetime precision may differ slightly


if __name__ == '__main__':
    unittest.main()
