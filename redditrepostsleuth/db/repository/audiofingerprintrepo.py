from typing import List

from redditrepostsleuth.model.db.databasemodels import AudioFingerPrint


class AudioFingerPrintRepository:
    def __init__(self, db_session):
        self.db_session = db_session

    def add(self, item: AudioFingerPrint):
        self.db_session.add(item)

    def get_by_post_id(self, post_id: str) -> AudioFingerPrint:
        return self.db_session.query(AudioFingerPrint).filter(AudioFingerPrint.post_id == post_id).first()

    def bulk_save(self, items: List[AudioFingerPrint]):
        self.db_session.bulk_save_objects(items)