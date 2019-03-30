import os
import random
import time
from typing import List

from distance import hamming

from redditrepostsleuth.common.logging import log
from redditrepostsleuth.config import config
from redditrepostsleuth.db.uow.unitofworkmanager import UnitOfWorkManager
from datetime import datetime
from annoy import AnnoyIndex

from redditrepostsleuth.model.db.databasemodels import Post
from redditrepostsleuth.model.imagematch import ImageMatch
from redditrepostsleuth.util import redlock
from redditrepostsleuth.util.objectmapping import annoy_result_to_image_match


class DuplicateImageService:
    def __init__(self, uowm: UnitOfWorkManager):
        self.uowm = uowm
        self.index  = AnnoyIndex(64)
        self.index_last_build = None
        self.index_size = 0
        self._load_index_file()

    def _build_index(self):
        """
        Check if the index has expired.  Build a new one if it has.

        This gets tricky since celery can be running many processes.  We don't wait every process trying to build a new index
        at the same time.  To prevent this we use RedLock to create a lock in Redis. Every new task that comes in will try
        to get the index file. If that files doesn't exist it will try to build it. If any process fails to get the lock
        the task fails and is retryed in 3 minutes.
        """


        if self.index_last_build is None or (datetime.now() - self.index_last_build).seconds > config.index_keep_alive:

            if self._load_index_file():
                log.error('Index file returned true')
                return

            time.sleep(random.randint(10,30)) # Keep multiple processes from grabbing lock all at once
            log.debug('%s - Attempting to get index lock', os.getpid())

            # Check for index one more time. I keep having processes start another rebuild just as one finishes
            if self._load_index_file():
                log.error('Index file returned true')
                return

            lock_name = 'index_lock_' + config.machine_id
            with redlock.create_lock(lock_name, ttl=config.index_build_lock_ttl):
                log.info('%s - Got Lock', os.getpid())
                log.info('Building new Annoy index')
                self.index = AnnoyIndex(64)
                if os.path.isfile(config.index_file_name):
                    log.info('Deleting existing index file')
                    os.remove(config.index_file_name)
                start = datetime.now()
                with self.uowm.start() as uow:
                    offset = 0
                    while True:
                        log.info('Loading 100000 image hashes')
                        existing_images = uow.posts.find_all_images_with_hash_return_id_hash(offset=offset, limit=1000000)
                        if not existing_images:
                            log.info('No more image hashes to load')
                            break
                        delta = datetime.now() - start
                        log.info('Loaded %s images in %s seconds', len(existing_images), delta.seconds)
                #log.info('Index will be built with %s hashes', len(existing_images))
                #self.index_size = len(existing_images)
                        for image in existing_images:
                            vector = list(bytearray(image[1], encoding='utf-8'))
                            self.index.add_item(image[0], vector)
                        offset += 1000000

                self.index.build(config.index_tree_count)
                log.debug('Before index save')
                self.index.save(config.index_file_name)
                log.debug('After index save')
                self.index_last_build = datetime.now()
                delta = datetime.now() - start
                log.info('Total index build time was %s seconds', delta.seconds)
                time.sleep(15)


    def _load_index_file(self) -> bool:
        """
        Check if index file exists.  If it does, check it's age.  If it's fresh enough use it, if not build one
        :return:
        """
        log.info('%s - Attempting to load Annoy index file', os.getpid())
        if os.path.isfile(config.index_file_name):
            log.info('%s = Found Annoy index', os.getpid())
            created_at = datetime.fromtimestamp(os.stat(config.index_file_name).st_ctime)
            delta = datetime.now() - created_at
            log.info('%s - Indexed created %s seconds ago', os.getpid(), delta.seconds)
            if delta.seconds > config.index_keep_alive:
                log.info('%s - Index is too old.  Not using', os.getpid())
                return False
            else:
                log.info('%s - Index is fresh, using it', os.getpid())
                self.index = AnnoyIndex(64)
                self.index_last_build = created_at
                self.index.load(config.index_file_name)
                return True
        else:
            log.info('%s - No existing index file found', os.getpid())
            return False


    def _clean_results(self, results: List[ImageMatch], orig_id: int) -> List[ImageMatch]:
        """
        Take a list of matches and filter out the results.
        :param results: List of ImageMatch
        :param orig_id: ID of the post we are checked for reposts
        :return:
        """
        with self.uowm.start() as uow:
            original = uow.posts.get_by_id(orig_id)

        final_results = []
        for match in results:
            if match.annoy_distance > 0.265:
                #log.debug('Skipping result with distance %s', result[1])
                continue
            # Skip original query (result[0] is DB ID)
            if match.match_id == match.original_id:
                continue

            with self.uowm.start() as uow:
                match.post = uow.posts.get_by_id(match.match_id)

            if original.author == match.post.author:
                log.debug('Skipping post with same Author')
                continue

            if match.post.created_at > original.created_at:
                log.debug('Skipping match that is newer than the post we are checking. Original: %s - Match: %s', original.created_at, match.post.created_at)

            match.hamming_distance = hamming(original.dhash_h, match.post.dhash_h)

            if match.hamming_distance <= config.hamming_cutoff:
                log.debug('Match %s: Annoy %s - Ham: %s', match.match_id, match.hamming_distance, match.annoy_distance)
                final_results.append(match)
            else:
                #log.debug('Passed annoy and failed hamming. (Anny: %s - Ham: %s) - %s', result[1], hamming_distance, result[0])
                pass

        return final_results


    def check_duplicate(self, post: Post) -> List[ImageMatch]:
        # TODO: Load and append post object to each match
        self._build_index()
        log.debug('%s - Checking %s for duplicates', os.getpid(), post.post_id)
        log.debug('Image hash: %s', post.dhash_h)
        search_array = bytearray(post.dhash_h, encoding='utf-8')
        r = self.index.get_nns_by_vector(list(search_array), 50, search_k=20000, include_distances=True)
        results = list(zip(r[0], r[1]))
        matches = [annoy_result_to_image_match(match, post.id) for match in results]
        return self._clean_results(matches, post.id)

    @property
    def annoy(self):
        pass