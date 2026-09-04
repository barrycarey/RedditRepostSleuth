"""
Tests for username pattern analysis.
"""

from unittest import TestCase

from redditrepostsleuth.core.services.spam.username_patterns import (
    UsernameAnalysis,
    analyze_username,
    batch_analyze_usernames,
    get_username_suspicion_score,
)


class TestUsernamePatterns(TestCase):
    """Test cases for username pattern analysis."""

    def test__analyze_username__reddit_auto_generated_adjective_noun_number(self):
        """Test detection of Reddit auto-generated username pattern: Adjective_Noun_1234."""
        result = analyze_username('Prestigious_Hat_8937')
        self.assertTrue(result.is_suspicious)
        self.assertGreater(result.confidence, 0.5)
        self.assertIn('reddit_auto_adjective_noun_number', result.matched_patterns)

    def test__analyze_username__reddit_auto_generated_camelcase_digits(self):
        """Test detection of CamelCaseWord1234 pattern."""
        result = analyze_username('BrightSky1847')
        self.assertTrue(result.is_suspicious)
        self.assertGreater(result.confidence, 0.5)

    def test__analyze_username__reddit_auto_wordword_number(self):
        """Test detection of WordWordNumber pattern."""
        result = analyze_username('HappyMango2847')
        self.assertTrue(result.is_suspicious)
        self.assertGreater(result.confidence, 0.5)

    def test__analyze_username__random_alphanumeric_ending_digits(self):
        """Test detection of random chars ending with many digits."""
        result = analyze_username('xhfkjsdf12345')
        # Should detect the random_chars_ending_digits pattern
        self.assertGreater(result.confidence, 0.3)

    def test__analyze_username__many_trailing_digits(self):
        """Test detection of username with many trailing digits."""
        result = analyze_username('spammer123456')
        self.assertTrue(result.is_suspicious)
        self.assertIn('many_trailing_digits', result.matched_patterns)

    def test__analyze_username__lowercase_words_underscore_digits(self):
        """Test detection of lowercase_word_1234 pattern."""
        result = analyze_username('happy_cat_8472')
        self.assertGreater(result.confidence, 0.5)

    def test__analyze_username__crypto_prefix(self):
        """Test detection of crypto-related prefix."""
        result = analyze_username('cryptotrader99')
        self.assertIn('crypto_prefix', result.matched_patterns)
        self.assertGreater(result.confidence, 0.2)

    def test__analyze_username__promo_prefix(self):
        """Test detection of promotional prefix."""
        result = analyze_username('freeoffersnow')
        self.assertIn('promo_prefix', result.matched_patterns)

    def test__analyze_username__repeated_chars(self):
        """Test detection of repeated characters."""
        result = analyze_username('boooooring123')
        self.assertIn('repeated_chars', result.matched_patterns)

    def test__analyze_username__excessive_underscores(self):
        """Test detection of excessive underscores."""
        result = analyze_username('user___name___123')
        self.assertIn('excessive_underscores', result.matched_patterns)

    def test__analyze_username__legitimate_throwaway(self):
        """Test that throwaway usernames reduce suspicion."""
        result = analyze_username('throwaway123')
        # Should have reduced confidence due to throwaway pattern
        self.assertIn('legitimate:throwaway_explicit', result.matched_patterns)

    def test__analyze_username__legitimate_year_suffix(self):
        """Test that year suffix usernames reduce suspicion."""
        result = analyze_username('redditor2023')
        self.assertIn('legitimate:year_suffix', result.matched_patterns)

    def test__analyze_username__normal_username_low_suspicion(self):
        """Test that normal usernames have low suspicion."""
        result = analyze_username('john_doe')
        self.assertFalse(result.is_suspicious)
        self.assertLess(result.confidence, 0.5)

    def test__analyze_username__simple_username_low_suspicion(self):
        """Test that simple usernames have low suspicion."""
        # Short usernames with few trailing digits should be less suspicious
        result = analyze_username('bob_smith')
        # Should not be flagged as highly suspicious
        self.assertLess(result.confidence, 0.7)

    def test__analyze_username__empty_username(self):
        """Test handling of empty username."""
        result = analyze_username('')
        self.assertFalse(result.is_suspicious)
        self.assertEqual(result.confidence, 0.0)

    def test__analyze_username__deleted_username(self):
        """Test handling of [deleted] username."""
        result = analyze_username('[deleted]')
        self.assertFalse(result.is_suspicious)
        self.assertEqual(result.confidence, 0.0)

    def test__analyze_username__none_username(self):
        """Test handling of None username."""
        result = analyze_username(None)
        self.assertFalse(result.is_suspicious)
        self.assertEqual(result.confidence, 0.0)

    def test__batch_analyze_usernames__multiple(self):
        """Test batch analysis of multiple usernames."""
        usernames = [
            'Prestigious_Hat_8937',  # Suspicious
            'john_doe',               # Not suspicious
            'BrightSky1847',          # Suspicious
        ]
        results = batch_analyze_usernames(usernames)
        self.assertEqual(len(results), 3)
        self.assertTrue(results[0].is_suspicious)
        self.assertFalse(results[1].is_suspicious)
        self.assertTrue(results[2].is_suspicious)

    def test__batch_analyze_usernames__empty_list(self):
        """Test batch analysis with empty list."""
        results = batch_analyze_usernames([])
        self.assertEqual(len(results), 0)

    def test__get_username_suspicion_score__helper(self):
        """Test the quick helper function."""
        score = get_username_suspicion_score('Prestigious_Hat_8937')
        self.assertGreater(score, 0.5)

        score = get_username_suspicion_score('john_doe')
        self.assertLess(score, 0.5)

    def test__analyze_username__all_caps_word(self):
        """Test detection of all caps words."""
        result = analyze_username('SPAMMER_user')
        self.assertIn('all_caps_word', result.matched_patterns)

    def test__username_analysis_dataclass(self):
        """Test UsernameAnalysis dataclass creation."""
        analysis = UsernameAnalysis(
            username='test_user',
            is_suspicious=True,
            confidence=0.75,
            matched_patterns=['test_pattern'],
            details='Test details'
        )
        self.assertEqual(analysis.username, 'test_user')
        self.assertTrue(analysis.is_suspicious)
        self.assertEqual(analysis.confidence, 0.75)
        self.assertEqual(analysis.matched_patterns, ['test_pattern'])
        self.assertEqual(analysis.details, 'Test details')

    def test__analyze_username__confidence_capped_at_1(self):
        """Test that confidence is capped at 1.0."""
        # Even with multiple matching patterns, confidence should not exceed 1.0
        result = analyze_username('Prestigious_Hat_8937')
        self.assertLessEqual(result.confidence, 1.0)

    def test__analyze_username__confidence_not_negative(self):
        """Test that confidence is not negative."""
        # Legitimate patterns reduce score but shouldn't go below 0
        result = analyze_username('throwaway2023')
        self.assertGreaterEqual(result.confidence, 0.0)
