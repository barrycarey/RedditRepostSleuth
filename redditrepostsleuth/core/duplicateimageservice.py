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
from redditrepostsleuth.core.util.imagehashing import set_image_hashes, get_image_hashes
from redditrepostsleuth.core.util.objectmapping import annoy_result_to_image_match
from redditrepostsleuth.core.util.redlock import redlock
from redditrepostsleuth.core.util.reposthelpers import sort_reposts


class DuplicateImageService:
    def __init__(self, uowm: UnitOfWorkManager):
        self.uowm = uowm
        self.historical_index  = AnnoyIndex(64)
        self.historical_index_built_at = None
        self.historical_index_size = 0
        self.current_index = AnnoyIndex(64)
        self.current_index_built_at = None
        self.current_index_size = 0
        log.info('Created dup image service')

    def _load_index_files(self) -> None:
        try:
            self._load_current_index_file()
        except NoIndexException:
            log.error('No current image index found.  Continuing with historical')
            self.current_index = None

        self._load_historical_index_file()

    def _load_current_index_file(self) -> None:
        """
        Loads the current month index
        :return:
        """
        if self.current_index_built_at and (datetime.now() - self.current_index_built_at).seconds < 1200:
            log.debug('Loaded index is less than 20 minutes old.  Skipping load')
            return

        log.debug('Index file is %s', config.current_image_index)
        if not os.path.isfile(config.current_image_index):
            if not self.current_index_built_at:
                log.error('No existing index found and no index loaded in memory')
                raise NoIndexException('No existing index found')
            elif self.current_index_built_at and (datetime.now() - self.current_index_built_at).seconds > 7200:
                log.error('No existing index found and loaded index is too old')
                raise NoIndexException('No existing index found')
            else:
                log.info('No existing index found, using in memory index')
                return

        created_at = datetime.fromtimestamp(os.stat(config.current_image_index).st_ctime)
        delta = datetime.now() - created_at

        if delta.seconds > 7200:
            log.info('Existing current index is too old.  Skipping repost check')
            raise NoIndexException('Existing current index is too old')

        if not self.current_index_built_at:
            with redlock.create_lock('index_load', ttl=30000):
                log.debug('Loading existing index')
                self.current_index = AnnoyIndex(64)
                self.current_index.load(config.current_image_index)
                self.current_index_built_at = created_at
                self.current_index_size = self.current_index.get_n_items()
                log.info('Loaded current image index with %s items', self.current_index.get_n_items())
                return

        if created_at > self.current_index_built_at:
            log.info('Existing current image index is newer than loaded index.  Loading new index')
            with redlock.create_lock('index_load', ttl=30000):
                log.info('Got index lock')
                self.current_index.load(config.current_image_index)
                self.current_index_built_at = created_at
                log.error('New file has %s items', self.current_index.get_n_items())
                log.info('New current image index loaded with %s items', self.current_index.get_n_items())
                if self.current_index.get_n_items() < self.current_index_size:
                    log.critical('New current image index has less items than old. Aborting repost check')
                    raise NoIndexException('New current image index has less items than last index')
                self.current_index_size = self.current_index.get_n_items()

        else:
            log.debug('Loaded index is up to date.  Using with %s items', self.historical_index.get_n_items())

    def _load_historical_index_file(self) -> None:
        """
        Check if index file exists.  If it does, check it's age.  If it's fresh enough use it, if not build one
        :return:
        """

        if self.historical_index_built_at and (datetime.now() - self.historical_index_built_at).seconds < 259200:
            log.debug('Loaded index is less than 72 hours old.  Skipping load')
            return

        log.debug('Historical image index file is %s', config.historical_image_index)
        if not os.path.isfile(config.historical_image_index):
            if not self.historical_index_built_at:
                log.error('No existing historical image index found and no index loaded in memory')
                raise NoIndexException('No existing index found')
            else:
                # Hits this if no index file but one already loaded in memeory
                log.info('No existing index found, using in memory index')
                return

        created_at = datetime.fromtimestamp(os.stat(config.historical_image_index).st_ctime)
        delta = datetime.now() - created_at

        if created_at.month < datetime.now().month:
            log.info('Existing historical image index is too old. Index month: %s, current month %s Skipping repost check', created_at.month, datetime.now().month)
            raise NoIndexException('Existing historical image index is too old')

        if not self.historical_index_built_at:
            with redlock.create_lock('index_load', ttl=30000):
                log.debug('Loading existing historical image index')
                self.historical_index = AnnoyIndex(64)
                self.historical_index.load(config.historical_image_index)
                self.historical_index_built_at = created_at
                self.historical_index_size = self.historical_index.get_n_items()
                log.info('Loaded existing historical image index with %s items', self.historical_index.get_n_items())
                return

        if created_at > self.historical_index_built_at:
            log.info('Existing historical image index is newer than loaded index.  Loading new index')
            log.error('Loading newer historical image index file.  Old file had %s items,', self.historical_index.get_n_items())
            with redlock.create_lock('index_load', ttl=30000):
                log.info('Got index lock')
                self.historical_index.load(config.historical_image_index)
                self.historical_index_built_at = created_at
                log.error('New file has %s items', self.historical_index.get_n_items())
                log.info('New historical image index loaded with %s items', self.historical_index.get_n_items())
                if self.historical_index.get_n_items() < self.historical_index_size:
                    log.critical('New historical image index has less items than old. Aborting repost check')
                    raise NoIndexException('New historical image index has less items than last index')
                self.historical_index_size = self.historical_index.get_n_items()

        else:
            log.debug('Loaded index is up to date.  Using with %s items', self.historical_index.get_n_items())


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

            # TODO - Clean up this cluster fuck
            if match.hamming_distance > (target_hamming_distance if not is_meme else 0):
                log.debug('Hamming Filter Reject - Target: %s Actual: %s - %s', target_hamming_distance if not is_meme else 0,
                          match.hamming_distance, f'https://redd.it/{match.post.post_id}')
                continue

            if filter_dead_matches:
                if not is_image_still_available(match.post.url):
                    log.debug('Active Image Reject: Imgae has been deleted from post https://redd.it/%s', match.post.post_id)
                    continue

            log.debug('Match found: %s - A:%s H:%s', f'https://redd.it/{match.post.post_id}',
                      round(match.annoy_distance, 5), match.hamming_distance)

            results.append(match)
        log.info('Matches post-filter: %s', len(results))
        if is_meme:
            results = self._final_meme_filter(checked_post, results, target_hamming_distance)

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
        log.info('Checking %s for duplicates - https://redd.it/%s', post.post_id, post.post_id)
        self._load_index_files()
        result = ImageRepostWrapper()
        start = perf_counter()
        search_array = bytearray(post.dhash_h, encoding='utf-8')

        historical_r = self.historical_index.get_nns_by_vector(list(search_array), max_matches, search_k=20000, include_distances=True)
        historical_results = list(zip(historical_r[0], historical_r[1]))
        result.matches = [annoy_result_to_image_match(match, post.id) for match in historical_results]
        result.index_size = self.historical_index.get_n_items()

        if self.current_index:
            current_r = self.current_index.get_nns_by_vector(list(search_array), max_matches, search_k=20000, include_distances=True)
            current_results = list(zip(current_r[0], current_r[1]))
            result.matches = self._merge_search_results(result.matches, [annoy_result_to_image_match(match, post.id) for match in current_results])
            result.index_size = result.index_size + self.current_index.get_n_items()
        else:
            log.error('No current image index loaded.  Only using historical results')



        if filter:
            meme_template = None
            # TODO - Possibly make this optional instead of running on each check
            if meme_filter:
                meme_template = self.get_meme_template(post)
                if meme_template:
                    result.meme_template = meme_template
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
                                                              is_meme=meme_template or False)
        else:
            self._set_match_posts(result.matches)
            self._set_match_hamming(post, result.matches)
        result.checked_post = post
        result.search_time = round(perf_counter() - start, 5)
        return result

    def _merge_search_results(self, first: List[ImageMatch], second: List[ImageMatch]) -> List[ImageMatch]:
        results = first.copy()
        for a in second:
            match = next((x for x in results if x.match_id == a.match_id), None)
            if match:
                continue
            results.append(a)

        return results


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

    def _final_meme_filter(self, searched_post: Post, matches: List[ImageMatch], target_hamming):
        results = []
        try:
            target_hashes = get_image_hashes(searched_post, hash_size=32)
        except Exception as e:
            log.exception('Failed to convert target post for meme check', exc_info=True)
            return matches

        for match in matches:
            try:
                match_hashes = get_image_hashes(match.post, hash_size=32)
            except Exception as e:
                log.error('Failed to get meme hash for %s', match.post.id)
                continue

            h_distance = hamming(target_hashes['dhash_h'], match_hashes['dhash_h'])

            if h_distance > target_hamming:
                log.info('Meme Hamming Filter Reject - Target: %s Actual: %s - %s', target_hamming,
                          h_distance, f'https://redd.it/{match.post.post_id}')
                continue

            log.debug('Match found: %s - H:%s', f'https://redd.it/{match.post.post_id}',
                       h_distance)
            match.hamming_distance = h_distance
            results.append(match)

        return results

    @DeprecationWarning
    def _ramp_meme_hashes(self, matches: List[ImageMatch]) -> List[ImageMatch]:
        for match in matches:
            set_image_hashes(match.post, hash_size=32)
        return matches
