from datetime import datetime, timedelta
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

    def get_older_with_matches(self, limit: int = None) -> List[ImageSearch]:
        since = datetime.now() - timedelta(days=14)
        return self.db_session.query(ImageSearch).filter(ImageSearch.searched_at < since, ImageSearch.matches_found > 5).limit(limit).all()

    def remove(self, item: ImageSearch):
        self.db_session.delete(item)