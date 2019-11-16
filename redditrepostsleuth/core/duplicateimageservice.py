import os
from typing import List, Tuple

from distance import hamming
from time import perf_counter

from sqlalchemy import Float

from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.exception import NoIndexException
from redditrepostsleuth.core.logging import log
from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager
from datetime import datetime
from annoy import AnnoyIndex

from redditrepostsleuth.core.db.databasemodels import Post, MemeTemplate
from redditrepostsleuth.core.model.events.annoysearchevent import AnnoySearchEvent
from redditrepostsleuth.core.model.imagematch import ImageMatch
from redditrepostsleuth.core.model.imagerepostwrapper import ImageRepostWrapper
from redditrepostsleuth.core.services.eventlogging import EventLogging
from redditrepostsleuth.core.util.helpers import is_image_still_available
from redditrepostsleuth.core.util.imagehashing import set_image_hashes, get_image_hashes
from redditrepostsleuth.core.util.objectmapping import annoy_result_to_image_match
from redditrepostsleuth.core.util.redlock import redlock
from redditrepostsleuth.core.util.reposthelpers import sort_reposts


class DuplicateImageService:
    def __init__(self, uowm: UnitOfWorkManager, event_logger: EventLogging, config: Config = None):

        self.uowm = uowm
        self.historical_index  = AnnoyIndex(64)
        self.historical_index_built_at = None
        self.historical_index_size = 0
        self.current_index = AnnoyIndex(64)
        self.current_index_built_at = None
        self.current_index_size = 0
        self.event_logger = event_logger

        if config:
            self.config = config
        else:
            self.config = Config()

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
        if self.current_index_built_at and (datetime.now() - self.current_index_built_at).seconds < self.config.index_current_skip_load_age:
            log.debug('Loaded index is less than 20 minutes old.  Skipping load')
            return

        log.debug('Index file is %s', self.config.index_current_file)
        if not os.path.isfile(self.config.index_current_file):
            if not self.current_index_built_at:
                log.error('No existing index found and no index loaded in memory')
                raise NoIndexException('No existing index found')
            elif self.current_index_built_at and (datetime.now() - self.current_index_built_at).seconds > 7200:
                log.error('No existing index found and loaded index is too old')
                raise NoIndexException('No existing index found')
            else:
                log.info('No existing index found, using in memory index')
                return

        created_at = datetime.fromtimestamp(os.stat(self.config.index_current_file).st_ctime)
        delta = datetime.now() - created_at

        if delta.seconds > 7200:
            log.info('Existing current index is too old.  Skipping repost check')
            raise NoIndexException('Existing current index is too old')

        if not self.current_index_built_at:
            with redlock.create_lock('index_load', ttl=30000):
                log.debug('Loading existing index')
                self.current_index = AnnoyIndex(64)
                self.current_index.load(self.config.index_current_file)
                self.current_index_built_at = created_at
                self.current_index_size = self.current_index.get_n_items()
                log.info('Loaded current image index with %s items', self.current_index.get_n_items())
                return

        if created_at > self.current_index_built_at:
            log.info('Existing current image index is newer than loaded index.  Loading new index')
            with redlock.create_lock('index_load', ttl=30000):
                log.info('Got index lock')
                self.current_index = AnnoyIndex(64)
                self.current_index.load(self.config.index_current_file)
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

        if self.historical_index_built_at and (datetime.now() - self.historical_index_built_at).seconds < self.config.index_historical_skip_load_age:
            log.debug('Loaded index is less than 72 hours old.  Skipping load')
            return

        log.debug('Historical image index file is %s', self.config.index_historical_file)
        if not os.path.isfile(self.config.index_historical_file):
            if not self.historical_index_built_at:
                log.error('No existing historical image index found and no index loaded in memory')
                raise NoIndexException('No existing index found')
            else:
                # Hits this if no index file but one already loaded in memeory
                log.info('No existing index found, using in memory index')
                return

        created_at = datetime.fromtimestamp(os.stat(self.config.index_historical_file).st_ctime)
        delta = datetime.now() - created_at

        if created_at.month < datetime.now().month:
            log.info('Existing historical image index is too old. Index month: %s, current month %s Skipping repost check', created_at.month, datetime.now().month)
            raise NoIndexException('Existing historical image index is too old')

        if not self.historical_index_built_at:
            with redlock.create_lock('index_load', ttl=30000):
                log.debug('Loading existing historical image index')
                self.historical_index = AnnoyIndex(64)
                self.historical_index.load(self.config.index_historical_file)
                self.historical_index_built_at = created_at
                self.historical_index_size = self.historical_index.get_n_items()
                log.info('Loaded existing historical image index with %s items', self.historical_index.get_n_items())
                return

        if created_at > self.historical_index_built_at:
            log.info('Existing historical image index is newer than loaded index.  Loading new index')
            log.error('Loading newer historical image index file.  Old file had %s items,', self.historical_index.get_n_items())
            with redlock.create_lock('index_load', ttl=30000):
                log.info('Got index lock')
                self.historical_index = AnnoyIndex(64)
                self.historical_index.load(self.config.index_historical_file)
                self.historical_index_built_at = created_at
                log.error('New file has %s items', self.historical_index.get_n_items())
                log.info('New historical image index loaded with %s items', self.historical_index.get_n_items())
                if self.historical_index.get_n_items() < self.historical_index_size:
                    log.critical('New historical image index has less items than old. Aborting repost check')
                    raise NoIndexException('New historical image index has less items than last index')
                self.historical_index_size = self.historical_index.get_n_items()

        else:
            log.debug('Loaded index is up to date.  Using with %s items', self.historical_index.get_n_items())


    def _filter_results_for_reposts(
            self,
            matches: List[ImageMatch],
            checked_post: Post,
            target_hamming_distance: int = None,
            target_annoy_distance: float = None,
            same_sub: bool = False,
            date_cutoff: int = None,
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
            target_hamming_distance = target_hamming_distance or self.config.default_hamming_distance

        target_annoy_distance = target_annoy_distance or self.config.default_annoy_distance

        results = []
        log.info('Target Annoy Dist: %s - Target Hamming Dist: %s', target_annoy_distance, target_hamming_distance)
        log.info('Meme Filter: %s - Only Older: %s - Day Cutoff: %s - Same Sub: %s', is_meme, only_older_matches, date_cutoff, same_sub)
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
            if date_cutoff and (datetime.utcnow() - match.post.created_at).days > date_cutoff:
                log.debug('Date Cutoff Reject: Target: %s Actual: %s - %s', date_cutoff, (datetime.utcnow() - match.post.created_at).days, f'https://redd.it/{match.post.post_id}')
                continue
            if checked_post.author == match.post.author:
                # TODO - Need logic to check age and sub of matching posts with same author
                continue

            # TODO - Clean up this cluster fuck
            if match.hamming_distance > (target_hamming_distance if not is_meme else 0): # If it's a meme use 0 first pass on default hash.
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
                                 result_filter: bool = True,
                                 max_matches: int = 75,  # TODO -
                                 target_hamming_distance: int = None,
                                 target_annoy_distance: float = None,
                                 same_sub: bool = False,
                                 date_cutoff: int = None,
                                 filter_dead_matches: bool = True,
                                 only_older_matches=True,
                                 meme_filter=False) -> ImageRepostWrapper:
        """
        Wrapper around check_duplicates to keep existing API intact
        :rtype: ImageRepostWrapper
        :param post: Post object
        :param result_filter: Filter the returned result or return raw results
        :param target_hamming_distance: Only return matches below this value
        :param target_annoy_distance: Only return matches below this value.  This is checked first
        :return: List of matching images
        """
        log.info('Checking %s for duplicates - https://redd.it/%s', post.post_id, post.post_id)
        self._load_index_files()
        search_results = ImageRepostWrapper()
        start = perf_counter()
        search_array = bytearray(post.dhash_h, encoding='utf-8')
        current_results = []

        raw_results = self._search_index_by_vector(search_array, self.historical_index, max_matches=max_matches)
        raw_results = filter(
            self._annoy_filter(target_annoy_distance or self.config.default_annoy_distance),
            raw_results
        ) # Pre-filter results on default annoy value
        historical_results = self._convert_annoy_results(raw_results, post.id)
        self._set_match_posts(historical_results)

        # TODO - I don't like duplicating this code.  Oh well
        if self.current_index:
            raw_results = self._search_index_by_vector(search_array, self.current_index, max_matches=max_matches)
            raw_results = filter(
                self._annoy_filter(target_annoy_distance or self.config.default_annoy_distance),
                raw_results
            )  # Pre-filter results on default annoy value
            current_results = self._convert_annoy_results(raw_results, post.id)
            self._set_match_posts(current_results, historical=False)
            search_results.total_searched = search_results.total_searched + self.current_index.get_n_items()
        else:
            log.error('No current image index loaded.  Only using historical results')

        search_results.matches = self._merge_search_results(historical_results, current_results)
        search_results.index_search_time = round(perf_counter() - start, 5)

        if result_filter:
            self._set_match_hamming(post, search_results.matches)
            meme_template = None
            # TODO - Possibly make this optional instead of running on each check
            if meme_filter:
                meme_template = self.get_meme_template(post)
                if meme_template:
                    search_results.meme_template = meme_template
                    target_hamming_distance = meme_template.target_hamming
                    target_annoy_distance = meme_template.target_annoy
                    log.info('Using meme filter %s', meme_template.name)
                    log.debug('Got meme template, overriding distance targets. Target is %s', target_hamming_distance)


            search_results.matches = self._filter_results_for_reposts(search_results.matches, post,
                                                                      target_annoy_distance=target_annoy_distance,
                                                                      target_hamming_distance=target_hamming_distance,
                                                                      same_sub=same_sub,
                                                                      date_cutoff=date_cutoff,
                                                                      filter_dead_matches=filter_dead_matches,
                                                                      only_older_matches=only_older_matches,
                                                                      is_meme=meme_template or False)
        else:
            self._set_match_posts(search_results.matches)
            self._set_match_hamming(post, search_results.matches)

        search_results.checked_post = post
        search_results.total_search_time = round(perf_counter() - start, 5)
        search_results.total_searched = self.current_index.get_n_items() if self.current_index else 0
        search_results.total_searched = search_results.total_searched + self.historical_index.get_n_items()
        self._log_search_time(search_results)
        return search_results

    def _filter_search_results(self):
        pass

    def _search_index_by_vector(self, vector: bytearray, index: AnnoyIndex, max_matches=50) -> List[ImageMatch]:
        r = index.get_nns_by_vector(list(vector), max_matches, search_k=20000, include_distances=True)
        return self._zip_annoy_results(r)

    def _search_index_by_id(self, post_id: int, index: AnnoyIndex) -> List[ImageMatch]:
        pass

    def _zip_annoy_results(self, annoy_results: List[tuple]) -> Tuple[int, float]:
        return list(zip(annoy_results[0], annoy_results[1]))

    def _convert_annoy_results(self, annoy_results, checked_post_id: int):
        return [annoy_result_to_image_match(match, checked_post_id) for match in annoy_results]

    def _annoy_filter(self, target_annoy_distance: Float):
        def annoy_distance_filter(match):
            return match[1] < target_annoy_distance
        return annoy_distance_filter

    def _log_search_time(self, search_results: ImageRepostWrapper):
        self.event_logger.save_event(
            AnnoySearchEvent(
                total_search_time=search_results.total_search_time,
                index_search_time=search_results.index_search_time,
                index_size=search_results.total_searched,
                event_type='duplicate_image_search'
            )
        )

    def _merge_search_results(self, first: List[ImageMatch], second: List[ImageMatch]) -> List[ImageMatch]:
        results = first.copy()
        for a in second:
            match = next((x for x in results if x.match_id == a.match_id), None)
            if match:
                continue
            results.append(a)

        return results


    def _set_match_posts(self, matches: List[ImageMatch], historical: bool = True) -> List[ImageMatch]:
        """
        Attach each matches corresponding database entry.
        Due to how annoy uses IDs to allocate memory we have to maintain 2 image post tables. 1 for all posts up until
        the start of the current month.  A 2nd to maintain this months posts.
        :param historical:
        :rtype: List[ImageMatch]
        :param matches: List of matches
        """
        with self.uowm.start() as uow:
            for match in matches:
                # TODO - Clean this shit up once I fix relationships
                # Hit the correct table if historical or current
                if historical:
                    original_image_post = uow.image_post.get_by_id(match.match_id)
                else:
                    original_image_post = uow.image_post_current.get_by_id(match.match_id)

                if not original_image_post:
                    log.error('Failed to lookup original match post. ID %s - Historical: %s', match.match_id, historical)
                    continue

                match_post = uow.posts.get_by_post_id(original_image_post.post_id)
                match.post = match_post
                match.match_id = match_post.id
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