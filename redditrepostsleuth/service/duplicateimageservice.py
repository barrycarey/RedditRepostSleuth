import os

from distance import hamming

from redditrepostsleuth.common.logging import log
from redditrepostsleuth.config import config
from redditrepostsleuth.db.uow.unitofworkmanager import UnitOfWorkManager
from datetime import datetime
from annoy import AnnoyIndex

from redditrepostsleuth.model.db.databasemodels import Post


class DuplicateImageService:
    def __init__(self, uowm: UnitOfWorkManager):
        self.uowm = uowm
        self.index  = AnnoyIndex(64)
        self.index_last_build = None
        self._load_index_file()

    def _build_index(self):
        """
        If index has nto been created or it is too old, create a new index
        """
        if self.index_last_build is None or (datetime.now() - self.index_last_build).seconds > config.index_keep_alive:
            log.info('Building new Annoy index')
            if os.path.isfile(config.index_file_name):
                log.info('Deleting existing index file')
                os.remove(config.index_file_name)
            with self.uowm.start() as uow:
                existing_images = uow.posts.find_all_images_with_hash_return_id_hash()
            log.info('Index will be built with %s hashes', len(existing_images))
            for image in existing_images:
                vector = list(bytearray(image[1], encoding='utf-8'))
                self.index.add_item(image[0], vector)
            self.index.build(config.index_tree_count)
            self.index.save(config.index_file_name)

    def _load_index_file(self):
        """
        Check if index file exists.  If it does, check it's age.  If it's fresh enough use it, if not build one
        :return:
        """
        log.info('Attempting to load Annoy index file')
        if os.path.isfile(config.index_file_name):
            log.info('Found Annoy index')
            created_at = datetime.fromtimestamp(os.stat(config.index_file_name).st_ctime)
            delta = datetime.now() - created_at
            if delta.seconds > config.index_keep_alive:
                log.info('Index is too old.  Not using')
                return None
            else:
                log.info('Index is fresh, using it')
                self.index_last_build = created_at
                self.index.load(config.index_file_name)
                self.index.build(config.index_tree_count)

    def _clean_results(self, results, orig_id):
        with self.uowm.start() as uow:
            original = uow.posts.get_by_id(orig_id)

        final_results = []
        for result in results:
            if result[1] > 0.265:
                log.debug('Skipping result with distance %s', result[1])
                continue
            # Skip original query (result[0] is DB ID)
            if result[0] == orig_id:
                continue

            with self.uowm.start() as uow:
                post = uow.posts.get_by_id(result[0])

            hamming_distance = hamming(original.dhash_h, post.dhash_h)
            log.debug('Distance query image %s and %s is %s', original.post_id, post.post_id, hamming_distance)
            if hamming_distance <= config.hamming_distance:
                final_results.append(result)

        return final_results


    def check_duplicate(self, post: Post):
        self._build_index()
        search_array = bytearray(post.dhash_h, encoding='utf-8')
        r = self.index.get_nns_by_vector(list(search_array), 50, search_k=20000, include_distances=True)
        results = list(zip(r[0], r[1]))
        self._clean_results(results, post.id)

    @property
    def annoy(self):
        pass