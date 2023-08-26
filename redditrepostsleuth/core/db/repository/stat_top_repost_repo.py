from typing import List

from redditrepostsleuth.core.db.databasemodels import StatsTopRepost


class StatTopRepostRepo:
    def __init__(self, db_session):
        self.db_session = db_session
    def add(self, item):
        self.db_session.add(item)

    def get_all(self, day_range: int, nsfw: bool = False) -> list[StatsTopRepost]:
        return self.db_session.query(StatsTopRepost).filter(StatsTopRepost.post_type_id == 2, StatsTopRepost.day_range == day_range, StatsTopRepost.nsfw == nsfw).all()