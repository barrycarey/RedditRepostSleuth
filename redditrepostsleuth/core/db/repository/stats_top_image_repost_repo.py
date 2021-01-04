from typing import Text

from redditrepostsleuth.core.db.databasemodels import StatsTopImageRepost


class StatsTopImageRepostRepo:
    def __init__(self, db_session):
        self.db_session = db_session

    def get_all(self, days: int = 7, nsfw: bool = False):
        return self.db_session.query(StatsTopImageRepost).filter(StatsTopImageRepost.days == days, StatsTopImageRepost.nsfw == nsfw).order_by(StatsTopImageRepost.repost_count.desc()).all()

    def get_by_post_id_and_days(self, post_id: Text, days: int):
        return self.db_session.query(StatsTopImageRepost).filter(StatsTopImageRepost.post_id == post_id, StatsTopImageRepost.days == days).first()

    def add(self, item: StatsTopImageRepost):
        self.db_session.add(item)