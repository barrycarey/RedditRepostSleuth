from typing import List

from sqlalchemy import DateTime

from redditrepostsleuth.common.logging import log
from redditrepostsleuth.db.model.post import Post


class PostRepository:
    def __init__(self, db_session):
        self.db_session = db_session
    def add(self, item):
        log.debug('Inserting: %s', item)
        self.db_session.add(item)

    def get_by_id(self, id: int) -> Post:
        return self.db_session.get(Post, id)

    def get_by_post_id(self, id: int) -> Post:
        return self.db_session.query(Post).filter(Post.post_id == id).first()

    def find_all_by_hash(self, hash_str: str, limit: int = None) -> List[Post]:
        query = self.db_session.query(Post).filter(Post.image_hash == hash_str, Post.post_type == 'image').limit(limit).all()
        return query

    def find_all_by_type(self, post_type: str, limit: int = None) -> List[Post]:
        return self.db_session.query(Post).filter(Post.post_type == post_type).limit(limit).all()

    def find_all_by_repost_check(self, repost_check: bool, limit: int = None):
        return self.db_session.query(Post).filter(Post.checked_repost == False, Post.post_type == 'image', Post.image_hash != None).order_by(Post.created_at.desc()).limit(limit).all()

    def find_all_older_posts(self, created: DateTime):
        return self.db_session.query(Post).filter(Post.created_at < created, Post.post_type == 'image').order_by(Post.created_at.desc()).all()

    def find_all_images_with_hash(self):
        return self.db_session.query(Post).filter(Post.image_hash != None).all()

    def remove(self, item: Post):
        self.db_session.delete(item)