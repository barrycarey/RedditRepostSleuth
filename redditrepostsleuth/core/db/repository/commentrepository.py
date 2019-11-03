from redditrepostsleuth.common.logging import log
from redditrepostsleuth.core.db.databasemodels import Comment


class CommentRepository:
    def __init__(self, db_session):
        self.db_session = db_session
    def add(self, item):
        log.debug('Inserting: %s', item)
        self.db_session.add(item)

    def get_by_id(self, id: int) -> Comment:
        return self.db_session.get(Comment, id)

    def get_by_comment_id(self, id: str) -> Comment:
        return self.db_session.query(Comment).filter(Comment.comment_id == id).first()