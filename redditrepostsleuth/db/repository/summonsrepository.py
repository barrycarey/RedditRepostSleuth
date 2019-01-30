from redditrepostsleuth.common.logging import log
from redditrepostsleuth.model.db.databasemodels import Summons


class SummonsRepository:
    def __init__(self, db_session):
        self.db_session = db_session
    def add(self, item):
        log.debug('Inserting: %s', item)
        self.db_session.add(item)

    def get_by_id(self, id: int) -> Summons:
        return self.db_session.get(Summons, id)

    def get_by_comment_id(self, id: str) -> Summons:
        return self.db_session.query(Summons).filter(Summons.comment_id == id).first()