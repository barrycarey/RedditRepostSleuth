from typing import List, Text

from sqlalchemy import func
from datetime import timedelta, datetime
from redditrepostsleuth.core.logging import log
from redditrepostsleuth.core.db.databasemodels import ImageRepost


class ImageRepostRepository:

    def __init__(self, db_session):
        self.db_session = db_session

    def get_all(self, limit: int = None, offset: int = None) -> List[ImageRepost]:
        return self.db_session.query(ImageRepost).order_by(ImageRepost.id.desc()).offset(offset).limit(limit).all()

    def get_all_without_author(self, limit: int = None, offset: int = None):
        return self.db_session.query(ImageRepost).filter(ImageRepost.author == None).order_by(ImageRepost.id.desc()).offset(offset).limit(limit).all()

    def get_by_id(self, id: int) -> ImageRepost:
        return self.db_session.query(ImageRepost).filter(ImageRepost.id == id).first()

    def get_dups_by_post_id(self, post_id: str) -> ImageRepost:
        return self.db_session.query(ImageRepost).filter(ImageRepost.post_id == post_id).all()

    def get_by_repost_of(self, post_id: Text) -> List[ImageRepost]:
        return self.db_session.query(ImageRepost).filter(ImageRepost.repost_of == post_id).all()

    def get_all_by_subreddit(self, subreddit: Text, source='sub_monitor', limit: int = None, offset: int = None) -> List[ImageRepost]:
        return self.db_session.query(ImageRepost).filter(ImageRepost.subreddit == subreddit, ImageRepost.source == source).order_by(ImageRepost.id.desc()).limit(limit).offset(offset).all()

    def get_count(self, hours: int = None):
        query = self.db_session.query(func.count(ImageRepost.id))
        if hours:
            query = query.filter(ImageRepost.detected_at > (datetime.now() - timedelta(hours=hours)))
        r = query.first()
        return r[0] if r else None

    def get_count_by_subreddit(self, subreddit: Text, hours: int = None):
        query = self.db_session.query(func.count(ImageRepost.id)).filter(ImageRepost.subreddit == subreddit)
        if hours:
            query = query.filter(ImageRepost.detected_at > (datetime.now() - timedelta(hours=hours)))
        return query.first()

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