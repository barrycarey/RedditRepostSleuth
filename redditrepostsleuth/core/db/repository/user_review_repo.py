from typing import List, Optional

from sqlalchemy import desc

from redditrepostsleuth.core.db.databasemodels import UserReview


class UserReviewRepo:

    def __init__(self, db_session):
        self.db_session = db_session

    def add(self, item: UserReview):
        self.db_session.add(item)

    def get_all(self, limit: int = None) -> list[UserReview]:
        return self.db_session.query(UserReview).limit(limit).all()

    def get_all_unchecked(self, limit: int = None) -> list[UserReview]:
        return self.db_session.query(UserReview).filter(UserReview.last_checked == None).limit(limit).all()

    def get_by_username(self, username: str) -> Optional[UserReview]:
        return self.db_session.query(UserReview).filter(UserReview.username == username).first()

    def get_high_risk_users(
        self,
        min_score: float = 0.6,
        limit: int = 100
    ) -> List[UserReview]:
        """Get users with high spam scores for review."""
        return self.db_session.query(UserReview).filter(
            UserReview.spam_score >= min_score
        ).order_by(
            desc(UserReview.spam_score)
        ).limit(limit).all()

    def get_users_needing_review(self, limit: int = 100) -> List[UserReview]:
        """Get users flagged for review but not yet verified."""
        return self.db_session.query(UserReview).filter(
            UserReview.spam_score >= 0.6,
            UserReview.is_verified_spam == False,
            UserReview.is_verified_legit == False
        ).order_by(
            desc(UserReview.spam_score)
        ).limit(limit).all()

    def mark_verified_spam(self, username: str) -> bool:
        """Mark a user as verified spam after manual review."""
        updated = self.db_session.query(UserReview).filter(
            UserReview.username == username
        ).update({
            'is_verified_spam': True,
            'is_verified_legit': False
        })
        return updated > 0

    def mark_verified_legit(self, username: str) -> bool:
        """Mark a user as verified legitimate after manual review."""
        updated = self.db_session.query(UserReview).filter(
            UserReview.username == username
        ).update({
            'is_verified_spam': False,
            'is_verified_legit': True
        })
        return updated > 0

    def get_verified_spam_users(self, limit: int = 100) -> List[UserReview]:
        """Get users verified as spam (for training data)."""
        return self.db_session.query(UserReview).filter(
            UserReview.is_verified_spam == True
        ).order_by(
            desc(UserReview.spam_score)
        ).limit(limit).all()

    def get_verified_legit_users(self, limit: int = 100) -> List[UserReview]:
        """Get users verified as legitimate (for training data)."""
        return self.db_session.query(UserReview).filter(
            UserReview.is_verified_legit == True
        ).limit(limit).all()