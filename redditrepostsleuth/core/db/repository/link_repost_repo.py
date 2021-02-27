from datetime import datetime, timedelta
from typing import List, Text

from sqlalchemy import func

from redditrepostsleuth.core.db.databasemodels import LinkRepost


class LinkPostRepo:
    def __init__(self, db_session):
        self.db_session = db_session

    def get_by_repost_of(self, post_id) -> LinkRepost:
        return self.db_session.query(LinkRepost).filter(LinkRepost.repost_of == post_id).all()

    def get_all_by_subreddit(self, subreddit: Text, source='sub_monitor', limit: int = None, offset: int = None) -> List[LinkRepost]:
        return self.db_session.query(LinkRepost).filter(LinkRepost.subreddit == subreddit, LinkRepost.source == source).order_by(LinkRepost.id.desc()).all()

    def get_count(self, hours: int = None):
        query = self.db_session.query(func.count(LinkRepost.id))
        if hours:
            query = query.filter(LinkRepost.detected_at > (datetime.now() - timedelta(hours=hours)))
        r = query.first()
        return r[0] if r else None

    def get_count_by_subreddit(self, subreddit: Text, hours: int = None):
        query = self.db_session.query(func.count(LinkRepost.id)).filter(LinkRepost.subreddit == subreddit)
        if hours:
            query = query.filter(LinkRepost.detected_at > (datetime.now() - timedelta(hours=hours)))
        return query.first()

    def remove(self, item: LinkRepost):
        self.db_session.delete(item)

    def add(self, item):
        self.db_session.add(item)