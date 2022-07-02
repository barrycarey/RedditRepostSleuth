from datetime import datetime
from typing import List

from redditrepostsleuth.core.db.databasemodels import ImagePost
from redditrepostsleuth.core.logging import log


class ImagePostRepository:
    def __init__(self, db_session):
        self.db_session = db_session

    def add(self, item):
        self.db_session.add(item)

    def get_all(self, limit: int = None, offset: int = None) -> List[ImagePost]:
        return self.db_session.query(ImagePost).order_by(ImagePost.id.desc()).limit(limit).offset(offset).all()

    def get_all_without_created_at(self, limit: int = None):
        return self.db_session.query(ImagePost).filter(ImagePost.created_at > datetime(2019,11,1)).limit(limit).all()

    def get_by_id(self, id: int) -> ImagePost:
        return self.db_session.query(ImagePost).filter(ImagePost.id == id).first()

    def get_by_post_id(self, id: str) -> ImagePost:
        return self.db_session.query(ImagePost).filter(ImagePost.post_id == id).first()

    def get_after_date(self, date: datetime) -> List[ImagePost]:
        return self.db_session.query(ImagePost).filter(ImagePost.created_at > date).all()

    def get_before_date(self, date: datetime) -> List[ImagePost]:
        return self.db_session.query(ImagePost).filter(ImagePost.created_at < date).all()

    def page_by_id(self, id: int, limit: int = None) -> List[ImagePost]:
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