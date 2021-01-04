from typing import List

from redditrepostsleuth.core.db.databasemodels import MonitoredSub


class MonitoredSubRepository:
    def __init__(self, db_session):
        self.db_session = db_session

    def add(self, item):
        self.db_session.add(item)

    def get_all(self, limit: int = None) -> List[MonitoredSub]:
        return self.db_session.query(MonitoredSub).order_by(MonitoredSub.subscribers.desc()).limit(limit).all()

    def get_all_active(self, limit: int = None) -> List[MonitoredSub]:
        return self.db_session.query(MonitoredSub).filter(MonitoredSub.active == True).order_by(MonitoredSub.subscribers.desc()).limit(limit).all()

    def get_by_id(self, id: int) -> MonitoredSub:
        return self.db_session.query(MonitoredSub).filter(MonitoredSub.id == id).first()

    def get_by_sub(self, sub: str) -> MonitoredSub:
        return self.db_session.query(MonitoredSub).filter(MonitoredSub.name == sub).first()

    def update(self, item: MonitoredSub):
        self.db_session.merge(item)

    def remove(self, item: MonitoredSub):
        self.db_session.delete(item)

    def refresh(self, item: MonitoredSub):
        self.db_session.refresh(item)