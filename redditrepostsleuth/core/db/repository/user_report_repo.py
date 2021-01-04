from datetime import timedelta, datetime
from typing import Text, List

from redditrepostsleuth.core.db.databasemodels import UserReport
from redditrepostsleuth.core.logging import log


class UserReportRepo:
    def __init__(self, db_session):
        self.db_session = db_session

    def add(self, item):
        log.debug('Inserting: %s', item)
        self.db_session.add(item)

    def get_reports_for_voting(self, days: int) -> List[UserReport]:
        since = datetime.now() - timedelta(days=days)
        return self.db_session.query(UserReport).filter(UserReport.reported_at > since,
                                                        UserReport.report_type == 'False Positive',
                                                        UserReport.sent_for_voting == False).order_by(
            UserReport.reported_at.desc()).all()

    def get_all(self, limit: int = None, offset: int = None) -> List[UserReport]:
        return self.db_session.query(UserReport).offset(offset).limit(limit).all()

    def get_by_id(self, id: Text) -> UserReport:
        return self.db_session.query(UserReport).filter(UserReport.id == id).first()

    def get_by_post_id(self, post_id: Text) -> List[UserReport]:
        return self.db_session.query(UserReport).filter(UserReport.post_id == post_id).all()

    def get_first_by_message_id(self, id: Text) -> UserReport:
        return self.db_session.query(UserReport).filter(UserReport.message_id == id).first()

    def remove(self, item: UserReport):
        self.db_session.delete(item)