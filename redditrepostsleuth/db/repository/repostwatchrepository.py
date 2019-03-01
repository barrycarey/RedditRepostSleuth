from redditrepostsleuth.common.logging import log
from redditrepostsleuth.model.db.databasemodels import RepostWatch


class RepostWatchRepository:
    def __init__(self, db_session):
        self.db_session = db_session

    def add(self, item):
        log.debug('Inserting: %s', item)
        self.db_session.add(item)

    def get_by_id(self, id: int) -> RepostWatch:
        return self.db_session.query(RepostWatch).filter(RepostWatch.id == id).first()

    def get_by_post_id(self, id: str) -> RepostWatch:
        return self.db_session.query(RepostWatch).filter(RepostWatch.post_id == id).first()

    def find_existing_watch(self, user: str, post_id: str):
        return self.db_session.query(RepostWatch).filter(RepostWatch.user == user, RepostWatch.post_id == post_id).first()

    def remove(self, item: RepostWatch):
        log.debug('Deleting post %s', item.id)
        self.db_session.delete(item)