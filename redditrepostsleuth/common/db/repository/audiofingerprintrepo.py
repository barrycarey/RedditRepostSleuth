from typing import List

from redditrepostsleuth.common.logging import log
from redditrepostsleuth.common.model.db.databasemodels import AudioFingerPrint


class AudioFingerPrintRepository:
    def __init__(self, db_session):
        self.db_session = db_session

    def add(self, item: AudioFingerPrint):
        self.db_session.add(item)

    def get_by_post_id(self, post_id: str) -> AudioFingerPrint:
        return self.db_session.query(AudioFingerPrint).filter(AudioFingerPrint.post_id == post_id).first()

    def bulk_save(self, items: List[AudioFingerPrint]):
        log.info('Saving %s audio hashes', len(items))
        self.db_session.bulk_save_objects(items)