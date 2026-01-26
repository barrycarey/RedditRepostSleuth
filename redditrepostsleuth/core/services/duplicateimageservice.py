import json
import logging
from time import perf_counter
from typing import List, Text, Optional

import requests
from praw import Reddit
from requests.exceptions import ConnectionError
from sqlalchemy.exc import IntegrityError

from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.db.databasemodels import Post, MemeTemplate, MemeHash
from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.core.exception import NoIndexException, ImageConversionException
from redditrepostsleuth.core.model.events.imagesearchevent import ImageSearchEvent
from redditrepostsleuth.core.model.image_index_api_result import APISearchResults
from redditrepostsleuth.core.model.image_search_settings import ImageSearchSettings
from redditrepostsleuth.core.model.search.image_search_match import ImageSearchMatch
from redditrepostsleuth.core.model.search.image_search_results import ImageSearchResults
from redditrepostsleuth.core.services.eventlogging import EventLogging
from redditrepostsleuth.core.util.helpers import get_default_image_search_settings, hamming_distance_bits
from redditrepostsleuth.core.util.imagehashing import get_image_hashes
from redditrepostsleuth.core.util.repost.repost_helpers import sort_reposts, get_closest_image_match, \
    set_all_title_similarity, \
    filter_search_results, log_search
from redditrepostsleuth.core.util.repost_filters import hamming_distance_filter

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
        :param search_results: Search results containing matches to filter
        :param sort_by: How to sort the filtered results
        :rtype: ImageSearchResults
        """

        log.debug('Starting result filters with %s matches', len(search_results.matches))

        search_results = filter_search_results(search_results)

        search_results.search_times.start_timer('get_closest_match_time')
        # Since we regenerate the hash for memes we have to make sure the match is alive regardless of setting
        if search_results.meme_template:
            validate_checked_url = True
        else:
            validate_checked_url = search_results.search_settings.filter_dead_matches #
        closest_match = get_closest_image_match(search_results.matches, validate_url=validate_checked_url)
        search_results.search_times.stop_timer('get_closest_match_time')

        if closest_match and closest_match.hamming_match_percent > 40: # TODO - Move to config
            search_results.closest_match = closest_match
            if search_results.closest_match and search_results.meme_template:
                search_results.search_times.start_timer('set_closest_meme_hash_time')
                match_hash = self._get_meme_hash(search_results.closest_match.post.url)
                search_results.closest_match.hamming_distance = hamming_distance_bits(search_results.meme_hash, match_hash)
                search_results.closest_match.hash_size = len(match_hash) * 4  # Bit count
                search_results.search_times.stop_timer('set_closest_meme_hash_time')

        # Has to be after closest match so we don't drop closest
        search_results.search_times.start_timer('distance_filter_time')
        search_results.matches = list(filter(hamming_distance_filter(search_results.target_hamming_distance), search_results.matches))
        search_results.search_times.stop_timer('distance_filter_time')

        if search_results.meme_template:
            search_results.search_times.start_timer('meme_filter_time')
            search_results.matches = self._final_meme_filter(search_results.meme_hash, search_results.matches,
                                                             search_results.target_meme_hamming_distance)
            search_results.search_times.stop_timer('meme_filter_time')

        search_results.matches = sort_reposts(search_results.matches, sort_by=sort_by)

        for match in search_results.matches:
            log.debug('Match found: %s - H:%s P:%s', f'https://redd.it/{match.post.post_id}',
                      match.hamming_distance, f'{match.hamming_match_percent}%')

        return search_results

    def check_image(
            self,
            url: str,
            post: Post = None,
            source='unknown',
            sort_by='created',
            search_settings: ImageSearchSettings = None,
            target_hash: str = None,
            meme_hash: str = None,

    ) -> ImageSearchResults:
        """
        Execute a search for a given image
        :param url: URL of image to search for
        :param post: Database post object
        :param source: Source that triggered this search.  Used for logging
        :param sort_by: Sort results by
        :param search_settings: Search settings to use when searching
        :param target_hash: Pre-computed target hash (optional, avoids URL fetch)
        :param meme_hash: Pre-computed meme hash (optional, avoids URL fetch for meme detection)
        :return: Search Results
        :rtype: ImageSearchResults
        """
        log.debug('Checking URL for matches: %s', url)

        if not search_settings:
            log.info('No search settings provided, using default')
            search_settings = get_default_image_search_settings(self.config)

        search_results = ImageSearchResults(
            url,
            checked_post=post,
            search_settings=search_settings,
            target_hash=target_hash
        )

        search_results.search_times.start_timer('total_search_time')

        if search_settings.meme_filter:
            search_results.search_times.start_timer('meme_detection_time')
            search_results.meme_template = self._get_meme_template(search_results.target_hash, source=source)
            search_results.search_times.stop_timer('meme_detection_time')
            if search_results.meme_template:
                search_settings.target_match_percent = 100  # Keep only 100% matches on default hash size
                search_results.search_times.start_timer('set_meme_hash_time')
                if meme_hash:
                    search_results.meme_hash = meme_hash
                else:
                    search_results.meme_hash = self._get_meme_hash(url, post_id=post.post_id if post else None)
                search_results.search_times.stop_timer('set_meme_hash_time')
                if not search_results.meme_hash:
                    log.warning('No meme hash, disabled meme filter')
                    search_results.meme_template = None
                else:
                    log.info('Using meme filter %s', search_results.meme_template.id)

        log.debug('Search Settings: %s', search_settings)

        search_results.search_times.start_timer('image_search_api_time')
        api_search_results = self._get_matches(
            search_results.target_hash,
            search_results.target_hamming_distance,  # Bit-level distance (0-256)
            max_matches=search_settings.max_matches,
            source=source,
        )
        search_results.search_times.stop_timer('image_search_api_time')

        search_results.search_times.index_search_time = float(api_search_results.total_search_time)
        search_results.total_searched = api_search_results.total_searched

        # Pre-filter before expensive DB lookup
        search_results.search_times.start_timer('prefilter_time')
        api_search_results, _ = self._prefilter_api_results(
            api_search_results,
            search_results.target_hamming_distance,
            keep_top_n=10
        )
        search_results.search_times.stop_timer('prefilter_time')

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

        if search_results.matches:
            search_results = self._filter_results_for_reposts(
                search_results,
                sort_by=sort_by
            )
        search_results.search_times.stop_timer('total_search_time')
        self._log_search_time(search_results, source)
        with self.uowm.start() as uow:
            log_search(uow, search_results, source, 'image')

        log.debug('Searched %s items and found %s matches', search_results.total_searched, len(search_results.matches))
        return search_results

    def check_gallery(
            self,
            url: str,
            post: Post = None,
            source='unknown',
            sort_by='created',
            search_settings: ImageSearchSettings = None,

    ) -> ImageSearchResults:
        pass

    def _get_meme_hash(self, url: str, post_id=None) -> Optional[Text]:
        """
        Take a given URL and return the hash that will be used for the meme filter
        :param url: URL to hash
        :return: Hash of the image
        :rtype: Optional[Text]
        """
        meme_hash = None
        with self.uowm.start() as uowm:
            if post_id:
                start = perf_counter()
                meme_hash = uowm.meme_hash.get_by_post_id(post_id)
                log.debug('Meme cache query: %s', round(perf_counter() - start, 5))
                if meme_hash:
                    log.debug('Using cached meme hash')
                    return meme_hash.hash

            try:
                meme_hashes = get_image_hashes(url, hash_size=self.config.default_meme_filter_hash_size)
                meme_hash = meme_hashes['dhash_h']
            except ImageConversionException:
                log.warning('Failed to get meme hash. ')
                if post_id:
                    # TODO - This can potentially start deleting images if we drop internet connection
                    log.info('Sending post %s to delete queue', post_id)
                    #celery.send_task('redditrepostsleuth.core.celery.admin_tasks.delete_post_task', args=[post_id,])
                return
            except Exception:
                log.exception('Failed to get meme hash for %s', url, exc_info=True)
                return

            if meme_hash and post_id:
                log.debug('Saving meme hash')
                uowm.meme_hash.add(MemeHash(post_id=post_id, hash=meme_hash))
                try:
                    uowm.commit()
                except IntegrityError as e:
                    log.warning('Failed to save Meme hash, already exists. Post %s', post_id)
                except Exception as e:
                    log.exception('')

        return meme_hash

    def _get_matches(
            self,
            hash: Text,
            target_hamming_distance: float,
            max_matches: int = 50,
            source: str = 'unknown',
    ) -> APISearchResults:
        """
        Take a given hash and search the image index API for matches
        :param hash: Hash of image to search
        :param target_hamming_distance: Target hamming distance (in bits, 0-256 for 256-bit hash)
        :param max_matches: Max results to fetch from index API
        :param source: Source of the request for logging
        :rtype: APISearchResults
        """
        try:
            params = {
                'hash': hash,
                'max_results': max_matches,
                #'h_filter': target_hamming_distance
            }
            url = f'{self.config.index_api}/image'
            log.debug('Image Index API request: %s with params %s', url, params)
            r = requests.get(url, params=params, headers={'x-source': source})
        except ConnectionError:
            log.error('Failed to connect to Index API')
            raise NoIndexException('Failed to connect to Index API')
        except Exception as e:
            log.exception('Problem with image index api', exc_info=True)
            raise

        if r.status_code == 503:
            log.warning('Index API returned 503 (indexes loading)')
            raise NoIndexException('Index API unavailable (503)')

        if r.status_code != 200:
            log.error('Unexpected status from index API: %s | %s', r.status_code, r.text)
            raise NoIndexException(f'Unexpected status {r.status_code}')

        res_data = json.loads(r.text)

        try:
            api_results = APISearchResults(**res_data)
            # Debug: top 3 match distances across all indexes
            all_matches = [m for idx_result in api_results.results for m in idx_result.matches]
            top_3 = sorted(all_matches, key=lambda x: x.distance)[:3]
            log.debug('Top 3 match distances: %s', [m.distance for m in top_3])
            return api_results
        except TypeError as e:
            raise NoIndexException(f'Failed to convert API result: {str(e)}')

    def _prefilter_api_results(
            self,
            api_results: APISearchResults,
            target_hamming_distance: float,
            keep_top_n: int = 10
    ) -> tuple[APISearchResults, int]:
        """
        Pre-filter API results by hamming distance before DB lookup.
        Keeps matches within threshold AND top N closest for closest_match accuracy.

        :param api_results: Raw API search results
        :param target_hamming_distance: Target distance threshold (bits)
        :param keep_top_n: Number of closest matches to keep regardless of threshold
        :return: Tuple of (filtered results, original match count)
        """
        original_count = sum(len(r.matches) for r in api_results.results)

        for index_result in api_results.results:
            if not index_result.matches:
                continue

            # Sort by distance (closest first)
            sorted_matches = sorted(index_result.matches, key=lambda m: m.distance)

            # Keep all within threshold
            within_threshold = [m for m in sorted_matches if m.distance <= target_hamming_distance]

            # Keep top N closest regardless of threshold
            top_n = sorted_matches[:keep_top_n]

            # Merge without duplicates (dict by id)
            merged = {m.id: m for m in within_threshold}
            for m in top_n:
                if m.id not in merged:
                    merged[m.id] = m

            index_result.matches = list(merged.values())

        filtered_count = sum(len(r.matches) for r in api_results.results)
        log.debug('Pre-filter: %s -> %s matches (kept top %s + threshold %.1f)',
                  original_count, filtered_count, keep_top_n, target_hamming_distance)

        return api_results, original_count

    def _build_search_results(
            self,
            api_search_results: APISearchResults,
            url: Text,
            searched_hash: Text,
    ) -> List[ImageSearchMatch]:
        """
        Take a list of index matches and convert them to ImageSearchMatches
        :param api_search_results: Results from the FAISS index API search
        :param url: URL of the image we searched
        :param searched_hash: The hash that was searched (unused, kept for API compatibility)
        :return: List of ImageSearchMatch objects
        """
        results = []
        log.debug('Building search results from index matches')
        with self.uowm.start() as uow:
            for r in api_search_results.results:
                log.debug(f'Found {len(r.matches)} in {r.index_name}')

                # Create mapping from index ID to distance from API results
                distance_map = {m.id: m.distance for m in r.matches}

                index_matches = uow.image_index_map.get_all_in_by_ids_and_index(
                    [m.id for m in r.matches], r.index_name
                )

                for im in index_matches:
                    results.append(
                        ImageSearchMatch(
                            url,
                            im.post_id,
                            im.post,
                            int(distance_map[im.annoy_index_id]),  # Use annoy_index_id for lookup
                            256  # Standard hash size in bits
                        )
                    )

        log.debug('%s results built', len(results))
        return results

    def _log_search_time(self, search_results: ImageSearchResults, source: Text):
        self.event_logger.save_event(
            ImageSearchEvent(
                search_results.search_times,
                event_type='duplicate_image_search',
                source=source
            )
        )


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


    def _get_meme_template(self, image_hash: Text, source: str = 'unknown') -> Optional[MemeTemplate]:
        try:
            r = requests.get(f'{self.config.index_api}/meme', params={'hash': image_hash}, headers={'x-source': source})
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

    def _get_cached_meme_hashes(self,post_ids: list[str]) -> dict[str, str]:
        results = {}
        with self.uowm.start() as uow:
            res = uow.meme_hash.get_by_post_ids(post_ids)
            for meme_hash in res:
                results[meme_hash.post_id] = meme_hash.hash
            return results

    def _final_meme_filter(self,
                           searched_hash: Text,
                           matches: List[ImageSearchMatch],
                           target_hamming
                           ) -> List[ImageSearchMatch]:
        results = []
        log.debug('MEME FILTER - Filtering %s matches', len(matches))
        if len(matches) == 0:
            return matches
        cached_meme_hashes = self._get_cached_meme_hashes([m.post.post_id for m in matches])

        for match in matches:
            match_hash = cached_meme_hashes.get(match.post.post_id)
            if not match_hash:
                try:
                    meme_hashes = get_image_hashes(match.post.url, hash_size=self.config.default_meme_filter_hash_size)
                    match_hash = meme_hashes['dhash_h']
                except ImageConversionException:
                    log.warning('Failed to get meme hash for %s.  Sending to delete queue', match.post.post_id)
                    #delete_post_task.apply_async((match.post.post_id,))
                    continue
                except Exception:
                    log.exception('Failed to get meme hash for %s', match.post.url, exc_info=True)
                    continue
            if not match_hash:
                continue
            h_distance = hamming_distance_bits(searched_hash, match_hash)

            if h_distance > target_hamming:
                log.info('Meme Hamming Filter Reject - Target: %s Actual: %s - %s', target_hamming,
                         h_distance, f'https://redd.it/{match.post.post_id}')
                continue
            log.debug('Match found: %s - H:%s', f'https://redd.it/{match.post.post_id}',
                      h_distance)
            match.hamming_distance = h_distance
            match.hash_size = len(searched_hash) * 4  # Bit count
            results.append(match)

        return results

