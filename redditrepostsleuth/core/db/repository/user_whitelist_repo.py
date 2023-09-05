from typing import Optional

from redditrepostsleuth.core.db.databasemodels import UserWhitelist


class UserWhitelistRepo:

    def __init__(self, db_session):
        self.db_session = db_session

    def add(self, item):
        self.db_session.add(item)

    def get_by_username_and_subreddit(self, username: str, monitored_sub_id: int) -> Optional[UserWhitelist]:
        return self.db_session.query(UserWhitelist).filter(UserWhitelist.username == username, UserWhitelist.monitored_sub_id == monitored_sub_id).first()


    def get_by_username(self, username: str) -> Optional[UserWhitelist]:
        return self.db_session.query(UserWhitelist).filter(UserWhitelist.username == username).first()