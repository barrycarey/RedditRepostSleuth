from datetime import datetime, timedelta
from typing import List, Text, Optional

from sqlalchemy import func

from redditrepostsleuth.core.db.databasemodels import BotComment


class BotCommentRepo:
    def __init__(self, db_session):
        self.db_session = db_session

    def get_all(self, limit: int = None) -> List[BotComment]:
        return self.db_session.query(BotComment).limit(limit).all()

    def get_by_post_id(self, post_id) -> List[BotComment]:
        return self.db_session.query(BotComment).filter(BotComment.post_id == post_id).all()

    def get_by_post_id_and_type(self, post_id: Text, response_type: Text) -> BotComment:
        return self.db_session.query(BotComment).filter(BotComment.reddit_post_id == post_id, BotComment.source == response_type).first()

    def get_after_date(self, date: datetime) -> List[BotComment]:
        return self.db_session.query(BotComment).filter(BotComment.comment_left_at > date, BotComment.active == True).order_by(BotComment.id).all()

    def get_by_comment_id(self, comment_id: str) -> BotComment:
        return self.db_session.query(BotComment).filter(BotComment.comment_id == comment_id).first()
    def add(self, item: BotComment):
        self.db_session.add(item)

    def remove(self, item: BotComment):
        self.db_session.delete(item)

    def remove_by_post_id(self, post_id: str) -> None:
        self.db_session.query(BotComment).filter(BotComment.post_id == post_id).delete()

    def get_count(self, hours: int = None) -> Optional[int]:
        query = self.db_session.query(func.count(BotComment.id))
        if hours:
            query = query.filter(BotComment.comment_left_at > (datetime.now() - timedelta(hours=hours)))
        r = query.first()
        return r[0] if r else None