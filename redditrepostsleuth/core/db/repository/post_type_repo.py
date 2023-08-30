from typing import Optional

from redditrepostsleuth.core.db.databasemodels import PostType


class PostTypeRepo:

    def __init__(self, db_session):
        self.db_session = db_session

    def get_by_name(self, name: str) -> Optional[PostType]:
        return self.db_session.query(PostType).filter(PostType.name == name).first()