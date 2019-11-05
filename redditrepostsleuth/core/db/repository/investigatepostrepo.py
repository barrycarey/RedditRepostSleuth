from redditrepostsleuth.core.db.databasemodels import InvestigatePost


class InvestigatePostRepo:
    def __init__(self, db_session):
        self.db_session = db_session

    def add(self, item: InvestigatePost):
        self.db_session.add(item)

    def get_all(self):
        return self.db_session.query(InvestigatePost).all()