from typing import List, Optional, Set

from redditrepostsleuth.core.db.databasemodels import SpamSubredditList


class SpamSubredditRepo:

    def __init__(self, db_session):
        self.db_session = db_session

    def add(self, item: SpamSubredditList):
        self.db_session.add(item)

    def get_by_id(self, id: int) -> Optional[SpamSubredditList]:
        return self.db_session.query(SpamSubredditList).filter(
            SpamSubredditList.id == id
        ).first()

    def get_by_name(self, subreddit_name: str) -> Optional[SpamSubredditList]:
        return self.db_session.query(SpamSubredditList).filter(
            SpamSubredditList.subreddit_name == subreddit_name
        ).first()

    def get_all(self, active_only: bool = True) -> List[SpamSubredditList]:
        query = self.db_session.query(SpamSubredditList)
        if active_only:
            query = query.filter(SpamSubredditList.is_active == True)
        return query.all()

    def get_all_names(self, active_only: bool = True) -> Set[str]:
        """Get set of all spam subreddit names for fast lookup."""
        query = self.db_session.query(SpamSubredditList.subreddit_name)
        if active_only:
            query = query.filter(SpamSubredditList.is_active == True)
        return {row[0].lower() for row in query.all()}

    def get_by_category(self, category: str, active_only: bool = True) -> List[SpamSubredditList]:
        query = self.db_session.query(SpamSubredditList).filter(
            SpamSubredditList.category == category
        )
        if active_only:
            query = query.filter(SpamSubredditList.is_active == True)
        return query.all()

    def is_spam_subreddit(self, subreddit_name: str) -> bool:
        """Check if a subreddit is in the spam list."""
        result = self.db_session.query(SpamSubredditList).filter(
            SpamSubredditList.subreddit_name == subreddit_name,
            SpamSubredditList.is_active == True
        ).first()
        return result is not None

    def deactivate(self, subreddit_name: str) -> bool:
        """Deactivate a subreddit in the spam list. Returns True if updated."""
        result = self.db_session.query(SpamSubredditList).filter(
            SpamSubredditList.subreddit_name == subreddit_name
        ).update({'is_active': False}, synchronize_session=False)
        return result > 0

    def delete_by_name(self, subreddit_name: str) -> bool:
        """Delete a subreddit from the spam list. Returns True if deleted."""
        result = self.db_session.query(SpamSubredditList).filter(
            SpamSubredditList.subreddit_name == subreddit_name
        ).delete(synchronize_session=False)
        return result > 0

    def get_as_dict(self) -> dict:
        """
        Get all active spam subreddits as a dictionary.

        Returns:
            Dict mapping lowercase subreddit name to (category, weight) tuple
        """
        records = self.db_session.query(SpamSubredditList).filter(
            SpamSubredditList.is_active == True
        ).all()
        return {
            r.subreddit_name.lower(): (r.category, r.weight)
            for r in records
        }
