from typing import Text

from redditrepostsleuth.core.db.databasemodels import MonitoredSubConfigRevision, MonitoredSubConfigChange


class MonitoredSubConfigChangeRepo:
    def __init__(self, db_session):
        self.db_session = db_session

    def add(self, revision: MonitoredSubConfigChange):
        self.db_session.add(revision)

    def update(self, revision: MonitoredSubConfigChange):
        self.db_session.update(revision)

    def get_all_by_subreddit(self, subreddit: Text, limit: int = None, offset: int = None):
        return self.db_session.query(MonitoredSubConfigChange).filter(
            MonitoredSubConfigChange.subreddit == subreddit).order_by(MonitoredSubConfigChange.updated_at.desc()).limit(
            limit).offset(offset).all()