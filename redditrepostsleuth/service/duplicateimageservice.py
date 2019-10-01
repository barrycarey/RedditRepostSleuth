import os
import random
import time
from typing import List

from distance import hamming

from redditrepostsleuth.common.exception import NoIndexException
from redditrepostsleuth.common.logging import log
from redditrepostsleuth.config import config
from redditrepostsleuth.db.uow.unitofworkmanager import UnitOfWorkManager
from datetime import datetime
from annoy import AnnoyIndex

from redditrepostsleuth.model.db.databasemodels import Post
from redditrepostsleuth.model.imagematch import ImageMatch
from redditrepostsleuth.util.objectmapping import annoy_result_to_image_match
from redditrepostsleuth.util.reposthelpers import sort_reposts


class DuplicateImageService:
    def __init__(self, uowm: UnitOfWorkManager):
        self.uowm = uowm
        self.index  = AnnoyIndex(64)
        self.index_built_at = None

        log.info('Created dup image service')


    def _load_index_file(self) -> None:
        """
        Check if index file exists.  If it does, check it's age.  If it's fresh enough use it, if not build one
        :return:
        """

        if not os.path.isfile(config.index_file_name):
            if not self.index_built_at:
                log.error('No existing index found and no index loaded in memory')
                raise NoIndexException('No existing index found')
            elif self.index_built_at and (datetime.now() - self.index_built_at).seconds > 21600:
                log.error('No existing index found and loaded index is too old')
                raise NoIndexException('No existing index found')
            else:
                log.info('No existing index found, using in memory index')
                return

        created_at = datetime.fromtimestamp(os.stat(config.index_file_name).st_ctime)
        delta = datetime.now() - created_at

        if delta.seconds > 21600:
            log.info('Existing index is too old.  Skipping repost check')
            raise NoIndexException('Existing index is too old')

        if not self.index_built_at:
            log.debug('Loading existing index')
            self.index = AnnoyIndex(64)
            self.index.load(config.index_file_name)
            self.index_built_at = created_at
            log.info('Loaded existing index with %s items', self.index.get_n_items())
            return

        if created_at > self.index_built_at:
            log.info('Existing index is newer than loaded index.  Loading new index')
            log.error('Loading newer index file.  Old file had %s items,', self.index.get_n_items())
            self.index.load(config.index_file_name)
            self.index_built_at = created_at
            log.error('New file has %s items', self.index.get_n_items())
            log.info('New index loaded with %s items', self.index.get_n_items())

        else:
            log.info('Loaded index is up to date.  Using with %s items', self.index.get_n_items())


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
                # Hacky but we need this to get the original database post ID from the RedditImagePost object
                original_image_post = uow.image_post.get_by_id(match.match_id)
                match_post = uow.posts.get_by_post_id(original_image_post.post_id)

                match.post = match_post
                match.match_id = match_post.id

            if original.author == match.post.author:
                log.debug('Skipping post with same Author')
                continue

            if match.post.created_at > original.created_at:
                log.debug('Skipping match that is newer than the post we are checking. Original: %s - Match: %s', original.created_at, match.post.created_at)
                continue

            if match.post.crosspost_parent:
                log.debug("Skipping match that is a crosspost")
                continue

            match.hamming_distance = hamming(original.dhash_h, match.post.dhash_h)

            if match.hamming_distance <= config.hamming_cutoff:
                log.debug('Match %s: Annoy %s - Ham: %s', match.match_id, match.hamming_distance, match.annoy_distance)
                final_results.append(match)
            else:
                #log.debug('Passed annoy and failed hamming. (Anny: %s - Ham: %s) - %s', result[1], hamming_distance, result[0])
                pass

        return sort_reposts(final_results)


    def check_duplicate(self, post: Post) -> List[ImageMatch]:
        # TODO: Load and append post object to each match
        self._load_index_file()
        log.debug('%s - Checking %s for duplicates', os.getpid(), post.post_id)
        log.debug('Image hash: %s', post.dhash_h)
        search_array = bytearray(post.dhash_h, encoding='utf-8')
        r = self.index.get_nns_by_vector(list(search_array), 50, search_k=20000, include_distances=True)
        results = list(zip(r[0], r[1]))
        matches = [annoy_result_to_image_match(match, post.id) for match in results]
        return self._clean_results(matches, post.id)
