class LinkPostRepo:
    def __init__(self, db_session):
        self.db_session = db_session

    def add(self, item):
        self.db_session.add(item)