from typing import NoReturn

from redditrepostsleuth.core.db.databasemodels import MemeHash


class MemeHashRepo:
    def __init__(self, db_session):
        self.db_session = db_session

    def add(self, item: MemeHash) -> NoReturn:
        self.db_session.add(item)

    def get_by_post_id(self, post_id: str) -> MemeHash:
        return self.db_session.query(MemeHash).filter(MemeHash.post_id == post_id).first()