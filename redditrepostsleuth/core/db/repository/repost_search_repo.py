from datetime import datetime, timedelta

from redditrepostsleuth.core.db.databasemodels import RepostSearch


class RepostSearchRepo:
    def __init__(self, db_session):
        self.db_session = db_session

    def get_by_id(self, id: int) -> RepostSearch:
        return self.db_session.query(RepostSearch).filter(RepostSearch.id == id).first()

    def get_by_post_id(self, post_id: int) -> list[RepostSearch]:
        return self.db_session.query(RepostSearch).filter(RepostSearch.post_id == post_id).all()

    def add(self, search: RepostSearch):
        self.db_session.add(search)

    def update(self, revision: RepostSearch):
        self.db_session.update(revision)

    def get_all_older_than_days(self, days: int, limit: int = 100) -> list[RepostSearch]:
        delta = datetime.utcnow() - timedelta(days=days)
        return self.db_session.query(RepostSearch).filter(RepostSearch.searched_at < delta).limit(limit).all()

    def get_all_ids_older_than_days(self, days: int, limit: int = 100) -> list[RepostSearch]:
        delta = datetime.utcnow() - timedelta(days=days)
        return self.db_session.query(RepostSearch.id).filter(RepostSearch.searched_at < delta).order_by(RepostSearch.id).limit(limit).all()


    def delete_all_older_than_days(self, days: int, limit: int = 100) -> None:
        delta = datetime.utcnow() - timedelta(days=days)
        self.db_session.query(RepostSearch).filter(RepostSearch.searched_at < delta).limit(limit).delete()

    def delete_all_with_lower_id(self, lower_id: int) -> None:
        self.db_session.query(RepostSearch).filter(RepostSearch.id < lower_id).delete()

    def get_oldest_search(self) -> RepostSearch:
        return self.db_session.query(RepostSearch).order_by(RepostSearch.id).first()

    def get_all(self, limit: int = None):
        return self.db_session.query(RepostSearch).limit(limit).all()

    def get_by_subreddit(self, subreddit: str, source: str = 'sub_monitor', only_reposts: bool = False, limit: int = None, offset: int = None) -> list[RepostSearch]:
        query = self.db_session.query(RepostSearch).filter(RepostSearch.subreddit == subreddit, RepostSearch.source == source)
        if only_reposts:
            query = query.filter(RepostSearch.matches_found > 0)
        return query.order_by(RepostSearch.id.desc()).limit(limit).offset(offset).all()

    def get_all_reposts_by_subreddit(self, subreddit: str, source: str = 'sub_monitor', limit: int = None, offset: int = None):
        return self.db_session.query(RepostSearch).filter(RepostSearch.subreddit == subreddit, RepostSearch.source == source, RepostSearch.matches_found > 0).order_by(
            RepostSearch.id.desc()).limit(limit).offset(offset).all()

    def get_older_with_matches(self, limit: int = None) -> list[RepostSearch]:
        since = datetime.now() - timedelta(days=14)
        return self.db_session.query(RepostSearch).filter(RepostSearch.searched_at < since, RepostSearch.matches_found > 5).limit(limit).all()

    def remove(self, item: RepostSearch):
        self.db_session.delete(item)