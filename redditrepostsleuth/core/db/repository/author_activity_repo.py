from datetime import datetime
from typing import List, Optional

from sqlalchemy import func

from redditrepostsleuth.core.db.databasemodels import AuthorActivityTracking


class AuthorActivityRepo:

    def __init__(self, db_session):
        self.db_session = db_session

    def add(self, item: AuthorActivityTracking):
        self.db_session.add(item)

    def get_by_post_id(self, post_id: str) -> Optional[AuthorActivityTracking]:
        return self.db_session.query(AuthorActivityTracking).filter(
            AuthorActivityTracking.post_id == post_id
        ).first()

    def get_by_author(self, author: str, limit: int = None) -> List[AuthorActivityTracking]:
        query = self.db_session.query(AuthorActivityTracking).filter(
            AuthorActivityTracking.author == author
        ).order_by(AuthorActivityTracking.created_at.desc())
        if limit:
            query = query.limit(limit)
        return query.all()

    def get_by_author_since(self, author: str, since: datetime) -> List[AuthorActivityTracking]:
        return self.db_session.query(AuthorActivityTracking).filter(
            AuthorActivityTracking.author == author,
            AuthorActivityTracking.created_at >= since
        ).order_by(AuthorActivityTracking.created_at.desc()).all()

    def get_author_subreddit_counts(self, author: str) -> List[tuple]:
        """Get count of posts per subreddit for an author."""
        return self.db_session.query(
            AuthorActivityTracking.subreddit,
            func.count(AuthorActivityTracking.id).label('count')
        ).filter(
            AuthorActivityTracking.author == author
        ).group_by(AuthorActivityTracking.subreddit).all()

    def get_author_stats(self, author: str) -> dict:
        """Get aggregate statistics for an author."""
        from sqlalchemy import Integer as SqlInteger
        result = self.db_session.query(
            func.count(AuthorActivityTracking.id).label('total_posts'),
            func.sum(func.cast(AuthorActivityTracking.is_nsfw, SqlInteger)).label('nsfw_count'),
            func.sum(func.cast(AuthorActivityTracking.has_adult_link, SqlInteger)).label('adult_link_count'),
            func.sum(func.cast(AuthorActivityTracking.has_short_link, SqlInteger)).label('short_link_count'),
            func.count(func.distinct(AuthorActivityTracking.subreddit)).label('unique_subreddits')
        ).filter(AuthorActivityTracking.author == author).first()

        if result:
            return {
                'total_posts': result.total_posts or 0,
                'nsfw_count': result.nsfw_count or 0,
                'adult_link_count': result.adult_link_count or 0,
                'short_link_count': result.short_link_count or 0,
                'unique_subreddits': result.unique_subreddits or 0
            }
        return {
            'total_posts': 0,
            'nsfw_count': 0,
            'adult_link_count': 0,
            'short_link_count': 0,
            'unique_subreddits': 0
        }

    def count_by_author(self, author: str) -> int:
        return self.db_session.query(func.count(AuthorActivityTracking.id)).filter(
            AuthorActivityTracking.author == author
        ).scalar() or 0

    def delete_older_than(self, cutoff_date: datetime) -> int:
        """Delete records older than the cutoff date. Returns count of deleted records."""
        result = self.db_session.query(AuthorActivityTracking).filter(
            AuthorActivityTracking.created_at < cutoff_date
        ).delete(synchronize_session=False)
        return result

    def get_author_subreddit_distribution(self, username: str) -> dict:
        """
        Get subreddit post distribution for an author as a dictionary.
        """
        counts = self.get_author_subreddit_counts(username)
        return {sub: count for sub, count in counts}
