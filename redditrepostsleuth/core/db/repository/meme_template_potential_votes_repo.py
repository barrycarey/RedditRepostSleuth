from typing import List, Text

from redditrepostsleuth.core.db.databasemodels import MemeTemplatePotentialVote


class MemeTemplatePotentialVoteRepo:
    def __init__(self, db_session):
        self.db_session = db_session

    def add(self, item: MemeTemplatePotentialVote):
        self.db_session.add(item)

    def get_all(self, limit: int = None, offset: int = None) -> List[MemeTemplatePotentialVote]:
        return self.db_session.query(MemeTemplatePotentialVote).limit(limit).offset(offset).all()

    def get_by_post_and_user(self, post_id: Text, user: Text) -> List[MemeTemplatePotentialVote]:
        return self.db_session.query(MemeTemplatePotentialVote).filter(MemeTemplatePotentialVote.post_id == post_id,
                                                                       MemeTemplatePotentialVote.user == user).all()

    def remove(self, item: MemeTemplatePotentialVote):
        self.db_session.delete(item)

    def update(self, item: MemeTemplatePotentialVote):
        self.db_session.merge(item)