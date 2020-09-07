from typing import List, Text

from redditrepostsleuth.core.db.databasemodels import LinkRepost


class LinkPostRepo:
    def __init__(self, db_session):
        self.db_session = db_session

    def get_by_repost_of(self, post_id) -> LinkRepost:
        return self.db_session.query(LinkRepost).filter(LinkRepost.repost_of == post_id).all()

    def get_all_by_subreddit(self, subreddit: Text, source='sub_monitor', limit: int = None, offset: int = None) -> List[LinkRepost]:
        return self.db_session.query(LinkRepost).filter(LinkRepost.subreddit == subreddit, LinkRepost.source == source).order_by(LinkRepost.id.desc()).all()

    def remove(self, item: LinkRepost):
        self.db_session.delete(item)

    def add(self, item):
        self.db_session.add(item)