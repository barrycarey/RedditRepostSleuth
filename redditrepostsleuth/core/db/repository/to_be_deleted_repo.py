from typing import List

from redditrepostsleuth.core.db.databasemodels import ToBeDeleted


class ToBeDeletedRepo:
    def __init__(self, db_session):
        self.db_session = db_session

    def add(self, item: ToBeDeleted):
        self.db_session.add(item)

    def get_all(self, limit: int = None, offset: int = None) -> List[ToBeDeleted]:
        return self.db_session.query(ToBeDeleted).limit(limit).offset(offset).all()

    def remove(self, item: ToBeDeleted):
        self.db_session.delete(item)

    def update(self, item: ToBeDeleted):
        self.db_session.merge(item)