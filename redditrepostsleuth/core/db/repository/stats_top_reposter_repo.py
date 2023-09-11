from sqlalchemy import func

from redditrepostsleuth.core.db.databasemodels import StatsTopReposter


class StatTopReposterRepo:

    def __init__(self, db_session):
        self.db_session = db_session

    def add(self, item):
        self.db_session.add(item)

    def get_total_reposts_by_author_and_day_range(self, author: str, day_range: int) -> StatsTopReposter:
        res = self.db_session.query(func.sum(StatsTopReposter.repost_count)).filter(StatsTopReposter.author == author, StatsTopReposter.day_range == day_range).one()
        return res[0]
    def get_by_author_post_type_and_range(self, author: str, post_type_id: int, day_range: int) -> list[StatsTopReposter]:
        return self.db_session.query(StatsTopReposter).filter(StatsTopReposter.post_type_id == post_type_id,
                                                              StatsTopReposter.day_range == day_range,
                                                              StatsTopReposter.author == author).first()

    def get_by_post_type_and_range(self, post_type_id: int, day_range: int):
        return self.db_session.query(StatsTopReposter).filter(StatsTopReposter.day_range == day_range, StatsTopReposter.post_type_id == post_type_id).all()