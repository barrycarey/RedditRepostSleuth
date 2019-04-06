from typing import List

from sqlalchemy import DateTime, or_, func
from datetime import datetime, timedelta
from redditrepostsleuth.common.logging import log
from redditrepostsleuth.model.db.databasemodels import Post, ImagePost


class ImagePostRepository:
    def __init__(self, db_session):
        self.db_session = db_session

    def add(self, item):
        self.db_session.add(item)

    def page_by_id(self, id: int, limit: int = None):
        return self.db_session.query(ImagePost).filter(ImagePost.id > id).order_by(ImagePost.id).limit(limit).all()

    def bulk_save(self, items: List[ImagePost]):
        self.db_session.bulk_save_objects(items)

    def update(self, item: ImagePost):
        self.db_session.merge(item)

    def remove(self, item: ImagePost):
        log.debug('Deleting post %s', item.id)
        self.db_session.delete(item)

    def find_all_images_with_hash_return_id_hash(self, limit: int = None, id: int = 0):
        return self.db_session.query(ImagePost).filter(ImagePost.id > id).with_entities(ImagePost.id, ImagePost.dhash_h).limit(limit).all()