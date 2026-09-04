"""
Username pattern analysis for spam detection.

This module implements username pattern analysis to identify potentially
auto-generated or suspicious usernames commonly associated with spam accounts.
"""

import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple


@dataclass
class UsernameAnalysis:
    """Result of username pattern analysis."""
    username: str
    is_suspicious: bool
    confidence: float  # 0.0 to 1.0
    matched_patterns: List[str] = field(default_factory=list)
    details: Optional[str] = None


# Pattern definitions: (name, regex, confidence_weight)
# Higher weight = more indicative of spam/auto-generated username
USERNAME_PATTERNS: List[Tuple[str, str, float]] = [
    # Reddit auto-generated patterns (very high confidence)
    (
        'reddit_auto_adjective_noun_number',
        r'^[A-Z][a-z]+_[A-Z][a-z]+_\d{3,4}$',
        0.85
    ),
    (
        'reddit_auto_word_word_digits',
        r'^[A-Z][a-z]{3,12}[A-Z][a-z]{3,12}\d{1,4}$',
        0.75
    ),

    # Word+Word+Number patterns (high confidence)
    (
        'camel_case_digits',
        r'^[A-Z][a-z]+[A-Z][a-z]+\d{2,4}$',
        0.70
    ),
    (
        'lowercase_words_digits',
        r'^[a-z]+_[a-z]+_\d{3,4}$',
        0.65
    ),
    (
        'two_words_underscore_digits',
        r'^[A-Za-z]+_[A-Za-z]+\d{2,4}$',
        0.60
    ),

    # Random alphanumeric patterns (medium-high confidence)
    (
        'random_chars_ending_digits',
        r'^[a-zA-Z]{6,12}\d{4,6}$',
        0.55
    ),
    (
        'mixed_case_random',
        r'^(?:[A-Z][a-z]){3,6}\d{2,4}$',
        0.50
    ),

    # Common spam patterns
    (
        'many_trailing_digits',
        r'^[a-zA-Z_]+\d{5,}$',
        0.75
    ),
    (
        'underscore_number_pattern',
        r'^[a-zA-Z]+_\d+_[a-zA-Z]+$',
        0.55
    ),
]

# Legitimate patterns that reduce suspicion (negative weights)
LEGITIMATE_PATTERNS: List[Tuple[str, str, float]] = [
    (
        'throwaway_explicit',
        r'^(?:throwaway|alt|anon|temp)\d*$',
        -0.30
    ),
    (
        'year_suffix',
        r'^[a-zA-Z_]+(?:19|20)\d{2}$',
        -0.20
    ),
    (
        'reddit_style_username',
        r'^[a-zA-Z][a-zA-Z0-9_-]{2,18}[a-zA-Z0-9]$',
        -0.10
    ),
]

# Spam-specific indicators (additional checks)
SPAM_INDICATORS: List[Tuple[str, str, float]] = [
    (
        'crypto_prefix',
        r'^(?:crypto|nft|btc|eth|doge|moon|coin)',
        0.25
    ),
    (
        'promo_prefix',
        r'^(?:promo|offer|deal|free|win|earn)',
        0.30
    ),
    (
        'repeated_chars',
        r'(.)\1{4,}',
        0.35
    ),
    (
        'excessive_underscores',
        r'_{3,}',
        0.20
    ),
    (
        'all_caps_word',
        r'^[A-Z]{4,}',
        0.15
    ),
]


def analyze_username(username: str) -> UsernameAnalysis:
    """
    Analyze a username for suspicious patterns.

    Args:
        username: Reddit username to analyze

    Returns:
        UsernameAnalysis with suspicion score and matched patterns
    """
    if not username or username == '[deleted]':
        return UsernameAnalysis(
            username=username or '',
            is_suspicious=False,
            confidence=0.0,
            details='Invalid or deleted username'
        )

    matched_patterns = []
    total_weight = 0.0

    # Check main suspicious patterns
    for name, pattern, weight in USERNAME_PATTERNS:
        if re.match(pattern, username, re.IGNORECASE):
            matched_patterns.append(name)
            total_weight += weight

    # Check spam indicators
    for name, pattern, weight in SPAM_INDICATORS:
        if re.search(pattern, username, re.IGNORECASE):
            matched_patterns.append(name)
            total_weight += weight

    # Check legitimate patterns (reduce suspicion)
    for name, pattern, weight in LEGITIMATE_PATTERNS:
        if re.match(pattern, username, re.IGNORECASE):
            matched_patterns.append(f'legitimate:{name}')
            total_weight += weight  # weight is negative

    # Normalize confidence to 0.0-1.0 range
    confidence = max(0.0, min(1.0, total_weight))

    # Consider suspicious if confidence >= 0.5
    is_suspicious = confidence >= 0.5

    # Build details string
    details = None
    if matched_patterns:
        suspicious_patterns = [p for p in matched_patterns if not p.startswith('legitimate:')]
        if suspicious_patterns:
            details = f"Matched: {', '.join(suspicious_patterns[:3])}"

    return UsernameAnalysis(
        username=username,
        is_suspicious=is_suspicious,
        confidence=confidence,
        matched_patterns=matched_patterns,
        details=details
    )


def batch_analyze_usernames(usernames: List[str]) -> List[UsernameAnalysis]:
    """
    Analyze multiple usernames for suspicious patterns.

    Args:
        usernames: List of Reddit usernames to analyze

    Returns:
        List of UsernameAnalysis results
    """
    return [analyze_username(username) for username in usernames]


def get_username_suspicion_score(username: str) -> float:
    """
    Quick helper to get just the suspicion score for a username.

    Args:
        username: Reddit username to check

    Returns:
        Suspicion confidence score (0.0 to 1.0)
    """
    analysis = analyze_username(username)
    return analysis.confidence
