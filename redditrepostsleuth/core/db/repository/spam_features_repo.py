from datetime import datetime
from typing import List, Optional

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
