from typing import Text, List

from redditrepostsleuth.core.db.databasemodels import BotPrivateMessage


class BotPrivateMessageRepo:
    def __init__(self, db_session):
        self.db_session = db_session

    def get_all(self, limit: int = None) -> List[BotPrivateMessage]:
        return self.db_session.query(BotPrivateMessage).limit(limit).all()

    def get_by_post_id(self, post_id: Text) -> List[BotPrivateMessage]:
        return self.db_session.query(BotPrivateMessage).filter(BotPrivateMessage.in_response_to_post == -post_id).all()

    def get_by_comment_id(self, post_id: Text) -> List[BotPrivateMessage]:
        return self.db_session.query(BotPrivateMessage).filter(BotPrivateMessage.in_response_to_comment == -post_id).all()

    def add(self, item: BotPrivateMessage):
        self.db_session.add(item)

    def remove(self, item: BotPrivateMessage):
        self.db_session.delete(item)