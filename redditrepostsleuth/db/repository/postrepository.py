from typing import List

from sqlalchemy import DateTime, or_, func
from datetime import datetime, timedelta
from redditrepostsleuth.common.logging import log
from redditrepostsleuth.model.db.databasemodels import Post


class PostRepository:
    def __init__(self, db_session):
        self.db_session = db_session

    def add(self, item):
        log.debug('Inserting: %s', item)
        self.db_session.add(item)

    def bulk_save(self, items: List[Post]):
        self.db_session.bulk_save_objects(items)

    def update(self, item: Post):
        self.db_session.merge(item)

    def page_by_id(self, id: int, limit: int = None):
        return self.db_session.query(Post).filter(Post.id > id).order_by(Post.id).limit(limit).all()

    def get_all(self, limit: int = None, offset: int = None):
        return self.db_session.query(Post).filter(Post.ingested_from == 'praw').order_by(Post.id.desc()).offset(offset).limit(limit).all()

    def get_newest_praw(self):
        return self.db_session.query(Post).filter(Post.ingested_from == 'praw').order_by(Post.id.desc()).first()

    def get_oldest_post(self, limit: int = None):
        return self.db_session.query(Post).order_by(Post.created_at).first()

    def get_by_id(self, id: int) -> Post:
        return self.db_session.query(Post).filter(Post.id == id).first()

    def get_by_post_id(self, id: str) -> Post:
        #log.debug('Looking up post with ID %s', id)
        return self.db_session.query(Post).filter(Post.post_id == id).first()

    def find_all_by_url(self, url: str, limit: int = None):
        return self.db_session.query(Post).filter(Post.url == url).limit(limit).all()

    def find_all_by_url_hash(self, hash: str, limit: int = None):
        return self.db_session.query(Post).filter(Post.url_hash == hash).limit(limit).all()

    def find_all_by_type(self, post_type: str, limit: int = None, offset: int = None) -> List[Post]:
        return self.db_session.query(Post).filter(Post.post_type == post_type).order_by(Post.id.desc()).offset(offset).limit(limit).all()

    def find_all_by_repost_check(self, repost_check: bool, limit: int = None, offset: int = None):
        return self.db_session.query(Post).filter(Post.checked_repost == repost_check, Post.post_type == 'image', Post.crosspost_parent == None, Post.dhash_h != None).offset(offset).limit(limit).all()

    def find_all_for_delete_check(self, hours: int, limit: int = None, offset: int = None) -> List[Post]:
        since = datetime.now() - timedelta(hours=hours)
        return self.db_session.query(Post).filter(Post.last_deleted_check < since).offset(offset).limit(limit).all()

    def no_selftext(self, limit: int, offset: int):
        return self.db_session.query(Post).filter(Post.post_type == 'text', Post.selftext == None).offset(offset).limit(limit).all()

    # TODO - Rename this
    def find_all_images_with_hash_return_id_hash(self, limit: int = None, offset: int = 0):
        return self.db_session.query(Post).filter(Post.post_type == 'image', Post.dhash_h != None).with_entities(Post.id, Post.dhash_h).offset(offset).limit(limit).all()

    def annoy_load_test(self, limit: int = None, offset: int = None):
        return self.db_session.query(Post).filter(Post.post_type == 'image', Post.dhash_h != None, Post.id > offset).with_entities(Post.id, Post.dhash_h).order_by(Post.id).limit(limit).all()

    def count_by_type(self, post_type: str):
        r = self.db_session.query(func.count(Post.id)).filter(Post.post_type == post_type).first()
        return r[0] if r else None

    def get_count(self):
        r = self.db_session.query(func.count(Post.id)).first()
        return r[0] if r else None

    # Repost methods
    def find_all_by_type_repost(self, post_type: str, limit: int = None, offset: int = None) -> List[Post]:
        return self.db_session.query(Post).filter(Post.post_type == post_type, Post.checked_repost == 0).offset(offset).limit(limit).all()

    def find_all_links_without_hash(self, limit: int = None, offset: int = None) -> List[Post]:
        return self.db_session.query(Post).filter(Post.post_type == 'link', Post.url_hash == None).order_by(Post.created_at.desc()).offset(offset).limit(limit).all()

    def get_with_self_text(self, limit: int = None, offset: int = None):
        return self.db_session.query(Post).filter(Post.post_type == 'text', Post.selftext != None).with_entities(Post.id, Post.selftext).offset(offset).limit(limit).all()

    def remove(self, item: Post):
        log.debug('Deleting post %s', item.id)
        self.db_session.delete(item)