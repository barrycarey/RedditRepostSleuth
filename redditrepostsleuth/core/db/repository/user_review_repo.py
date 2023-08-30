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

    def get_by_username(self, username: str) -> UserReview:
        return self.db_session.query(UserReview).filter(UserReview.username == username).first()