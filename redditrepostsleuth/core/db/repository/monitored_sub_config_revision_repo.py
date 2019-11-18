from typing import Text

from redditrepostsleuth.core.db.databasemodels import MonitoredSubConfigRevision


class MonitoredSubConfigRevisionRepo:
    def __init__(self, db_session):
        self.db_session = db_session

    def add(self, revision: MonitoredSubConfigRevision):
        self.db_session.add(revision)

    def update(self, revision: MonitoredSubConfigRevision):
        self.db_session.update(revision)

    def get_by_revision_id(self, revision_id: Text) -> MonitoredSubConfigRevision:
        return self.db_session.query(MonitoredSubConfigRevision).filter(MonitoredSubConfigRevision.revision_id == revision_id).first()