import datetime

from sqlalchemy import or_

from redditrepostsleuth.core.db.databasemodels import Subreddit


class SubredditRepo:
    def __init__(self, db_session):
        self.db_session = db_session

    def add(self, item):
        self.db_session.add(item)

    def get_by_name(self, name: str):
        return self.db_session.query(Subreddit).filter(Subreddit.name == name).first()

    def get_subreddits_to_update(self, limit: int = None, offset: int = None) -> list[Subreddit]:
        delta = datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=3)
        return self.db_session.query(Subreddit).filter(or_(Subreddit.added_at < delta, Subreddit.last_checked == None)).limit(limit).offset(offset).all()