from redditrepostsleuth.core.db.databasemodels import MonitoredSubConfigRevision, ImageSearch


class ImageSearchRepo:
    def __init__(self, db_session):
        self.db_session = db_session

    def add(self, search: ImageSearch):
        self.db_session.add(search)

    def update(self, revision: ImageSearch):
        self.db_session.update(revision)

    def get_all(self, limit: int = None):
        return self.db_session.query(ImageSearch).limit(limit).all()