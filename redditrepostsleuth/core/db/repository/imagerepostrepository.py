from typing import List, Text

from sqlalchemy import func
from datetime import timedelta, datetime
from redditrepostsleuth.core.logging import log
from redditrepostsleuth.core.db.databasemodels import ImageRepost


class ImageRepostRepository:

    def __init__(self, db_session):
        self.db_session = db_session

    def get_all(self):
        return self.db_session.query(ImageRepost).all()

    def get_by_id(self, id: int) -> ImageRepost:
        return self.db_session.query(ImageRepost).filter(ImageRepost.id == id).first()

    def get_dups_by_post_id(self, post_id: str) -> ImageRepost:
        return self.db_session.query(ImageRepost).filter(ImageRepost.post_id == post_id).all()

    def get_by_repost_of(self, post_id: Text) -> List[ImageRepost]:
        return self.db_session.query(ImageRepost).filter(ImageRepost.repost_of == post_id).all()

    def get_count(self):
        r = self.db_session.query(func.count(ImageRepost.id)).first()
        return r[0] if r else None

    def add(self, item):
        log.debug('Inserting: %s', item)
        self.db_session.add(item)

    def bulk_save(self, items: List[ImageRepost]):
        self.db_session.bulk_save_objects(items)

    def update(self, item: ImageRepost):
        self.db_session.merge(item)

    def get_top_last_over_days(self, days: int):
        oldest = datetime.utcnow() - timedelta(days=days)
        return self.db_session.query(ImageRepost).filter(ImageRepost.detected_at > oldest, )

    def remove(self, item: ImageRepost):
        log.debug('Deleting post %s', item.id)
        self.db_session.delete(item)