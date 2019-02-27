from typing import List

from sqlalchemy import func

from redditrepostsleuth.common.logging import log
from redditrepostsleuth.model.db.databasemodels import ImageRepost


class ImageRepostRepository:

    def __init__(self, db_session):
        self.db_session = db_session

    def get_by_id(self, id: int) -> ImageRepost:
        return self.db_session.query(ImageRepost).filter(ImageRepost.id == id).first

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