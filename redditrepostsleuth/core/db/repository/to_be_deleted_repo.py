from redditrepostsleuth.core.db.databasemodels import ToBeDeleted


class ToBeDeletedRepo:
    def __init__(self, db_session):
        self.db_session = db_session

    def add(self, item):
        self.db_session.add(item)

    def get_all(self, limit: int = None, offset: int = None):
        return self.db_session.query(ToBeDeleted).limit(limit).offset(offset).all()

    def remove(self, item):
        self.db_session.delete(item)