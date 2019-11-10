from datetime import datetime
from typing import List

from redditrepostsleuth.core.logging import log
from redditrepostsleuth.core.db.databasemodels import RedditImagePostCurrent


class ImagePostCurrentRepository:
    def __init__(self, db_session):
        self.db_session = db_session

    def add(self, item):
        self.db_session.add(item)

    def get_all_without_created_at(self, limit: int = None):
        return self.db_session.query(RedditImagePostCurrent).filter(RedditImagePostCurrent.created_at > datetime(2019,11,1)).limit(limit).all()

    def get_by_id(self, id: int) -> RedditImagePostCurrent:
        return self.db_session.query(RedditImagePostCurrent).filter(RedditImagePostCurrent.id == id).first()

    def get_by_post_id(self, id: str) -> RedditImagePostCurrent:
        return self.db_session.query(RedditImagePostCurrent).filter(RedditImagePostCurrent.post_id == id).first()

    def page_by_id(self, id: int, limit: int = None):
        return self.db_session.query(RedditImagePostCurrent).filter(RedditImagePostCurrent.id > id).order_by(RedditImagePostCurrent.id).limit(limit).all()

    def bulk_save(self, items: List[RedditImagePostCurrent]):
        self.db_session.bulk_save_objects(items)

    def update(self, item: RedditImagePostCurrent):
        self.db_session.merge(item)

    def remove(self, item: RedditImagePostCurrent):
        log.debug('Deleting post %s', item.id)
        self.db_session.delete(item)