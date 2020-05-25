from datetime import datetime
from typing import Text, List

from redditrepostsleuth.core.db.databasemodels import BannedUser


class BannedUserRepo:
    def __init__(self, db_session):
        self.db_session = db_session

    def add(self, item):
        self.db_session.add(item)

    def get_by_user(self, name: Text) -> BannedUser:
        return self.db_session.query(BannedUser).filter(BannedUser.name == name).first()

    def get_all(self, limit: int = None, offset: int = None) -> List[BannedUser]:
        return self.db_session.query(BannedUser).limit(limit).offset(offset).all()

    def get_expired_bans(self):
        return self.db_session.query(BannedUser).filter(BannedUser.expires_at < datetime.utcnow()).all()

    def remove(self, item):
        self.db_session.delete(item)