import os
from typing import List

from distance import hamming
from time import perf_counter
from redditrepostsleuth.core.exception import NoIndexException
from redditrepostsleuth.core.logging import log
from redditrepostsleuth.core.config import config
from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager
from datetime import datetime
from annoy import AnnoyIndex

from redditrepostsleuth.core.db.databasemodels import Post, MemeTemplate
from redditrepostsleuth.core.model.imagematch import ImageMatch
from redditrepostsleuth.core.model.imagerepostwrapper import ImageRepostWrapper
from redditrepostsleuth.core.util.helpers import is_image_still_available
from redditrepostsleuth.core.util.imagehashing import set_image_hashes
from redditrepostsleuth.core.util.objectmapping import annoy_result_to_image_match
from redditrepostsleuth.core.util.redlock import redlock
from redditrepostsleuth.core.util.reposthelpers import sort_reposts


class DuplicateImageService:
    def __init__(self, uowm: UnitOfWorkManager):
        self.uowm = uowm
        self.index  = AnnoyIndex(64)
        self.index_built_at = None
        self.index_size = 0
        #self._load_index_file()
        log.info('Created dup image service')


    def _load_index_file(self) -> None:
        """
        Check if index file exists.  If it does, check it's age.  If it's fresh enough use it, if not build one
        :return:
        """

        if self.index_built_at and (datetime.now() - self.index_built_at).seconds < 1200:
            log.debug('Loaded index is less than 20 minutes old.  Skipping load')
            return

        index_file = os.path.join('/opt/imageindex', config.index_file_name)
        log.debug('Index file is %s', index_file)
        if not os.path.isfile(index_file):
            if not self.index_built_at:
                log.error('No existing index found and no index loaded in memory')
                raise NoIndexException('No existing index found')
            elif self.index_built_at and (datetime.now() - self.index_built_at).seconds > 21600:
                log.error('No existing index found and loaded index is too old')
                raise NoIndexException('No existing index found')
            else:
                log.info('No existing index found, using in memory index')
                return


        created_at = datetime.fromtimestamp(os.stat(index_file).st_ctime)
        delta = datetime.now() - created_at

        if delta.seconds > 86400:
            log.info('Existing index is too old.  Skipping repost check')
            raise NoIndexException('Existing index is too old')

        if not self.index_built_at:
            with redlock.create_lock('index_load', ttl=30000):
                log.debug('Loading existing index')
                self.index = AnnoyIndex(64)
                self.index.load(index_file)
                self.index_built_at = created_at
                self.index_size = self.index.get_n_items()
                log.info('Loaded existing index with %s items', self.index.get_n_items())
                return

        if created_at > self.index_built_at:
            log.info('Existing index is newer than loaded index.  Loading new index')
            log.error('Loading newer index file.  Old file had %s items,', self.index.get_n_items())
            with redlock.create_lock('index_load', ttl=30000):
                log.info('Got index lock')
                self.index.load(index_file)
                self.index_built_at = created_at
                log.error('New file has %s items', self.index.get_n_items())
                log.info('New index loaded with %s items', self.index.get_n_items())
                if self.index.get_n_items() < self.index_size:
                    log.critical('New index has less items than old. Aborting repost check')
                    raise NoIndexException('New index has less items than last index')
                self.index_size = self.index.get_n_items()

        else:
            log.debug('Loaded index is up to date.  Using with %s items', self.index.get_n_items())


    def _filter_results_for_reposts(self, matches: List[ImageMatch],
                                    checked_post: Post,
                                    target_hamming_distance: int = None,
                                    target_annoy_distance: float = None,
                                    same_sub: bool = False, date_cutff: int = None,
                                    filter_dead_matches: bool = True,
                                    only_older_matches: bool = True,
                                    is_meme: bool = False) -> List[ImageMatch]:
        """
        Take a list of matches and filter out posts that are not reposts.
        This is done via distance checking, creation date, crosspost
        :param checked_post: The post we're finding matches for
        :param matches: A cleaned list of matches
        :param target_hamming_distance: Hamming cutoff for matches
        :param target_annoy_distance: Annoy cutoff for matches
        :rtype: List[ImageMatch]
        """
        # TODO - Allow array of filters to be passed
        # Dumb fix for 0 evaling to False
        if target_hamming_distance == 0:
            target_hamming_distance = 0
        else:
            target_hamming_distance = target_hamming_distance or config.hamming_cutoff

        target_annoy_distance = target_annoy_distance or config.annoy_match_cutoff
        self._set_match_posts(matches)
        self._set_match_hamming(checked_post, matches)
        results = []
        log.info('Checking %s %s for duplicates', checked_post.post_id, f'https://redd.it/{checked_post.post_id}')
        log.info('Target Annoy Dist: %s - Target Hamming Dist: %s', target_annoy_distance, target_hamming_distance)
        log.debug('Matches pre-filter: %s', len(matches))
        for match in matches:
            if not match.post.dhash_h:
                log.debug('Match %s missing dhash_h', match.post.post_id)
                continue
            if match.post.crosspost_parent:
                continue
            if same_sub and checked_post.subreddit != match.post.subreddit:
                log.debug('Same Sub Reject: Orig sub: %s - Match Sub: %s - %s', checked_post.subreddit, match.post.subreddit, f'https://redd.it/{match.post.post_id}')
                continue
            if match.annoy_distance > target_annoy_distance:
                log.debug('Annoy Filter Reject - Target: %s Actual: %s - %s', target_annoy_distance, match.annoy_distance, f'https://redd.it/{match.post.post_id}')
                continue
            if checked_post.post_id == match.post.post_id:
                continue
            if only_older_matches and match.post.created_at > checked_post.created_at:
                log.debug('Date Filter Reject: Target: %s Actual: %s - %s', checked_post.created_at.strftime('%Y-%d-%m'), match.post.created_at.strftime('%Y-%d-%m'), f'https://redd.it/{match.post.post_id}')
                continue
            if date_cutff and (datetime.utcnow() - match.post.created_at).days > date_cutff:
                log.debug('Date Cutoff Reject: Target: %s Actual: %s - %s', date_cutff, (datetime.utcnow() - match.post.created_at).days, f'https://redd.it/{match.post.post_id}')
                continue
            if checked_post.author == match.post.author:
                # TODO - Need logic to check age and sub of matching posts with same author
                continue

            if match.hamming_distance > target_hamming_distance:
                log.debug('Hamming Filter Reject - Target: %s Actual: %s - %s', target_hamming_distance,
                          match.hamming_distance, f'https://redd.it/{match.post.post_id}')
                continue
            log.debug('Match found: %s - A:%s H:%s', f'https://redd.it/{match.post.post_id}', round(match.annoy_distance, 5), match.hamming_distance)
            if filter_dead_matches:
                if not is_image_still_available(match.post.url):
                    log.debug('Active Image Reject: Imgae has been deleted from post https://redd.it/%s', match.post.post_id)
                    continue

            results.append(match)
        log.info('Matches post-filter: %s', len(results))
        if is_meme:
            results = self._final_meme_filter(set_image_hashes(checked_post, hash_size=32), results)

        return sort_reposts(results)

    def check_duplicates_wrapped(self, post: Post,
                                 filter: bool = True,
                                 max_matches: int = 75,
                                 target_hamming_distance: int = None,
                                 target_annoy_distance: float = None,
                                 same_sub: bool = False,
                                 date_cutff: int = None,
                                 filter_dead_matches: bool = True,
                                 only_older_matches=True,
                                 meme_filter=False) -> ImageRepostWrapper:
        """
        Wrapper around check_duplicates to keep existing API intact
        :rtype: ImageRepostWrapper
        :param post: Post object
        :param filter: Filter the returned result or return raw results
        :param target_hamming_distance: Only return matches below this value
        :param target_annoy_distance: Only return matches below this value.  This is checked first
        :return: List of matching images
        """
        self._load_index_file()
        result = ImageRepostWrapper()
        start = perf_counter()
        search_array = bytearray(post.dhash_h, encoding='utf-8')
        r = self.index.get_nns_by_vector(list(search_array), max_matches, search_k=20000, include_distances=True)
        search_results = list(zip(r[0], r[1]))
        result.matches = [annoy_result_to_image_match(match, post.id) for match in search_results]
        result.search_time = round(perf_counter() - start, 5)
        result.index_size = self.index.get_n_items()
        if filter:
            meme_template = None
            # TODO - Possibly make this optional instead of running on each check
            if meme_filter:
                meme_template = self.get_meme_template(post)
                if meme_template:
                    target_hamming_distance = meme_template.target_hamming
                    target_annoy_distance = meme_template.target_annoy
                    log.debug('Got meme template, overriding distance targets. Target is %s', target_hamming_distance)


            result.matches = self._filter_results_for_reposts(result.matches, post,
                                                              target_annoy_distance=target_annoy_distance,
                                                              target_hamming_distance=target_hamming_distance,
                                                              same_sub=same_sub,
                                                              date_cutff=date_cutff,
                                                              filter_dead_matches=filter_dead_matches,
                                                              only_older_matches=only_older_matches,
                                                              is_meme=False)
        else:
            self._set_match_posts(result.matches)
            self._set_match_hamming(post, result.matches)
        result.checked_post = post
        return result

    def _set_match_posts(self, matches: List[ImageMatch]) -> List[ImageMatch]:
        """
        Attach each matches corresponding database entry
        :rtype: List[ImageMatch]
        :param matches: List of matches
        """
        start = perf_counter()
        with self.uowm.start() as uow:
            for match in matches:
                # Hacky but we need this to get the original database post ID from the RedditImagePost object
                # TODO - Clean this shit up once I fix relationships
                original_image_post = uow.image_post.get_by_id(match.match_id)
                match_post = uow.posts.get_by_post_id(original_image_post.post_id)
                match.post = match_post
                match.match_id = match_post.id
        log.debug('Time to set match posts: %s', perf_counter() - start)
        return matches

    def get_meme_template(self, check_post: Post) -> MemeTemplate:
        """
        Check if a given post matches a known meme template.  If it is, use that templates distance override
        :param check_post: Post we're checking
        :rtype: List[ImageMatch]
        """
        with self.uowm.start() as uow:
            templates = uow.meme_template.get_all()

        for template in templates:
            h_distance = hamming(check_post.dhash_h, template.dhash_h)
            log.debug('Meme template %s: Hamming %s', template.name, h_distance)
            if (h_distance <= template.template_detection_hamming):
                log.info('Post %s matches meme template %s', f'https://redd.it/{check_post.post_id}', template.name)
                return template


    def _set_match_hamming(self, searched_post: Post, matches: List[ImageMatch]) -> List[ImageMatch]:
        """
        Take a list of ImageMatches and set the hamming distance vs origional post
        :rtype: List[ImageMatch]
        :param matches: List of ImageMatches
        :return: List of Imagematches
        """
        for match in matches:
            if not match.post:
                log.error('Match missing post object')
                continue
            if not match.post.dhash_h:
                log.error('Match %s missing dhash_h', match.post.post_id)
                continue
            match.hamming_distance = hamming(searched_post.dhash_h, match.post.dhash_h)
        return matches

    def _final_meme_filter(self, searched_post: Post, matches: List[ImageMatch]):
        matches = self._ramp_meme_hashes(matches)
        matches = self._set_match_hamming(searched_post, matches)
        result = []
        for match in matches:
            if match.hamming_distance > 10:
                log.info('Meme Hamming Filter Reject - Target: %s Actual: %s - %s', 10,
                          match.hamming_distance, f'https://redd.it/{match.post.post_id}')
                continue
            result.append(match)
        #return [match for match in matches if match.hamming_distance < 10]
        return result

    def _ramp_meme_hashes(self, matches: List[ImageMatch]) -> List[ImageMatch]:
        for match in matches:
            set_image_hashes(match.post, hash_size=32)
        return matches
