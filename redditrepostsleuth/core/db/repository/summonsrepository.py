from typing import List

from sqlalchemy import func

from redditrepostsleuth.core.logging import log
from redditrepostsleuth.core.db.databasemodels import Summons


class SummonsRepository:
    def __init__(self, db_session):
        self.db_session = db_session
    def add(self, item):
        log.debug('Inserting: %s', item)
        self.db_session.add(item)

    def get_all(self) -> List[Summons]:
        return self.db_session.query(Summons).all()

    def get_by_post_id(self, post_id) -> List[Summons]:
        return self.db_session.query(Summons).filter(Summons.post_id == post_id).all()

    def get_by_id(self, id: int) -> Summons:
        result = self.db_session.query(Summons).filter(Summons.id == id).first()
        return result

    def get_by_comment_id(self, id: str) -> Summons:
        return self.db_session.query(Summons).filter(Summons.comment_id == id).first()

    def get_unreplied(self, limit: int = 10) -> Summons:
        return self.db_session.query(Summons).filter(Summons.summons_replied_at == None).order_by(Summons.summons_received_at.desc()).limit(limit).all()

    def get_count(self):
        r = self.db_session.query(func.count(Summons.id)).first()
        return r[0] if r else None

    def remove(self, item: Summons):
        self.db_session.delete(item)