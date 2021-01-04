from typing import Text

from redditrepostsleuth.core.db.databasemodels import SiteAdmin


class SiteAdminRepo:
    def __init__(self, db_session):
        self.db_session = db_session

    def get_by_id(self, id: int) -> SiteAdmin:
        return self.db_session.query(SiteAdmin).filter(SiteAdmin.id == id).first()

    def get_by_username(self, username: Text) -> SiteAdmin:
        return self.db_session.query(SiteAdmin).filter(SiteAdmin.user == username).first()