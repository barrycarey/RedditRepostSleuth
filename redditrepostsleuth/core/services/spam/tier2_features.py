"""Tier 2 features dataclass for spam detection.

Contains features fetched from Reddit API (single Redditor object call)
and profile/comment scanning results.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional


@dataclass
class Tier2Features:
    """Container for Tier 2 (API-sourced) features.

    These features require Reddit API access to obtain:
    - Account info from Redditor object
    - Profile/comment scanning for adult and Telegram links
    """

    # Account info from Reddit API (single call)
    account_age_days: int = 0
    total_karma: int = 0
    post_karma: int = 0
    comment_karma: int = 0
    karma_per_day: float = 0.0
    has_verified_email: bool = False
    is_gold: bool = False
    has_custom_avatar: bool = False
    is_mod: bool = False
    account_suspended: bool = False

    # Profile/comment link scanning results
    has_adult_profile_links: bool = False
    has_telegram_links: bool = False
    profile_link_sources: Dict[str, List[str]] = field(default_factory=dict)

    # Metadata
    fetched_at: Optional[datetime] = None
    fetch_success: bool = True
    error_message: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            'account_age_days': self.account_age_days,
            'total_karma': self.total_karma,
            'post_karma': self.post_karma,
            'comment_karma': self.comment_karma,
            'karma_per_day': self.karma_per_day,
            'has_verified_email': self.has_verified_email,
            'is_gold': self.is_gold,
            'has_custom_avatar': self.has_custom_avatar,
            'is_mod': self.is_mod,
            'account_suspended': self.account_suspended,
            'has_adult_profile_links': self.has_adult_profile_links,
            'has_telegram_links': self.has_telegram_links,
            'profile_link_sources': self.profile_link_sources,
            'fetched_at': self.fetched_at.isoformat() if self.fetched_at else None,
            'fetch_success': self.fetch_success,
            'error_message': self.error_message,
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'Tier2Features':
        """Create instance from dictionary."""
        fetched_at = data.get('fetched_at')
        if fetched_at and isinstance(fetched_at, str):
            fetched_at = datetime.fromisoformat(fetched_at)

        return cls(
            account_age_days=data.get('account_age_days', 0),
            total_karma=data.get('total_karma', 0),
            post_karma=data.get('post_karma', 0),
            comment_karma=data.get('comment_karma', 0),
            karma_per_day=data.get('karma_per_day', 0.0),
            has_verified_email=data.get('has_verified_email', False),
            is_gold=data.get('is_gold', False),
            has_custom_avatar=data.get('has_custom_avatar', False),
            is_mod=data.get('is_mod', False),
            account_suspended=data.get('account_suspended', False),
            has_adult_profile_links=data.get('has_adult_profile_links', False),
            has_telegram_links=data.get('has_telegram_links', False),
            profile_link_sources=data.get('profile_link_sources', {}),
            fetched_at=fetched_at,
            fetch_success=data.get('fetch_success', True),
            error_message=data.get('error_message'),
        )

    @classmethod
    def suspended_user(cls, username: str, reason: str = None) -> 'Tier2Features':
        """Factory method for suspended/deleted user."""
        return cls(
            account_age_days=0,
            total_karma=0,
            post_karma=0,
            comment_karma=0,
            karma_per_day=0,
            has_verified_email=False,
            is_gold=False,
            has_custom_avatar=False,
            is_mod=False,
            account_suspended=True,
            fetched_at=datetime.utcnow(),
            fetch_success=True,
            error_message=reason or f"User {username} is suspended or deleted",
        )

    @classmethod
    def failed_fetch(cls, error_message: str) -> 'Tier2Features':
        """Factory method for failed fetch."""
        return cls(
            fetch_success=False,
            error_message=error_message,
            fetched_at=datetime.utcnow(),
        )

    def is_suspicious(self) -> bool:
        """Quick check if features indicate suspicious account."""
        suspicious_indicators = [
            self.account_suspended,
            self.account_age_days < 30 and self.total_karma < 100,
            self.karma_per_day < 0.5 and self.account_age_days > 90,
            not self.has_verified_email,
            self.has_telegram_links,
            self.has_adult_profile_links,
        ]
        # Account is suspicious if 3+ indicators are true
        return sum(suspicious_indicators) >= 3

    def get_suspicion_reasons(self) -> List[str]:
        """Get list of reasons why account might be suspicious."""
        reasons = []

        if self.account_suspended:
            reasons.append("Account is suspended")

        if self.account_age_days < 30:
            reasons.append(f"New account ({self.account_age_days} days old)")

        if self.total_karma < 100 and self.account_age_days > 7:
            reasons.append(f"Very low karma ({self.total_karma})")

        if self.karma_per_day < 0.5 and self.account_age_days > 90:
            reasons.append(f"Low karma rate ({self.karma_per_day:.2f}/day)")

        if not self.has_verified_email:
            reasons.append("No verified email")

        if not self.has_custom_avatar:
            reasons.append("Default avatar")

        if self.has_telegram_links:
            reasons.append("Has Telegram links")

        if self.has_adult_profile_links:
            reasons.append("Has adult platform links in profile")

        return reasons
