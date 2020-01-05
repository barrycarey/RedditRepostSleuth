from typing import Text

from redditrepostsleuth.core.db.databasemodels import MemeTemplate
from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.core.model.imagerepostwrapper import ImageRepostWrapper
from redditrepostsleuth.core.services.image_index_loader import ImageIndexLoader
from redditrepostsleuth.core.util.repost_filters import raw_annoy_filter


class MemeDetector:
    def __init__(self, uowm: UnitOfWorkManager, config, index_loader: ImageIndexLoader = None):
        self.config = config
        self.uowm = uowm
        self.index_loader = index_loader or ImageIndexLoader(config)

    def detect_meme(self, image_hash: Text) -> MemeTemplate:
        search_vector = bytearray(image_hash, encoding='utf-8')
        r = self.index_loader.meme_index.loaded_index.get_nns_by_vector(list(search_vector), 50, search_k=20000, include_distances=True)
        raw_results = list(zip(r[0], r[1]))
        raw_results = list(filter(
            raw_annoy_filter(0.265),
            raw_results
        ))
        raw_results.sort(key=lambda x: x[1], reverse=True)
        print('')

    def _get_meme_template(self, template_id: int):
        with self.uowm.start() as uow:
            return uow.meme_template.get_by_id(template_id)