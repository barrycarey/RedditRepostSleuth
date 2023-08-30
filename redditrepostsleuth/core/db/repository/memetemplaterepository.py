from typing import List, Text

from redditrepostsleuth.core.db.databasemodels import MemeTemplate


class MemeTemplateRepository:
    def __init__(self, db_session):
        self.db_session = db_session

    def add(self, item):
        self.db_session.add(item)

    def get_by_id(self, id: int) -> MemeTemplate:
        return self.db_session.query(MemeTemplate).filter(MemeTemplate.id == id).first()

    def get_by_post_id(self, id: int) -> MemeTemplate:
        return self.db_session.query(MemeTemplate).filter(MemeTemplate.post_id == id).first()

    def get_all(self, limit: int = 100, offset: int = 0) -> List[MemeTemplate]:
        return self.db_session.query(MemeTemplate).limit(limit).offset(offset).all()

    def update(self, item: MemeTemplate):
        self.db_session.merge(item)

    def remove(self, item: MemeTemplate):
        self.db_session.delete(item)