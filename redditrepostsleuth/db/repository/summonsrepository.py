from sqlalchemy import func

from redditrepostsleuth.common.logging import log
from redditrepostsleuth.model.db.databasemodels import Summons


class SummonsRepository:
    def __init__(self, db_session):
        self.db_session = db_session
    def add(self, item):
        log.debug('Inserting: %s', item)
        self.db_session.add(item)

    def get_by_id(self, id: int) -> Summons:
        result = self.db_session.query(Summons).filter(Summons.id == id).first()
        return result

    def get_by_comment_id(self, id: str) -> Summons:
        return self.db_session.query(Summons).filter(Summons.comment_id == id).first()

    def get_unreplied(self) -> Summons:
        return self.db_session.query(Summons).filter(Summons.summons_replied_at == None).all()

    def get_count(self):
        r = self.db_session.query(func.count(Summons.id)).first()
        return r[0] if r else None