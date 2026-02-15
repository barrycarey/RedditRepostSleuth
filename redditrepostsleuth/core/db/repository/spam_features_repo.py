from datetime import datetime, timedelta
from typing import List, Optional, Tuple

from redditrepostsleuth.core.db.databasemodels import UserSpamFeatures


class SpamFeaturesRepo:

    def __init__(self, db_session):
        self.db_session = db_session

    def add(self, item: UserSpamFeatures):
        self.db_session.add(item)

    def get_by_username(self, username: str) -> Optional[UserSpamFeatures]:
        return self.db_session.query(UserSpamFeatures).filter(
            UserSpamFeatures.username == username
        ).first()

    def get_by_usernames(self, usernames: List[str]) -> List[UserSpamFeatures]:
        """Batch lookup spam features for multiple usernames."""
        if not usernames:
            return []
        return self.db_session.query(UserSpamFeatures).filter(
            UserSpamFeatures.username.in_(usernames)
        ).all()

    def get_all(self, limit: int = None) -> List[UserSpamFeatures]:
        query = self.db_session.query(UserSpamFeatures)
        if limit:
            query = query.limit(limit)
        return query.all()

    def get_high_spam_scores(self, threshold: float = 0.7, limit: int = 100) -> List[UserSpamFeatures]:
        """Get users with spam scores above the threshold."""
        return self.db_session.query(UserSpamFeatures).filter(
            UserSpamFeatures.spam_score >= threshold
        ).order_by(UserSpamFeatures.spam_score.desc()).limit(limit).all()


    def get_high_spam_scores_paginated(
        self,
        threshold: float = 0.60,
        limit: int = 20,
        offset: int = 0
    ) -> Tuple[List[UserSpamFeatures], int]:
        """
        Get users with spam scores at or above threshold with pagination.

        Returns:
            Tuple of (list of UserSpamFeatures, total count matching threshold)
        """
        base_query = self.db_session.query(UserSpamFeatures).filter(
            UserSpamFeatures.spam_score >= threshold
        )

        total = base_query.count()

        results = base_query.order_by(
            UserSpamFeatures.spam_score.desc()
        ).offset(offset).limit(limit).all()

        return results, total

    def get_stale_features(self, older_than: datetime, limit: int = 100) -> List[UserSpamFeatures]:
        """Get features that need recomputation."""
        return self.db_session.query(UserSpamFeatures).filter(
            UserSpamFeatures.computed_at < older_than
        ).order_by(UserSpamFeatures.computed_at.asc()).limit(limit).all()

    def update_or_create(self, username: str, **kwargs) -> UserSpamFeatures:
        """Update existing features or create new record."""
        existing = self.get_by_username(username)
        if existing:
            for key, value in kwargs.items():
                if hasattr(existing, key):
                    setattr(existing, key, value)
            existing.computed_at = datetime.utcnow()
            return existing
        else:
            new_features = UserSpamFeatures(username=username, **kwargs)
            self.add(new_features)
            return new_features

    def delete_by_username(self, username: str) -> bool:
        """Delete features for a user. Returns True if deleted."""
        result = self.db_session.query(UserSpamFeatures).filter(
            UserSpamFeatures.username == username
        ).delete(synchronize_session=False)
        return result > 0

    def user_was_recently_analyzed(self, username: str, within_days: int = 7) -> bool:
        """Check if user was analyzed within the specified number of days."""
        cutoff = datetime.utcnow() - timedelta(days=within_days)
        result = self.db_session.query(UserSpamFeatures).filter(
            UserSpamFeatures.username == username,
            UserSpamFeatures.computed_at >= cutoff
        ).first()
        return result is not None

    def delete_old_records(self, username: str, keep_count: int) -> int:
        """
        Delete old feature records for a user, keeping the most recent ones.
        Note: UserSpamFeatures uses username as PK, so this is a no-op if only one record per user.
        """
        # Currently UserSpamFeatures has username as unique PK - one record per user
        return 0

    def get_users_needing_tier2_enrichment(
        self,
        limit: int = 50,
        min_tier1_score: float = 0.0
    ) -> List[UserSpamFeatures]:
        """
        Get users that have Tier 1 features but no Tier 2 enrichment.

        Args:
            limit: Maximum users to return
            min_tier1_score: Minimum spam score to be considered for enrichment

        Returns:
            List of UserSpamFeatures needing Tier 2 enrichment
        """
        return self.db_session.query(UserSpamFeatures).filter(
            UserSpamFeatures.tier2_enriched_at.is_(None),
            UserSpamFeatures.tier2_enrichment_failed.is_(False),
            UserSpamFeatures.spam_score >= min_tier1_score
        ).order_by(
            UserSpamFeatures.spam_score.desc()
        ).limit(limit).all()

    def get_high_risk_unenriched(
        self,
        min_score: float = 0.5,
        limit: int = 50
    ) -> List[UserSpamFeatures]:
        """
        Get high-risk users that haven't had Tier 2 enrichment yet.

        Args:
            min_score: Minimum spam score to qualify
            limit: Maximum users to return

        Returns:
            List of high-risk users without Tier 2 data
        """
        return self.db_session.query(UserSpamFeatures).filter(
            UserSpamFeatures.spam_score >= min_score,
            UserSpamFeatures.account_age_days.is_(None),
            UserSpamFeatures.tier2_enrichment_failed.is_(False)
        ).order_by(
            UserSpamFeatures.spam_score.desc()
        ).limit(limit).all()

    def update_tier2_features(
        self,
        username: str,
        account_age_days: int = None,
        total_karma: int = None,
        post_karma: int = None,
        comment_karma: int = None,
        karma_per_day: float = None,
        has_verified_email: bool = None,
        is_gold: bool = None,
        has_custom_avatar: bool = None,
        account_suspended: bool = None,
        has_adult_profile_links: bool = None,
        has_telegram_links: bool = None,
        profile_link_sources: dict = None,
        has_promotional_post_links: bool = None,
        detected_platforms: list = None
    ) -> Optional[UserSpamFeatures]:
        """
        Update Tier 2 features for a user.

        Args:
            username: Reddit username
            **kwargs: Tier 2 feature values

        Returns:
            Updated UserSpamFeatures or None if user not found
        """
        features = self.get_by_username(username)
        if not features:
            return None

        if account_age_days is not None:
            features.account_age_days = account_age_days
        if total_karma is not None:
            features.total_karma = total_karma
        if post_karma is not None:
            features.post_karma = post_karma
        if comment_karma is not None:
            features.comment_karma = comment_karma
        if karma_per_day is not None:
            features.karma_per_day = karma_per_day
        if has_verified_email is not None:
            features.has_verified_email = has_verified_email
        if is_gold is not None:
            features.is_gold = is_gold
        if has_custom_avatar is not None:
            features.has_custom_avatar = has_custom_avatar
        if account_suspended is not None:
            features.account_suspended = account_suspended
        if has_adult_profile_links is not None:
            features.has_adult_profile_links = has_adult_profile_links
        if has_telegram_links is not None:
            features.has_telegram_links = has_telegram_links
        if profile_link_sources is not None:
            features.profile_link_sources = profile_link_sources
        if has_promotional_post_links is not None:
            features.has_promotional_post_links = has_promotional_post_links

        # Merge detected_platforms into feature_data
        if detected_platforms:
            if features.feature_data is None:
                features.feature_data = {}
            # Merge with existing platforms (in case of re-enrichment)
            existing = features.feature_data.get('detected_platforms', [])
            merged = list(set(existing + detected_platforms))
            features.feature_data = {**features.feature_data, 'detected_platforms': merged}

        features.tier2_enriched_at = datetime.utcnow()
        features.tier2_enrichment_failed = False
        features.tier2_failure_reason = None

        return features

    def mark_tier2_enrichment_failed(
        self,
        username: str,
        reason: str
    ) -> Optional[UserSpamFeatures]:
        """
        Mark Tier 2 enrichment as failed for a user.

        Args:
            username: Reddit username
            reason: Failure reason (truncated to 200 chars)

        Returns:
            Updated UserSpamFeatures or None if user not found
        """
        features = self.get_by_username(username)
        if not features:
            return None

        features.tier2_enrichment_failed = True
        features.tier2_failure_reason = reason[:200] if reason else None
        features.tier2_enriched_at = datetime.utcnow()

        return features

    def get_suspended_users(self, limit: int = 100) -> List[UserSpamFeatures]:
        """Get users that have been marked as suspended."""
        return self.db_session.query(UserSpamFeatures).filter(
            UserSpamFeatures.account_suspended.is_(True)
        ).order_by(
            UserSpamFeatures.tier2_enriched_at.desc()
        ).limit(limit).all()

    def get_users_with_telegram_links(self, limit: int = 100) -> List[UserSpamFeatures]:
        """Get users that have Telegram links detected."""
        return self.db_session.query(UserSpamFeatures).filter(
            UserSpamFeatures.has_telegram_links.is_(True)
        ).order_by(
            UserSpamFeatures.tier2_enriched_at.desc()
        ).limit(limit).all()

    def update_comment_features(
        self,
        username: str,
        comment_features: dict
    ) -> Optional[UserSpamFeatures]:
        """
        Update comment analysis results for a user.

        Args:
            username: Reddit username
            comment_features: Dict of comment analysis metrics (stored as JSON)

        Returns:
            Updated UserSpamFeatures or None if user not found
        """
        features = self.get_by_username(username)
        if not features:
            return None

        features.comment_features = comment_features
        features.comment_analysis_at = datetime.utcnow()

        return features
