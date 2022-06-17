from typing import Text

from redditrepostsleuth.core.db.databasemodels import ImageIndexMap


class ImageIndexMapRepo:
    def __init__(self, db_session):
        self.db_session = db_session

    def get_by_id_and_index(self, id: int, index: Text) -> ImageIndexMap:
        return self.db_session.query(ImageIndexMap).filter(ImageIndexMap.annoy_index_id == id, ImageIndexMap.index_name == index).first()

    def add(self, item):
        self.db_session.add(item)