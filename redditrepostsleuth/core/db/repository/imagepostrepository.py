from typing import List

from redditrepostsleuth.core.logging import log
from redditrepostsleuth.core.db.databasemodels import RedditImagePost


class ImagePostRepository:
    def __init__(self, db_session):
        self.db_session = db_session

    def add(self, item):
        self.db_session.add(item)

    def get_all_without_created_at(self, limit: int = None):
        return self.db_session.query(RedditImagePost).filter(RedditImagePost.created_at == None).limit(limit).all()

    def get_by_id(self, id: int) -> RedditImagePost:
        return self.db_session.query(RedditImagePost).filter(RedditImagePost.id == id).first()

    def get_by_post_id(self, id: str) -> RedditImagePost:
        return self.db_session.query(RedditImagePost).filter(RedditImagePost.post_id == id).first()

    def page_by_id(self, id: int, limit: int = None):
        return self.db_session.query(RedditImagePost).filter(RedditImagePost.id > id).order_by(RedditImagePost.id).limit(limit).all()

    def bulk_save(self, items: List[RedditImagePost]):
        self.db_session.bulk_save_objects(items)

    def update(self, item: RedditImagePost):
        self.db_session.merge(item)

    def remove(self, item: RedditImagePost):
        log.debug('Deleting post %s', item.id)
        self.db_session.delete(item)

    def find_all_images_with_hash_return_id_hash(self, limit: int = None, id: int = 0):
        return self.db_session.query(RedditImagePost).filter(RedditImagePost.id > id).with_entities(RedditImagePost.id, RedditImagePost.dhash_h).limit(limit).all()