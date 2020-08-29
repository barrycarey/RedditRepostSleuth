from typing import Text

from redditrepostsleuth.core.db.databasemodels import MonitoredSubChecks


class MonitoredSubCheckRepository:
    def __init__(self, db_session):
        self.db_session = db_session

    def add(self, item):
        self.db_session.add(item)

    def get_by_id(self, id: str) -> MonitoredSubChecks:
        return self.db_session.query(MonitoredSubChecks).filter(MonitoredSubChecks.post_id == id).first()

    def get_by_subreddit(self, subreddit: Text, limit: int = 20, offset: int = None):
        return self.db_session.query(MonitoredSubChecks).filter(MonitoredSubChecks.subreddit == subreddit).order_by(MonitoredSubChecks.checked_at.desc()).limit(limit).offset(offset).all()

    def remove(self, item: MonitoredSubChecks):
        self.db_session.delete(item)