from typing import List

from redditrepostsleuth.core.db.databasemodels import BannedSubreddit


class ToBeDeletedRepo:
    def __init__(self, db_session):
        self.db_session = db_session

    def add(self, item: BannedSubreddit):
        self.db_session.add(item)

    def get_all(self, limit: int = None, offset: int = None) -> List[BannedSubreddit]:
        return self.db_session.query(BannedSubreddit).limit(limit).offset(offset).all()

    def remove(self, item: BannedSubreddit):
        self.db_session.delete(item)

    def update(self, item: BannedSubreddit):
        self.db_session.merge(item)