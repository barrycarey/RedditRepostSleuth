from typing import Text, List

from redditrepostsleuth.core.db.databasemodels import UserReport
from redditrepostsleuth.core.logging import log


class UserReportRepo:
    def __init__(self, db_session):
        self.db_session = db_session

    def add(self, item):
        log.debug('Inserting: %s', item)
        self.db_session.add(item)

    def get_all(self, limit: int = None, offset: int = None) -> List[UserReport]:
        return self.db_session.query(UserReport).offset(offset).limit(limit).all()

    def get_by_id(self, id: Text) -> UserReport:
        return self.db_session.query(UserReport).filter(UserReport.id == id).first()

    def get_first_by_message_id(self, id: Text) -> UserReport:
        return self.db_session.query(UserReport).filter(UserReport.message_id == id).first()