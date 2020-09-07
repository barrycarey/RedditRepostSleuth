from typing import Text

from redditrepostsleuth.core.db.databasemodels import BannedSubreddit


class BannedSubredditRepo:
    def __init__(self, db_session):
        self.db_session = db_session

    def add(self, item):
        self.db_session.add(item)

    def get_by_subreddit(self, name: Text) -> BannedSubreddit:
        return self.db_session.query(BannedSubreddit).filter(BannedSubreddit.subreddit == name).first()

    def get_all(self, limit: int = None, offset: int = None):
        return self.db_session.query(BannedSubreddit).order_by(BannedSubreddit.subreddit).limit(limit).offset(offset).all()

    def remove(self, item):
        self.db_session.delete(item)