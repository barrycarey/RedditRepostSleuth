from datetime import datetime, timedelta
from typing import Text, List

from redditrepostsleuth.core.db.databasemodels import MonitoredSubConfigRevision, RepostSearch


class RepostSearchRepo:
    def __init__(self, db_session):
        self.db_session = db_session

    def get_by_id(self, id: int) -> RepostSearch:
        return self.db_session.query(RepostSearch).filter(RepostSearch.id == id).first()

    def get_by_post_id(self, post_id: int) -> List[RepostSearch]:
        return self.db_session.query(RepostSearch).filter(RepostSearch.post_id == post_id).all()

    def add(self, search: RepostSearch):
        self.db_session.add(search)

    def update(self, revision: RepostSearch):
        self.db_session.update(revision)

    def get_all(self, limit: int = None):
        return self.db_session.query(RepostSearch).limit(limit).all()

    def get_by_subreddit(self, subreddit: str, source: Text = 'sub_monitor', only_reposts: bool = False, limit: int = None, offset: int = None) -> List[RepostSearch]:
        query = self.db_session.query(RepostSearch).filter(RepostSearch.subreddit == subreddit, RepostSearch.source == source)
        if only_reposts:
            query = query.filter(RepostSearch.matches_found > 0)
        return query.order_by(RepostSearch.id.desc()).limit(limit).offset(offset).all()

    def get_all_reposts_by_subreddit(self, subreddit: Text, source: Text = 'sub_monitor', limit: int = None, offset: int = None):
        return self.db_session.query(RepostSearch).filter(RepostSearch.subreddit == subreddit, RepostSearch.source == source, RepostSearch.matches_found > 0).order_by(
            RepostSearch.id.desc()).limit(limit).offset(offset).all()

    def get_older_with_matches(self, limit: int = None) -> List[RepostSearch]:
        since = datetime.now() - timedelta(days=14)
        return self.db_session.query(RepostSearch).filter(RepostSearch.searched_at < since, RepostSearch.matches_found > 5).limit(limit).all()

    def remove(self, item: RepostSearch):
        self.db_session.delete(item)