from typing import List

from redditrepostsleuth.core.db.databasemodels import MemeTemplate


class MemeTemplateRepository:
    def __init__(self, db_session):
        self.db_session = db_session

    def add(self, item):
        self.db_session.add(item)

    def get_by_id(self, id: int) -> MemeTemplate:
        return self.db_session.query(MemeTemplate).filter(MemeTemplate.id == id).first()

    def get_all(self) -> List[MemeTemplate]:
        return self.db_session.query(MemeTemplate).all()

    def get_by_name(self, name: str) -> MemeTemplate:
        return self.db_session.query(MemeTemplate).filter(MemeTemplate.name == name).first()

    def update(self, item: MemeTemplate):
        self.db_session.merge(item)