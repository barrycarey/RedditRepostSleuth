from datetime import datetime, timedelta
from typing import Text, List

from redditrepostsleuth.core.db.databasemodels import MonitoredSubConfigRevision, ImageSearch


class ImageSearchRepo:
    def __init__(self, db_session):
        self.db_session = db_session

    def get_by_id(self, id: int) -> ImageSearch:
        return self.db_session.query(ImageSearch).filter(ImageSearch.id == id).first()

    def get_by_post_id(self, post_id: Text) -> List[ImageSearch]:
        return self.db_session.query(ImageSearch).filter(ImageSearch.post_id == post_id).all()

    def add(self, search: ImageSearch):
        self.db_session.add(search)

    def update(self, revision: ImageSearch):
        self.db_session.update(revision)

    def get_all(self, limit: int = None):
        return self.db_session.query(ImageSearch).limit(limit).all()

    def get_by_subreddit(self, subreddit: Text, source: Text = 'sub_monitor', only_reposts: bool = False, limit: int = None, offset: int = None) -> List[ImageSearch]:
        query = self.db_session.query(ImageSearch).filter(ImageSearch.subreddit == subreddit, ImageSearch.source == source)
        if only_reposts:
            query = query.filter(ImageSearch.matches_found > 0)
        return query.order_by(ImageSearch.id.desc()).limit(limit).offset(offset).all()

    def get_all_reposts_by_subreddit(self, subreddit: Text, source: Text = 'sub_monitor', limit: int = None, offset: int = None):
        return self.db_session.query(ImageSearch).filter(ImageSearch.subreddit == subreddit, ImageSearch.source == source, ImageSearch.matches_found > 0).order_by(
            ImageSearch.id.desc()).limit(limit).offset(offset).all()

    def get_older_with_matches(self, limit: int = None) -> List[ImageSearch]:
        since = datetime.now() - timedelta(days=14)
        return self.db_session.query(ImageSearch).filter(ImageSearch.searched_at < since, ImageSearch.matches_found > 5).limit(limit).all()

    def remove(self, item: ImageSearch):
        self.db_session.delete(item)

    def remove_by_post_id(self, post_id: str) -> None:
        self.db_session.query(ImageSearch).filter(ImageSearch.post_id == post_id).delete()