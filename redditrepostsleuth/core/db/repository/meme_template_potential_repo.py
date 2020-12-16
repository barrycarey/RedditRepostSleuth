from typing import List, Text

from redditrepostsleuth.core.db.databasemodels import MemeTemplatePotential


class MemeTemplatePotentialRepo:
    def __init__(self, db_session):
        self.db_session = db_session

    def add(self, item: MemeTemplatePotential):
        self.db_session.add(item)

    def get_all(self, limit: int = None, offset: int = None) -> List[MemeTemplatePotential]:
        return self.db_session.query(MemeTemplatePotential).order_by(MemeTemplatePotential.id.desc()).limit(limit).offset(offset).all()

    def get_by_id(self, id: int) -> MemeTemplatePotential:
        return self.db_session.query(MemeTemplatePotential).filter(MemeTemplatePotential.id == id).first()

    def get_by_post_id(self, id: Text) -> MemeTemplatePotential:
        return self.db_session.query(MemeTemplatePotential).filter(MemeTemplatePotential.post_id == id).first()

    def get_with_more_votes_than(self, total: int) -> List[MemeTemplatePotential]:
        return self.db_session.query(MemeTemplatePotential).filter(MemeTemplatePotential.vote_total >= total).all()

    def get_with_less_votes_than(self, total: int) -> List[MemeTemplatePotential]:
        return self.db_session.query(MemeTemplatePotential).filter(MemeTemplatePotential.vote_total <= total).all()

    def remove(self, item: MemeTemplatePotential):
        self.db_session.delete(item)

    def update(self, item: MemeTemplatePotential):
        self.db_session.merge(item)