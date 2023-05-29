from typing import Text

from redditrepostsleuth.core.db.databasemodels import InvestigatePost


class InvestigatePostRepo:
    def __init__(self, db_session):
        self.db_session = db_session

    def add(self, item: InvestigatePost):
        self.db_session.add(item)

    def get_by_id(self, id: int):
        return self.db_session.query(InvestigatePost).filter(InvestigatePost.id == id).first()

    def get_by_post_id(self, id: Text) -> InvestigatePost:
        return self.db_session.query(InvestigatePost).filter(InvestigatePost.post_id == id).first()

    def get_all(self):
        return self.db_session.query(InvestigatePost).filter(InvestigatePost.flag_reason == 'High match meme').order_by(InvestigatePost.matches.desc()).limit(100).all()

    def remove(self, item: InvestigatePost):
        self.db_session.delete(item)

    def remove_by_post_id(self, post_id: str) -> None:
        self.db_session.query(InvestigatePost).filter(InvestigatePost.post_id == post_id).delete()