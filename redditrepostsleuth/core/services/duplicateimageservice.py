import json
import logging
from logging import LoggerAdapter
from typing import List, Text, Optional

import requests
from distance import hamming
from praw import Reddit
from requests.exceptions import ConnectionError

from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.db.databasemodels import Post, MemeTemplate, RepostSearch
from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.core.exception import NoIndexException, ImageConversionException
from redditrepostsleuth.core.logging import get_configured_logger
from redditrepostsleuth.core.model.events.annoysearchevent import AnnoySearchEvent
from redditrepostsleuth.core.model.image_index_api_result import APISearchResults, ImageMatch
from redditrepostsleuth.core.model.image_search_settings import ImageSearchSettings
from redditrepostsleuth.core.model.search.image_search_match import ImageSearchMatch
from redditrepostsleuth.core.model.search.image_search_results import ImageSearchResults
from redditrepostsleuth.core.services.eventlogging import EventLogging
from redditrepostsleuth.core.util.helpers import create_search_result_json, get_default_image_search_settings
from redditrepostsleuth.core.util.imagehashing import get_image_hashes
from redditrepostsleuth.core.util.repost_filters import annoy_distance_filter, hamming_distance_filter, \
    filter_no_dhash
from redditrepostsleuth.core.util.repost_helpers import sort_reposts, get_closest_image_match, set_all_title_similarity, \
    filter_search_results

log = logging.getLogger(__name__)

class DuplicateImageService:
    def __init__(
            self,
            uowm: UnitOfWorkManager,
            event_logger: EventLogging,
            reddit: Reddit,
            config: Config = None,
            ):
        self.reddit = reddit
        self.uowm = uowm
        self.event_logger = event_logger
        if config:
            self.config = config
        else:
            self.config = Config()
        log.info('Created dup image service')

    def _filter_results_for_reposts(
            self,
            search_results: ImageSearchResults,
            sort_by='created'
    ) -> ImageSearchResults:
        """
        Take a list of matches and filter out posts that are not reposts.
        This is done via distance checking, creation date, crosspost
        :param checked_post: The post we're finding matches for
        :param search_results: A cleaned list of matches
        :param target_hamming_distance: Hamming cutoff for matches
        :param target_annoy_distance: Annoy cutoff for matches
        :rtype: List[ImageSearchMatch]
        """

        log.debug('Starting result filters with %s matches', len(search_results.matches))

        search_results.matches = list(filter(filter_no_dhash, search_results.matches))

        search_results = filter_search_results(
            search_results,
            reddit=self.reddit,
            uitl_api=f'{self.config.util_api}/maintenance/removed'
        )

        search_results.search_times.start_timer('get_closest_match_time')
        # Since we regenerate the hash for memes we have to make sure the match is alive regardless of setting
        if search_results.meme_template:
            closest_check_url = True
        else:
            closest_check_url = search_results.search_settings.filter_dead_matches
        closest_match = get_closest_image_match(search_results.matches, check_url=closest_check_url)
        search_results.search_times.stop_timer('get_closest_match_time')

        if closest_match and closest_match.hamming_match_percent > 40: # TODO - Move to config
            search_results.closest_match = closest_match
            if search_results.closest_match and search_results.meme_template:
                search_results.search_times.start_timer('set_closest_meme_hash_time')
                match_hash = self._get_meme_hash(search_results.closest_match.post.url)
                search_results.closest_match.hamming_distance = hamming(search_results.meme_hash, match_hash)
                search_results.closest_match.hash_size = len(match_hash)
                search_results.search_times.stop_timer('set_closest_meme_hash_time')

        # Has to be after closest match so we don't drop closest
        search_results.search_times.start_timer('distance_filter_time')
        search_results.matches = list(filter(annoy_distance_filter(search_results.search_settings.target_annoy_distance), search_results.matches))
        search_results.matches = list(filter(hamming_distance_filter(search_results.target_hamming_distance), search_results.matches))
        search_results.search_times.stop_timer('distance_filter_time')

        if search_results.meme_template:
            search_results.search_times.start_timer('meme_filter_time')
            search_results.matches = self._final_meme_filter(search_results.meme_hash, search_results.matches,
                                              search_results.target_meme_hamming_distance)
            search_results.search_times.stop_timer('meme_filter_time')

        search_results.matches = sort_reposts(search_results.matches, sort_by=sort_by)

        for match in search_results.matches:
            log.debug('Match found: %s - A:%s H:%s P:%s', f'https://redd.it/{match.post.post_id}',
                      round(match.annoy_distance, 5), match.hamming_distance, f'{match.hamming_match_percent}%')

        return search_results

    def check_image(
            self,
            url: Text,
            post: Post = None,
            source='unknown',
            sort_by='created',
            search_settings: ImageSearchSettings = None,

    ) -> ImageSearchResults:
        """
        Execute a search for a given image
        :param url: URL of image to search for
        :param post: Database post object
        :param source: Source that triggered this search.  Used for logging
        :param sort_by: Sort results by
        :param search_settings: Search settings to use when searching
        :return: Search Results
        :rtype: ImageSearchResults
        """
        log.info('Checking URL for matches: %s', url)

        if not search_settings:
            log.info('No search settings provided, using default')
            search_settings = get_default_image_search_settings(self.config)

        search_results = ImageSearchResults(
            url,
            checked_post=post,
            search_settings=search_settings
        )

        search_results.search_times.start_timer('total_search_time')

        if search_settings.meme_filter:
            search_results.search_times.start_timer('meme_detection_time')
            search_results.meme_template = self._get_meme_template(search_results.target_hash)
            search_results.search_times.stop_timer('meme_detection_time')
            if search_results.meme_template:
                search_settings.target_match_percent = 100  # Keep only 100% matches on default hash size
                search_results.search_times.start_timer('set_meme_hash_time')
                search_results.meme_hash = self._get_meme_hash(url)
                search_results.search_times.stop_timer('set_meme_hash_time')
                if not search_results.meme_hash:
                    log.error('No meme hash, disabled meme filter')
                    search_results.meme_template = None
                else:
                    log.info('Using meme filter %s', search_results.meme_template.id)

        log.debug('Search Settings: %s', search_settings)

        search_results.search_times.start_timer('image_search_api_time')
        api_search_results = self._get_matches(
            search_results.target_hash,
            search_results.target_hamming_distance,
            search_settings.target_annoy_distance,
            max_matches=search_settings.max_matches,
            max_depth=search_settings.max_depth,
        )
        search_results.search_times.stop_timer('image_search_api_time')

        search_results.search_times.index_search_time = float(api_search_results.total_search_time)
        search_results.total_searched = api_search_results.total_searched

        search_results.search_times.start_timer('set_match_post_time')
        search_results.matches = self._build_search_results(api_search_results, url, search_results.target_hash)

        search_results.search_times.stop_timer('set_match_post_time')

        search_results.search_times.start_timer('remove_duplicate_time')
        search_results.matches = self._remove_duplicates(search_results.matches)
        search_results.search_times.stop_timer('remove_duplicate_time')

        if post and search_results.search_settings.check_title:
            search_results.search_times.start_timer('set_title_similarity_time')
            search_results.matches = set_all_title_similarity(search_results.checked_post.title, search_results.matches)
            search_results.search_times.stop_timer('set_title_similarity_time')

        search_results = self._filter_results_for_reposts(
            search_results,
            sort_by=sort_by
        )
        search_results.search_times.stop_timer('total_search_time')
        self._log_search_time(search_results, source)

        search_results = self._log_search(
            search_results,
            source
        )

        log.info('Seached %s items and found %s matches', search_results.total_searched, len(search_results.matches))
        return search_results

    def _get_meme_hash(self, url: Text) -> Optional[Text]:
        """
        Take a given URL and return the hash that will be used for the meme filter
        :param url: URL to hash
        :return: Hash of the image
        :rtype: Optional[Text]
        """
        try:
            meme_hashes = get_image_hashes(url, hash_size=self.config.default_meme_filter_hash_size)
            return meme_hashes['dhash_h']
        except ImageConversionException:
            log.error('Failed to get meme hash')
            return
        except Exception:
            log.exception('Failed to get meme hash for %s', url, exc_info=True)
            return

    def _get_matches(
            self,
            hash: Text,
            target_hamming_distance: float,
            target_annoy_distance: float,
            max_matches: int = 50,
            max_depth: int = 4000,
    ) -> APISearchResults:
        """
        Take a given hash and search the image index API for matches
        :param hash: Hash of image to search
        :param target_hamming_distance: Target hamming distance
        :param target_annoy_distance: Target annoy distance
        :param max_matches: Max results to fetch from index API
        :param max_depth: Max depth to search index
        :rtype: ImageIndexApiResult
        """
        try:

            params = {
                'hash': hash,
                'max_results': max_matches,
                'max_depth': max_depth,
                'a_filter': target_annoy_distance,
                'h_filter': target_hamming_distance
            }
            r = requests.get(f'{self.config.index_api}/image', params=params)
        except ConnectionError:
            log.error('Failed to connect to Index API')
            raise NoIndexException('Failed to connect to Index API')
        except Exception as e:
            log.exception('Problem with image index api', exc_info=True)
            raise

        if r.status_code != 200:
            log.error('Unexpected status from index API: %s', r.status_code)
            raise NoIndexException(f'Unexpected status: {r.status_code}')

        res_data = json.loads(r.text)

        try:
            return APISearchResults(**res_data)
        except TypeError as e:
            raise NoIndexException(f'Failed to convert API result: {str(e)}')

    def _build_search_results(
            self,
            api_search_results: APISearchResults,
            url: Text,
            searched_hash: Text,
    ) -> List[ImageSearchMatch]:
        """
        Take a list of index matches and convert them to ImageSearchMatches
        :param index_matches: Dict of raw matches from index search
        :param url: URL of the image we searched
        :return:
        """
        results = []
        log.info('Building search results from index matches')
        with self.uowm.start() as uow:
            for r in api_search_results.results:
                for match in r.matches:
                    image_match = self._get_image_search_match_from_index_result(match, r.index_name, url, searched_hash)
                    if image_match:
                        results.append(image_match)
        log.debug('%s results built', len(results))
        return results

    def _get_image_search_match_from_index_result(
            self,
            result: ImageMatch,
            index_name: str,
            url: Text,
            searched_hash: str,
    ) -> Optional[ImageSearchMatch]:

        with self.uowm.start() as uow:
            index_map = uow.image_index_map.get_by_id_and_index(result.id, index_name)

            if not index_map:
                log.error('Failed to find index map for id %s in index %s', result.id, index_name)
                return

            post = uow.posts.get_by_id(index_map.post_id)

        if not post:
            return

        log.debug(post.url)

        if not post.hash_1:
            log.error('Post %s missing dhash', post.post_id)
            return

        return ImageSearchMatch(
            url,
            index_map.post_id,
            post,
            hamming(searched_hash, post.hash_1),
            result.distance,
            len(post.hash_1)
        )

    def _log_search_time(self, search_results: ImageSearchResults, source: Text):
        self.event_logger.save_event(
            AnnoySearchEvent(
                search_results.search_times,
                event_type='duplicate_image_search',
                source=source
            )
        )

    def _log_search(
            self,
            search_results: ImageSearchResults,
            source: str,
    ) -> ImageSearchResults:

        logged_search = RepostSearch(
            post_id=search_results.checked_post.id,
            subreddit=search_results.checked_post.subreddit if search_results.checked_post else None,
            source=source,
            search_params=json.dumps(search_results.search_settings.to_dict()),
            matches_found=len(search_results.matches),
            search_time=search_results.search_times.total_search_time,
            post_type='image'
        )

        with self.uowm.start() as uow:
            uow.repost_search.add(logged_search)
            try:
                uow.commit()
                search_results.logged_search = logged_search
            except Exception as e:
                log.exception('Failed to save image search')

        return search_results

    def _remove_duplicates(self, matches: List[ImageSearchMatch]) -> List[ImageSearchMatch]:
        log.debug('Remove duplicates from %s matches', len(matches))
        results = []
        for a in matches:
            match = next((x for x in results if x.post.id == a.post.id), None)
            if match:
                continue
            results.append(a)
        log.debug('%s matches after duplicate removal', len(results))
        return results


    def _get_meme_template(self, image_hash: Text) -> Optional[MemeTemplate]:
        try:
            r = requests.get(f'{self.config.index_api}/meme', params={'hash': image_hash})
        except Exception as e:
            log.exception('Failed to get meme template from api', exc_info=True)
            return

        if r.status_code != 200:
            log.error('Unexpected Index API status %s. %s', r.status_code, r.text)
            return

        results = json.loads(r.text)

        if not results['meme_template_id']:
            return

        with self.uowm.start() as uow:
            return uow.meme_template.get_by_id(results['meme_template_id'])

    def _final_meme_filter(
            self,
            searched_hash: Text,
            matches: List[ImageSearchMatch],
            target_hamming
    ) -> List[ImageSearchMatch]:
        results = []
        log.debug('MEME FILTER - Filtering %s matches', len(matches))
        if len(matches) == 0:
            return matches

        for match in matches:
            match_hash = self._get_meme_hash(match.post.url)
            if not match_hash:
                continue
            h_distance = hamming(searched_hash, match_hash)

            if h_distance > target_hamming:
                log.info('Meme Hamming Filter Reject - Target: %s Actual: %s - %s', target_hamming,
                         h_distance, f'https://redd.it/{match.post.post_id}')
                continue
            log.debug('Match found: %s - H:%s', f'https://redd.it/{match.post.post_id}',
                      h_distance)
            match.hamming_distance = h_distance
            match.hash_size = len(searched_hash)
            results.append(match)

        return results

