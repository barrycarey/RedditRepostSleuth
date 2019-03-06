from redditrepostsleuth.common.logging import log
from redditrepostsleuth.model.db.databasemodels import VideoHash


class VideoHashRepository:
    def __init__(self, db_session):
        self.db_session = db_session

    def get_by_id(self, id: int) -> VideoHash:
        result = self.db_session.query(VideoHash).filter(VideoHash.id == id).first()
        return result

    def add(self, item):
        log.debug('Inserting: %s', item)
        self.db_session.add(item)