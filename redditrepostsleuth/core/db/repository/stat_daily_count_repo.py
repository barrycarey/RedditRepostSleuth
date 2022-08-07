from typing import List

from redditrepostsleuth.core.db.databasemodels import StatsDailyCount


class StatDailyCountRepo:
    def __init__(self, db_session):
        self.db_session = db_session

    def get_all(self, limit: int = None) -> List[StatsDailyCount]:
        return self.db_session.query(StatsDailyCount).order_by(StatsDailyCount.date.desc()).limit(limit).all()