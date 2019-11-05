from redditrepostsleuth.core.db.databasemodels import BotComment


class BotCommentRepo:
    def __init__(self, db_session):
        self.db_session = db_session

    def add(self, item: BotComment):
        self.db_session.add(item)

    def remove(self, item: BotComment):
        self.db_session.delete(item)