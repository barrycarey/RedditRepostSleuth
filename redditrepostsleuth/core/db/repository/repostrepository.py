from redditrepostsleuth.core.logging import log
from redditrepostsleuth.core.db.databasemodels import Reposts


class RepostRepository:
    def __init__(self, db_session):
        self.db_session = db_session


    def add(self, item):
        log.debug('Inserting: %s', item)
        self.db_session.add(item)


    def get_by_id(self, id: int) -> Reposts:
        return self.db_session.query(Reposts).filter(Reposts.id == id).first()


    def remove(self, item: Reposts):
        log.debug('Deleting post %s', item.id)
        self.db_session.delete(item)