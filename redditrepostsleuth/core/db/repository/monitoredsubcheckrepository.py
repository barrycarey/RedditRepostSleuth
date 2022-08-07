from datetime import datetime, timedelta
from typing import Text

from sqlalchemy import func

from redditrepostsleuth.core.db.databasemodels import MonitoredSubChecks


class MonitoredSubCheckRepository:
    def __init__(self, db_session):
        self.db_session = db_session

    def add(self, item):
        self.db_session.add(item)

    def get_by_id(self, id: int) -> MonitoredSubChecks:
        return self.db_session.query(MonitoredSubChecks).filter(MonitoredSubChecks.post_id == id).first()

    def get_by_subreddit(self, monitored_sub_id: int, limit: int = 20, offset: int = None):
        return self.db_session.query(MonitoredSubChecks).filter(MonitoredSubChecks.monitored_sub_id == monitored_sub_id).order_by(MonitoredSubChecks.checked_at.desc()).limit(limit).offset(offset).all()

    def remove(self, item: MonitoredSubChecks):
        self.db_session.delete(item)

    def get_count_by_subreddit(self, monitored_sub_id: int, hours: int = None):
        query = self.db_session.query(func.count(MonitoredSubChecks.id)).filter(MonitoredSubChecks.monitored_sub_id == monitored_sub_id)
        if hours:
            query = query.filter(MonitoredSubChecks.checked_at > (datetime.now() - timedelta(hours=hours)))
        return query.first()