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

    def get_oldest_post(self, limit: int = None):
        return self.db_session.query(Post).order_by(Post.created_at).first()

    def get_by_id(self, id: int) -> Post:
        return self.db_session.query(Post).filter(Post.id == id).first()

    def get_by_post_id(self, id: str) -> Post:
        #log.debug('Looking up post with ID %s', id)
        return self.db_session.query(Post).filter(Post.post_id == id).first()

    def find_all_by_hash(self, hash_str: str, limit: int = None) -> List[Post]:
        query = self.db_session.query(Post).filter(Post.image_hash == hash_str, Post.post_type == 'image').limit(limit).all()
        return query

    def find_all_without_hash(self, limit: int = None, offset: int = None) -> List[Post]:
        return self.db_session.query(Post).filter(Post.post_type == 'image', Post.ahash == None, Post.dhash_h == None, Post.dhash_v == None).offset(offset).limit(limit).all()

    def find_all_by_url(self, url: str, limit: int = None):
        return self.db_session.query(Post).filter(Post.url == url).limit(limit).all()

    def find_all_by_url_hash(self, hash: str, limit: int = None):
        return self.db_session.query(Post).filter(Post.url_hash == hash).limit(limit).all()

    def find_all_by_type(self, post_type: str, limit: int = None, offset: int = None) -> List[Post]:
        return self.db_session.query(Post).filter(Post.post_type == post_type).offset(offset).limit(limit).all()

    def find_all_by_repost_check(self, repost_check: bool, limit: int = None, offset: int = None):
        return self.db_session.query(Post).filter(Post.checked_repost == repost_check, Post.post_type == 'image', Post.crosspost_parent == None, Post.dhash_h != None).offset(offset).limit(limit).all()

    # TODO: Clean this up
    def find_all_by_repost_check_oldest(self, repost_check: bool, limit: int = None, offset: int = None):
        return self.db_session.query(Post).filter(Post.checked_repost == False, Post.post_type == 'image', Post.image_hash != None).order_by(Post.created_at).offset(offset).limit(limit).all()


    def find_all_older_posts(self, created: DateTime):
        return self.db_session.query(Post).filter(Post.created_at < created, Post.post_type == 'image').order_by(Post.created_at.desc()).all()

    def find_all_images_with_hash(self, limit: int = None, offset: int = None):
        return self.db_session.query(Post).filter(Post.image_hash != None).offset(offset).limit(limit).all()

    def find_all_unchecked_crosspost(self, limit: int = None, offset: int = None) -> List[Post]:
        return self.db_session.query(Post).filter(Post.crosspost_checked == False).offset(offset).limit(limit).all()

    def find_all_for_delete_check(self, hours: int, limit: int = None, offset: int = None) -> List[Post]:
        since = datetime.now() - timedelta(hours=hours)
        return self.db_session.query(Post).filter(Post.last_deleted_check < since).offset(offset).limit(limit).all()

    def find_all_older(self, date):
        return self.db_session.query(Post).filter(Post.created_at <= date, Post.post_type == 'image', Post.image_hash != None).with_entities(Post.post_id, Post.image_hash).all()

    # TODO - Rename this
    def find_all_images_with_hash_return_id_hash(self, limit: int = None, offset: int = None):
        return self.db_session.query(Post).filter(Post.post_type == 'image', Post.dhash_h != None).with_entities(Post.id, Post.dhash_h).offset(offset).limit(limit).all()

    def find_all_images_with_hash_return_id_hash2(self, limit: int = None, offset: int = None):
        return self.db_session.query(Post).filter(Post.post_type == 'image', Post.dhash_h != None).with_entities(Post.id, Post.dhash_h, Post.dhash_v).offset(offset).limit(limit).all()

    def count_by_type(self, post_type: str):
        r = self.db_session.query(func.count(Post.id)).filter(Post.post_type == post_type).first()
        return r[0] if r else None

    def get_count(self):
        r = self.db_session.query(func.count(Post.id)).first()
        return r[0] if r else None

    # Repost methods
    def find_all_by_type_repost(self, post_type: str, limit: int = None, offset: int = None) -> List[Post]:
        return self.db_session.query(Post).filter(Post.post_type == post_type, Post.checked_repost == 0).order_by(Post.created_at.desc()).offset(offset).limit(limit).all()

    def find_all_links_without_hash(self, limit: int = None, offset: int = None) -> List[Post]:
        return self.db_session.query(Post).filter(Post.post_type == 'link', Post.url_hash == None).order_by(Post.created_at.desc()).offset(offset).limit(limit).all()

    def find_all_without_bits_set(self, limit: int = None, offset: int = None) -> Post:
        return self.db_session.query(Post).filter(Post.post_type == 'image', Post.images_bits_set == None).offset(offset).limit(limit).all()

    def find_image_hashes_in_rage(self, lower: int, upper: int):
        return self.db_session.query(Post).filter(Post.image_bits_set.between(lower, upper)).with_entities(Post.post_id, Post.dhash_h).all()

    def remove(self, item: Post):
        log.debug('Deleting post %s', item.id)
        self.db_session.delete(item)