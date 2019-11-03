from typing import List

from redditrepostsleuth.core.logging import log
from redditrepostsleuth.core.db.databasemodels import VideoHash


class VideoHashRepository:
    def __init__(self, db_session):
        self.db_session = db_session

    def get_all(self, limit: int = None, offset: int = None) -> List[VideoHash]:
        return self.db_session.query(VideoHash).offset(offset).limit(limit).all()

    def get_by_id(self, id: int) -> VideoHash:
        result = self.db_session.query(VideoHash).filter(VideoHash.id == id).first()
        return result

    def get_by_post_id(self, id: str) -> VideoHash:
        result = self.db_session.query(VideoHash).filter(VideoHash.post_id == id).first()
        return result

    def add(self, item):
        log.debug('Inserting: %s', item)
        self.db_session.add(item)