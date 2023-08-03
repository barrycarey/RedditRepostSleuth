from typing import List

from redditrepostsleuth.core.db.databasemodels import StatsTopRepost


class StatTopRepostRepo:
    def __init__(self, db_session):
        self.db_session = db_session
    def add(self, item):
        self.db_session.add(item)

    def get_top_image_all_time(self, limit: int = 100, nsfw: bool = False) -> List[StatsTopRepost]:
        query = self.db_session.query(StatsTopRepost).filter(StatsTopRepost.post_type == 2)
        if not nsfw:
            query = query.filter(StatsTopRepost.nsfw == False)
        return query.order_by(StatsTopRepost.total_count.desc()).limit(limit).all()

    def get_top_image_1_day(self, limit: int = 100, nsfw: bool = False) -> List[StatsTopRepost]:
        query = self.db_session.query(StatsTopRepost).filter(StatsTopRepost.post_type == 2)
        if not nsfw:
            query = query.filter(StatsTopRepost.nsfw == False)
        return query.order_by(StatsTopRepost.day_count_1.desc()).limit(limit).all()

    def get_top_image_7_day(self, limit: int = 100, nsfw: bool = False) -> List[StatsTopRepost]:
        query = self.db_session.query(StatsTopRepost).filter(StatsTopRepost.post_type == 2)
        if not nsfw:
            query = query.filter(StatsTopRepost.nsfw == False)
        return query.order_by(StatsTopRepost.day_count_7.desc()).limit(limit).all()

    def get_top_image_30_day(self, limit: int = 100, nsfw: bool = False) -> List[StatsTopRepost]:
        query = self.db_session.query(StatsTopRepost).filter(StatsTopRepost.post_type == 2)
        if not nsfw:
            query = query.filter(StatsTopRepost.nsfw == False)
        return query.order_by(StatsTopRepost.day_count_30.desc()).limit(limit).all()

    def get_top_image_365_day(self, limit: int = 100, nsfw: bool = False) -> List[StatsTopRepost]:
        query = self.db_session.query(StatsTopRepost).filter(StatsTopRepost.post_type == 2)
        if not nsfw:
            query = query.filter(StatsTopRepost.nsfw == False)
        return query.order_by(StatsTopRepost.day_count_365.desc()).limit(limit).all()