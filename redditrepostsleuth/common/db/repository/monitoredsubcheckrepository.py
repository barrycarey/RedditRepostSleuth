from redditrepostsleuth.common.model.db.databasemodels import MonitoredSubChecks


class MonitoredSubCheckRepository:
    def __init__(self, db_session):
        self.db_session = db_session

    def add(self, item):
        self.db_session.add(item)

    def get_by_id(self, id: str) -> MonitoredSubChecks:
        return self.db_session.query(MonitoredSubChecks).filter(MonitoredSubChecks.post_id == id).first()

    def remove(self, item: MonitoredSubChecks):
        self.db_session.delete(item)