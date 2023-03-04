from typing import Text

from redditrepostsleuth.core.db.databasemodels import ImageIndexMap


class ImageIndexMapRepo:
    def __init__(self, db_session):
        self.db_session = db_session

    def get_by_id_and_index(self, id: int, index: Text) -> ImageIndexMap:
        return self.db_session.query(ImageIndexMap).filter(ImageIndexMap.annoy_index_id == id, ImageIndexMap.index_name == index).first()

    def get_all_in_by_ids_and_index(self, ids: list[int], index: str) -> list[ImageIndexMap]:
        return self.db_session.query(ImageIndexMap).filter(ImageIndexMap.annoy_index_id.in_(ids), ImageIndexMap.index_name == index).all()
    def add(self, item):
        self.db_session.add(item)