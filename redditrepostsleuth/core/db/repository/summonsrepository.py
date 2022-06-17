from datetime import datetime, timedelta
from typing import List, Text, Optional

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

    def get_by_user_interval(self, user: Text, interval_hours: int = 1) -> Optional[List[Summons]]:
        since = datetime.now() - timedelta(hours=interval_hours)
        return self.db_session.query(Summons).filter(Summons.requestor == user, Summons.summons_received_at > since).all()

    def get_by_comment_id(self, id: str) -> Summons:
        return self.db_session.query(Summons).filter(Summons.comment_id == id).first()

    def get_unreplied(self, limit: int = 10) -> Summons:
        return self.db_session.query(Summons).filter(Summons.summons_replied_at == None).order_by(Summons.summons_received_at.desc()).limit(limit).all()

    def get_count(self, hours: int = None):
        query = self.db_session.query(func.count(Summons.id))
        if hours:
            query = query.filter(Summons.summons_received_at > (datetime.now() - timedelta(hours=hours)))
        r = query.first()
        return r[0] if r else None

    def get_count_by_subreddit(self, subreddit: Text, hours: int = None):
        query = self.db_session.query(func.count(Summons.id)).filter(Summons.subreddit == subreddit)
        if hours:
            query = query.filter(Summons.summons_received_at > (datetime.now() - timedelta(hours=hours)))
        return query.first()

    def remove(self, item: Summons):
        self.db_session.delete(item)