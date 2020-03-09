from typing import Text, List

from redditrepostsleuth.core.db.databasemodels import MonitoredSubConfigRevision, ImageSearch


class ImageSearchRepo:
    def __init__(self, db_session):
        self.db_session = db_session

    def get_by_post_id(self, post_id: Text) -> List[ImageSearch]:
        return self.db_session.query(ImageSearch).filter(ImageSearch.post_id == post_id).all()

    def add(self, search: ImageSearch):
        self.db_session.add(search)

    def update(self, revision: ImageSearch):
        self.db_session.update(revision)

    def get_all(self, limit: int = None):
        return self.db_session.query(ImageSearch).limit(limit).all()

    def remove(self, item: ImageSearch):
        self.db_session.delete(item)