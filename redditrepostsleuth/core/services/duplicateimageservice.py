import json
from typing import List, Text, Optional

import requests
from distance import hamming
from praw import Reddit
from requests.exceptions import ConnectionError

from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.db.databasemodels import Post, ImageSearch, MemeTemplate
from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.core.exception import NoIndexException
from redditrepostsleuth.core.logging import log
from redditrepostsleuth.core.model.events.annoysearchevent import AnnoySearchEvent
from redditrepostsleuth.core.model.image_index_api_result import ImageIndexApiResult
from redditrepostsleuth.core.model.search.image_search_results import ImageSearchResults
from redditrepostsleuth.core.model.image_search_settings import ImageSearchSettings
from redditrepostsleuth.core.model.image_search_times import ImageSearchTimes
from redditrepostsleuth.core.model.search.image_search_match import ImageSearchMatch
from redditrepostsleuth.core.services.eventlogging import EventLogging
from redditrepostsleuth.core.util.helpers import create_search_result_json, get_default_image_search_settings
from redditrepostsleuth.core.util.imagehashing import get_image_hashes
from redditrepostsleuth.core.util.repost_filters import filter_same_post, filter_same_author, cross_post_filter, \
    filter_newer_matches, same_sub_filter, filter_days_old_matches, annoy_distance_filter, hamming_distance_filter, \
    filter_no_dhash, filter_title_distance, filter_removed_posts, filter_dead_urls_remote
from redditrepostsleuth.core.util.repost_helpers import sort_reposts, get_closest_image_match, set_all_title_similarity


class DuplicateImageService:
    def __init__(self, uowm: UnitOfWorkManager, event_logger: EventLogging, reddit: Reddit, config: Config = None):
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
        matches = search_results.matches

        matches = list(filter(filter_no_dhash, matches))

        # Only run these if we are search for an existing post
        if search_results.checked_post:
            matches = list(filter(filter_same_post(search_results.checked_post.post_id), matches))

            if search_results.search_settings.filter_same_author:
                matches = list(filter(filter_same_author(search_results.checked_post.author), matches))

            if search_results.search_settings.filter_crossposts:
                matches = list(filter(cross_post_filter, matches))

            if search_results.search_settings.only_older_matches:
                matches = list(filter(filter_newer_matches(search_results.checked_post.created_at), matches))

            if search_results.search_settings.same_sub:
                matches = list(filter(same_sub_filter(search_results.checked_post.subreddit), matches))

            if search_results.search_settings.target_title_match:
                matches = list(filter(filter_title_distance(search_results.search_settings.target_title_match), matches))

            if search_results.search_settings.max_days_old:
                matches = list(filter(filter_days_old_matches(search_results.search_settings.max_days_old), matches))

        closest_match = get_closest_image_match(matches, check_url=True)
        if closest_match and closest_match.hamming_match_percent > 40: # TODO - Move to config
            search_results.closest_match = closest_match

        # Has to be after closest match so we don't drop closest
        matches = list(filter(annoy_distance_filter(search_results.search_settings.target_annoy_distance), matches))
        matches = list(filter(hamming_distance_filter(search_results.target_hamming_distance), matches))

        if search_results.search_settings.filter_dead_matches:
            matches = filter_dead_urls_remote(
                f'{self.config.util_api}/maintenance/removed',
                self.reddit,
                matches
            )

        if search_results.search_settings.filter_removed_matches:
            matches = filter_removed_posts(self.reddit, matches)

        if search_results.meme_template:
            search_results.search_times.start_timer('meme_filter_time')
            matches = self._final_meme_filter(search_results.meme_hash, matches,
                                              search_results.target_meme_hamming_distance)
            search_results.search_times.stop_timer('meme_filter_time')

        search_results.matches = sort_reposts(matches, sort_by=sort_by)

        for match in matches:
            log.debug('Match found: %s - A:%s H:%s P:%s', f'https://redd.it/{match.post.post_id}',
                      round(match.annoy_distance, 5), match.hamming_distance, f'{match.hamming_match_percent}%')

        return search_results

    def check_image(
            self,
            url: Text,
            post: Post = None,
            source='unknown',
            sort_by='created',
            search_settings: ImageSearchSettings = None

    ) -> ImageSearchResults:
        log.info('Checking URL for matches: %s', url)

        if not search_settings:
            log.info('No search settings provided, using default')
            search_settings = get_default_image_search_settings(self.config)

        search_results = ImageSearchResults(
            url,
            checked_post=post,
            search_settings=search_settings
        )
        search_results.search_times = ImageSearchTimes()
        search_results.search_times.start_timer('total_search_time')

        if search_settings.meme_filter:
            search_results.search_times.start_timer('meme_detection_time')
            search_results.meme_template = self._get_meme_template(search_results.target_hash)
            search_results.search_times.stop_timer('meme_detection_time')
            if search_results.meme_template:
                search_settings.target_match_percent = 100  # Keep only 100% matches on default hash size
                search_results.meme_hash = self._get_meme_hash(url)
                if not search_results.meme_hash:
                    log.error('No meme hash, disabled meme filter')
                    search_results.meme_template = None
                else:
                    log.info('Using meme filter %s', search_results.meme_template.id)

        log.debug('Search Settings: %s', search_settings)

        api_search_results = self._get_matches(
            search_results.target_hash,
            search_results.target_hamming_distance,
            search_settings.target_annoy_distance,
            max_matches=search_settings.max_matches,
            max_depth=search_settings.max_depth,
            search_times=search_results.search_times
        )

        search_results.search_times.index_search_time = api_search_results.index_search_time
        search_results.total_searched = api_search_results.total_searched

        search_results.search_times.start_timer('set_match_post_time')
        search_results.matches = self._build_search_results(api_search_results.historical_matches, url,
                                                            search_results.target_hash)
        search_results.matches += self._build_search_results(api_search_results.current_matches, url,
                                                             search_results.target_hash, historical_index=False)
        search_results.search_times.stop_timer('set_match_post_time')

        search_results.search_times.start_timer('remove_duplicate_time')
        search_results.matches = self._remove_duplicates(search_results.matches)
        if post:
            search_results.matches = set_all_title_similarity(search_results.checked_post.title, search_results.matches)
        search_results.search_times.stop_timer('remove_duplicate_time')

        search_results.search_times.start_timer('total_filter_time')
        search_results = self._filter_results_for_reposts(
            search_results,
            sort_by=sort_by
        )
        search_results.search_times.stop_timer('total_filter_time')
        search_results.search_times.stop_timer('total_search_time')
        self._log_search_time(search_results, source)

        search_results.logged_search = self._log_search(
            search_results,
            source,
            api_search_results.used_current_index,
            api_search_results.used_historical_index,
        )
        if search_results.logged_search:
            search_results.search_id = search_results.logged_search.id
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
            search_times: ImageSearchTimes = None
    ) -> ImageIndexApiResult:
        """
        Take a given hash and search the image index API for matches
        :param hash: Hash of image to search
        :param target_hamming_distance: Target hamming distance
        :param target_annoy_distance: Target annoy distance
        :param max_matches: Max results to fetch from index API
        :param max_depth: Max depth to search index
        :param search_times: Optional time tracking
        :rtype: ImageIndexApiResult
        """
        try:
            if search_times:
                search_times.start_timer('image_search_api_time')
            params = {
                'hash': hash,
                'max_results': max_matches,
                'max_depth': max_depth,
                'a_filter': target_annoy_distance,
                'h_filter': target_hamming_distance
            }
            r = requests.get(f'{self.config.index_api}/image', params=params)
            if search_times:
                search_times.stop_timer('image_search_api_time')
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
            return ImageIndexApiResult(**res_data)
        except TypeError as e:
            raise NoIndexException(f'Failed to convert API result: {str(e)}')

    def _build_search_results(
            self,
            index_matches: List[dict],
            url: Text,
            searched_hash: Text,
            historical_index: bool = True
    ) -> List[ImageSearchMatch]:
        """
        Take a list of index matches and convert them to ImageSearchMatches
        :param index_matches: Dict of raw matches from index search
        :param url: URL of the image we searched
        :param historical_index: If results are from the historical index
        :return:
        """
        results = []
        log.debug('Building search results from %s index matches', len(index_matches))
        for m in index_matches:
            image_match = self._get_image_search_match_from_index_result(m, url, searched_hash,
                                                                         historical_index=historical_index)
            if image_match:
                results.append(image_match)
        log.debug('%s results built', len(results))
        return results

    def _get_image_search_match_from_index_result(
            self,
            result: dict,
            url: Text,
            searched_hash: Text,
            historical_index: bool = True
    ) -> Optional[ImageSearchMatch]:

        post = self._get_post_from_index_id(result['id'], historical_index=historical_index)

        if not post:
            return

        if not post.dhash_h:
            log.error('Post %s missing dhash', post.post_id)
            return

        return ImageSearchMatch(
            url,
            result['id'],
            post,
            hamming(searched_hash, post.dhash_h),
            result['distance'],
            len(post.dhash_h)
        )

    def _log_search_time(self, search_results: ImageSearchResults, source: Text):
        self.event_logger.save_event(
            AnnoySearchEvent(
                total_search_time=search_results.search_times.total_search_time,
                index_search_time=search_results.search_times.index_search_time,
                index_size=search_results.total_searched,
                event_type='duplicate_image_search',
                meme_detection_time=search_results.search_times.meme_detection_time,
                meme_filter_time=search_results.search_times.meme_filter_time,
                total_filter_time=search_results.search_times.total_filter_time,
                match_post_time=search_results.search_times.set_match_post_time,
                source=source
            )
        )

    def _log_search(
            self,
            search_results: ImageSearchResults,
            source: str,
            used_current_index: bool,
            used_historical_index: bool,
    ) -> Optional[ImageSearchResults]:
        image_search = ImageSearch(
            post_id=search_results.checked_post.post_id if search_results.checked_post else 'url',
            used_historical_index=used_historical_index,
            used_current_index=used_current_index,
            target_hamming_distance=search_results.target_hamming_distance,
            target_annoy_distance=search_results.search_settings.target_annoy_distance,
            same_sub=search_results.search_settings.same_sub,
            max_days_old=search_results.search_settings.max_days_old,
            filter_dead_matches=search_results.search_settings.filter_dead_matches,
            only_older_matches=search_results.search_settings.only_older_matches,
            meme_filter=search_results.search_settings.meme_filter,
            meme_template_used=search_results.meme_template.id if search_results.meme_template else None,
            search_time=search_results.search_times.total_search_time,
            index_search_time=search_results.search_times.index_search_time,
            total_filter_time=search_results.search_times.total_filter_time,
            target_title_match=search_results.search_settings.target_title_match,
            matches_found=len(search_results.matches),
            source=source,
            subreddit=search_results.checked_post.subreddit if search_results.checked_post else 'url',
            search_results=create_search_result_json(search_results),
            target_image_meme_match=search_results.search_settings.target_meme_match_percent,
            target_image_match=search_results.search_settings.target_match_percent
        )

        with self.uowm.start() as uow:
            uow.image_search.add(image_search)
            try:
                uow.commit()
                return image_search
            except Exception as e:
                log.exception('Failed to save image search', exc_info=False)

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

    def _get_post_from_index_id(self, index_id: int, historical_index: bool = True) -> Optional[Post]:
        with self.uowm.start() as uow:
            # Hit the correct table if historical or current
            if historical_index:
                original_image_post = uow.image_post.get_by_id(index_id)
            else:
                original_image_post = uow.image_post_current.get_by_id(index_id)

            if not original_image_post:
                log.error('Failed to lookup original match post. ID %s - Historical: %s', index_id, historical_index)
                return

            post = uow.posts.get_by_post_id(original_image_post.post_id)
            if not post:
                log.error('Failed to find original reddit_post for match')
                return
            return post

    def _set_match_post(self, match: ImageSearchMatch, historical: bool = True) -> Optional[ImageSearchMatch]:
        """
        Take a search match, lookup the Post object and attach to match
        :param match: Match object
        :param historical: Is the match from the historical index
        """
        with self.uowm.start() as uow:
            # Hit the correct table if historical or current
            if historical:
                original_image_post = uow.image_post.get_by_id(match.index_match_id)
            else:
                original_image_post = uow.image_post_current.get_by_id(match.index_match_id)

            if not original_image_post:
                log.error('Failed to lookup original match post. ID %s - Historical: %s', match.index_match_id,
                          historical)
                return

            match_post = uow.posts.get_by_post_id(original_image_post.post_id)
            if not match_post:
                log.error('Failed to find original reddit_post for match')
                return
            match.post = match_post
            return match

    def _get_meme_template(self, image_hash: Text) -> Optional[MemeTemplate]:
        try:
            r = requests.get(f'{self.config.index_api}/meme', params={'hash': image_hash})
        except Exception as e:
            log.exception('Failed to get meme template from api', exc_info=True)
            return

        if r.status_code != 200:
            log.error('Unexpected Index API status %s', r.status_code)
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
            try:
                match_hashes = get_image_hashes(match.post.url, hash_size=self.config.default_meme_filter_hash_size)
            except Exception as e:
                log.error('Failed to get meme hash for %s', match.post.id)
                continue

            h_distance = hamming(searched_hash, match_hashes['dhash_h'])

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

