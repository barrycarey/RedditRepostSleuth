from typing import List, Text

from sqlalchemy import func
from datetime import timedelta, datetime

from redditrepostsleuth.core.db.databasemodels import Repost
from redditrepostsleuth.core.logging import log



class RepostRepo:

    def __init__(self, db_session):
        self.db_session = db_session

    def get_all(self, limit: int = None, offset: int = None) -> List[Repost]:
        return self.db_session.query(Repost).order_by(Repost.id.desc()).offset(offset).limit(limit).all()

    def get_all_by_type(self, post_type_id: int, limit: None, offset: None) -> list[Repost]:
        return self.db_session.query(Repost).filter(Repost.post_type_id == post_type_id).order_by(Repost.id.desc()).offset(offset).limit(limit).all()

    def get_by_author(self, author: str) -> List[Repost]:
        return self.db_session.query(Repost).filter(Repost.author == author).all()

    def get_all_without_author(self, limit: int = None, offset: int = None):
        return self.db_session.query(Repost).filter(Repost.author == None).order_by(Repost.id.desc()).offset(offset).limit(limit).all()

    def get_by_id(self, id: int) -> Repost:
        return self.db_session.query(Repost).filter(Repost.id == id).first()

    def get_dups_by_post_id(self, post_id: str) -> Repost:
        return self.db_session.query(Repost).filter(Repost.post_id == post_id).all()

    def get_by_repost_of(self, post_id: Text) -> List[Repost]:
        return self.db_session.query(Repost).filter(Repost.repost_of == post_id).all()

    def get_all_by_subreddit(self, subreddit: Text, source='sub_monitor', limit: int = None, offset: int = None) -> List[Repost]:
        return self.db_session.query(Repost).filter(Repost.subreddit == subreddit, Repost.source == source).order_by(Repost.id.desc()).limit(limit).offset(offset).all()

    def get_count(self, hours: int = None, post_type: int = None):
        query = self.db_session.query(func.count(Repost.id))
        if post_type:
            query = query.filter(Repost.post_type_id == post_type)
        if hours:
            query = query.filter(Repost.detected_at > (datetime.now() - timedelta(hours=hours)))
        r = query.first()
        return r[0] if r else None

    def get_count_by_subreddit(self, subreddit: str, post_type_id: int, hours: int = None):
        query = self.db_session.query(func.count(Repost.id)).filter(Repost.subreddit == subreddit, Repost.post_type_id == post_type_id)
        if hours:
            query = query.filter(Repost.detected_at > (datetime.now() - timedelta(hours=hours)))
        return query.first()

    def add(self, item):
        self.db_session.add(item)

    def bulk_save(self, items: List[Repost]):
        self.db_session.bulk_save_objects(items)

    def update(self, item: Repost):
        self.db_session.merge(item)

    def get_top_last_over_days(self, days: int):
        oldest = datetime.utcnow() - timedelta(days=days)
        return self.db_session.query(Repost).filter(Repost.detected_at > oldest, )

    def remove(self, item: Repost):
        log.debug('Deleting post %s', item.id)
        self.db_session.delete(item)