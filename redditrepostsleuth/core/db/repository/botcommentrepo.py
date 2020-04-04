from datetime import datetime
from typing import List, Text

from redditrepostsleuth.core.db.databasemodels import BotComment


class BotCommentRepo:
    def __init__(self, db_session):
        self.db_session = db_session

    def get_all(self, limit: int = None) -> List[BotComment]:
        return self.db_session.query(BotComment).limit(limit).all()

    def get_by_post_id(self, post_id) -> List[BotComment]:
        return self.db_session.query(BotComment).filter(BotComment.post_id == post_id).all()

    def get_by_post_id_and_type(self, post_id: Text, response_type: Text) -> BotComment:
        return self.db_session.query(BotComment).filter(BotComment.post_id == post_id, BotComment.source == response_type).first()

    def get_after_date(self, date: datetime) -> List[BotComment]:
        return self.db_session.query(BotComment).filter(BotComment.comment_left_at > date).all()

    def add(self, item: BotComment):
        self.db_session.add(item)

    def remove(self, item: BotComment):
        self.db_session.delete(item)