import json
from time import perf_counter
from typing import List, Text, Optional

import Levenshtein
import requests
from praw import Reddit
from requests.exceptions import ConnectionError
from distance import hamming
from sqlalchemy import Float

from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.db.databasemodels import Post, ImageSearch, MemeTemplate
from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.core.exception import NoIndexException
from redditrepostsleuth.core.logging import log
from redditrepostsleuth.core.model.events.annoysearchevent import AnnoySearchEvent
from redditrepostsleuth.core.model.image_search_times import ImageSearchTimes
from redditrepostsleuth.core.model.imagematch import ImageMatch
from redditrepostsleuth.core.model.imagerepostwrapper import ImageRepostWrapper
from redditrepostsleuth.core.services.eventlogging import EventLogging
from redditrepostsleuth.core.util.helpers import create_search_result_json, get_hamming_from_percent
from redditrepostsleuth.core.util.imagehashing import get_image_hashes
from redditrepostsleuth.core.util.objectmapping import annoy_result_to_image_match
from redditrepostsleuth.core.util.repost_filters import filter_same_post, filter_same_author, cross_post_filter, \
    filter_newer_matches, same_sub_filter, filter_days_old_matches, annoy_distance_filter, hamming_distance_filter, \
    filter_no_dhash, filter_dead_urls, filter_title_distance, filter_removed_posts, filter_dead_urls_remote
from redditrepostsleuth.core.util.reposthelpers import sort_reposts, get_closest_image_match, set_all_title_similarity


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
            search_results: ImageRepostWrapper,
            target_annoy_distance: float = None,
            target_match_percent: int = None,
            target_meme_match_percent: int = None,
            target_title_match: int = None,
            same_sub: bool = False,
            date_cutoff: int = None,
            filter_dead_matches: bool = True,
            filter_removed_matches: bool = True,
            only_older_matches: bool = True,
            filter_crossposts=True,
            filter_author=True,
            sort_by='created'
    ) -> ImageRepostWrapper:
        """
        Take a list of matches and filter out posts that are not reposts.
        This is done via distance checking, creation date, crosspost
        :param checked_post: The post we're finding matches for
        :param search_results: A cleaned list of matches
        :param target_hamming_distance: Hamming cutoff for matches
        :param target_annoy_distance: Annoy cutoff for matches
        :rtype: List[ImageMatch]
        """
        start_time = perf_counter()
        # TODO - Allow array of filters to be passed

        if search_results.meme_template:
            target_hamming_distance = get_hamming_from_percent(
                target_meme_match_percent or self.config.target_image_meme_match, 256)
            search_results.target_match_percent = target_meme_match_percent or self.config.target_image_meme_match
        else:
            target_hamming_distance = get_hamming_from_percent(target_match_percent or self.config.target_image_match,
                                                               len(search_results.checked_post.dhash_h))
            search_results.target_match_percent = target_match_percent or self.config.target_image_match

        target_annoy_distance = target_annoy_distance or self.config.default_annoy_distance
        search_results.target_hamming_distance = target_hamming_distance
        search_results.target_annoy_distance = target_annoy_distance

        log.info('Target Annoy Dist: %s - Target Hamming Dist: %s', target_annoy_distance, target_hamming_distance)
        log.info('Meme Filter: %s - Only Older: %s - Day Cutoff: %s - Same Sub: %s', search_results.meme_template is None, only_older_matches, date_cutoff, same_sub)
        log.debug('Matches pre-filter: %s', len(search_results.matches))
        matches = search_results.matches
        matches = list(filter(filter_same_post(search_results.checked_post.post_id), matches))
        if filter_author:
            matches = list(filter(filter_same_author(search_results.checked_post.author), matches))
        if filter_crossposts:
            matches = list(filter(cross_post_filter, matches))
        matches = list(filter(filter_no_dhash, matches))

        if only_older_matches:
            matches = list(filter(filter_newer_matches(search_results.checked_post.created_at), matches))

        if same_sub:
            matches = list(filter(same_sub_filter(search_results.checked_post.subreddit), matches))

        if date_cutoff:
            matches = list(filter(filter_days_old_matches(date_cutoff), matches))

        if target_title_match:
            matches = set_all_title_similarity(search_results.checked_post.title, matches)
            matches = list(filter(filter_title_distance(target_title_match), matches))

        closest_match = get_closest_image_match(matches, check_url=True)
        if closest_match and closest_match.hamming_match_percent > 40:
            search_results.closest_match = closest_match


        matches = list(filter(annoy_distance_filter(target_annoy_distance), matches))
        # TODO - Don't like setting a hard zero hamming distance when meme is detected
        matches = list(filter(hamming_distance_filter(target_hamming_distance if not search_results.meme_template else 0), matches))

        if filter_dead_matches:
            matches = filter_dead_urls_remote(
                f'{self.config.util_api}/maintenance/removed',
                self.reddit,
                matches
            )
            matches = filter_removed_posts(self.reddit, matches)

        for match in matches:
            log.debug('Match found: %s - A:%s H:%s', f'https://redd.it/{match.post.post_id}',
                      round(match.annoy_distance, 5), match.hamming_distance)

        log.info('Matches post-filter: %s', len(matches))
        if search_results.meme_template:
            search_results.search_times.start_timer('meme_filter_time')
            matches = self._final_meme_filter(search_results.checked_post, matches, target_hamming_distance)
            search_results.search_times.stop_timer('meme_filter_time')
            search_results.target_match_percent = round(100 - (target_hamming_distance / 256) * 100, 2)

        search_results.matches = sort_reposts(matches, sort_by=sort_by)
        return search_results

    def check_duplicates_wrapped(self, post: Post,
                                 result_filter: bool = True,
                                 max_matches: int = 50,  # TODO -
                                 target_match_percent: int = None,
                                 target_meme_match_percent: int = None,
                                 target_annoy_distance: float = None,
                                 target_title_match: int = None,
                                 same_sub: bool = False,
                                 date_cutoff: int = None,
                                 filter_dead_matches: bool = True,
                                 filter_removed_matches: bool = True,
                                 only_older_matches=True,
                                 meme_filter=False,
                                 max_depth=4000,
                                 filter_crossposts=True,
                                 filter_author=True,
                                 source='unknown',
                                 sort_by='created') -> ImageRepostWrapper:
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
        search_results = ImageRepostWrapper()
        search_times = ImageSearchTimes()
        search_results.search_times = search_times
        search_times.start_timer('total_search_time')
        search_results.checked_post = post

        if meme_filter and result_filter:
            search_times.start_timer('meme_detection_time')
            search_results.meme_template = self._get_meme_template(post.dhash_h)
            search_times.stop_timer('meme_detection_time')
            if search_results.meme_template:
                log.info('Using meme filter %s', search_results.meme_template.id)

        if search_results.meme_template:
            target_hamming_distance = 0
        else:
            target_hamming_distance = get_hamming_from_percent(target_match_percent or self.config.target_image_match,
                                                                len(search_results.checked_post.dhash_h))

        try:
            search_times.start_timer('image_search_api_time')
            params = {
                'hash': post.dhash_h,
                'max_results': max_matches,
                'max_depth': max_depth,
                'a_filter': target_annoy_distance or self.config.default_annoy_distance,
                'h_filter': target_hamming_distance
            }
            r = requests.get(f'{self.config.index_api}/image', params=params)
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

        api_results = json.loads(r.text)
        search_times.index_search_time = api_results['index_search_time']
        search_results.total_searched = api_results['total_searched']

        historical_results = self._convert_annoy_results(api_results['historical_matches'], post.id)
        current_results = self._convert_annoy_results(api_results['current_matches'], post.id)
        log.warn('After Pre Annoy Filter %s', len(historical_results) + len(current_results))

        search_times.start_timer('set_match_post_time')
        historical_results = self._set_match_posts(historical_results)
        current_results = self._set_match_posts(current_results, historical=False)
        results = historical_results + current_results
        search_times.stop_timer('set_match_post_time')

        search_times.start_timer('remove_duplicate_time')
        search_results.matches = self._remove_duplicates(results)
        search_times.stop_timer('remove_duplicate_time')

        if result_filter:
            search_times.start_timer('set_match_hamming')
            self._set_match_hamming(post, search_results.matches)
            search_times.stop_timer('set_match_hamming')

            search_times.start_timer('total_filter_time')
            search_results = self._filter_results_for_reposts(search_results,
                                                                      target_annoy_distance=target_annoy_distance,
                                                                      target_match_percent=target_match_percent,
                                                                      target_meme_match_percent=target_meme_match_percent,
                                                                      same_sub=same_sub,
                                                                      date_cutoff=date_cutoff,
                                                                      filter_dead_matches=filter_dead_matches,
                                                                      only_older_matches=only_older_matches,
                                                                      target_title_match=target_title_match,
                                                                      sort_by=sort_by,
                                                                      filter_crossposts=filter_crossposts,
                                                                      filter_author=filter_author
                                                                      )
            search_times.stop_timer('total_filter_time')
        else:
            search_results.matches = self._set_match_posts(search_results.matches)
            self._set_match_hamming(post, search_results.matches)
        search_times.stop_timer('total_search_time')
        search_results.total_search_time = search_results.search_times.total_search_time # TODO - Properly fix this.
        self._log_search_time(search_results, source)
        search_results.logged_search = self._log_search(
            search_results,
            same_sub,
            date_cutoff,
            filter_dead_matches,
            only_older_matches,
            meme_filter,
            source,
            target_title_match,
            api_results['used_current_index'],
            api_results['used_historical_index'],
            target_match_percent or self.config.target_image_match,
            target_meme_match_percent or self.config.target_image_meme_match
        )
        if search_results.logged_search:
            search_results.search_id = search_results.logged_search.id
        log.info('Seached %s items and found %s matches', search_results.total_searched, len(search_results.matches))
        return search_results

    def _convert_annoy_results(self, annoy_results, checked_post_id: int):
        return [annoy_result_to_image_match(match, checked_post_id) for match in annoy_results]

    def _annoy_filter(self, target_annoy_distance: Float):
        def annoy_distance_filter(match):
            return match['distance'] < target_annoy_distance
        return annoy_distance_filter

    def _log_search_time(self, search_results: ImageRepostWrapper, source: Text):
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
            search_results: ImageRepostWrapper,
            same_sub: bool,
            max_days_old: int,
            filter_dead_matches: bool,
            only_older_matches: bool,
            meme_filter: bool,
            source: str,
            target_title_match: int,
            used_current_index: bool,
            used_historical_index: bool,
            target_image_match: int,
            target_image_meme_match: int
    ) -> Optional[ImageRepostWrapper]:
        image_search = ImageSearch(
            post_id=search_results.checked_post.post_id,
            used_historical_index=used_historical_index,
            used_current_index=used_current_index,
            target_hamming_distance=search_results.target_hamming_distance,
            target_annoy_distance=search_results.target_annoy_distance,
            same_sub=same_sub if same_sub else False,
            max_days_old=max_days_old if max_days_old else False,
            filter_dead_matches=filter_dead_matches,
            only_older_matches=only_older_matches,
            meme_filter=meme_filter,
            meme_template_used=search_results.meme_template.id if search_results.meme_template else None,
            search_time=search_results.search_times.total_search_time,
            index_search_time=search_results.search_times.index_search_time,
            total_filter_time=search_results.search_times.total_filter_time,
            target_title_match=target_title_match,
            matches_found=len(search_results.matches),
            source=source,
            subreddit=search_results.checked_post.subreddit,
            search_results=create_search_result_json(search_results),
            target_image_meme_match=target_image_meme_match,
            target_image_match=target_image_match
        )

        with self.uowm.start() as uow:
            uow.image_search.add(image_search)
            try:
                uow.commit()
                return image_search
            except Exception as e:
                log.exception('Failed to save image search', exc_info=False)

    def _merge_search_results(self, first: List[ImageMatch], second: List[ImageMatch]) -> List[ImageMatch]:
        results = first.copy()
        for a in second:
            match = next((x for x in results if x.match_id == a.match_id), None)
            if match:
                continue
            results.append(a)

        return results

    def _remove_duplicates(self, matches: List[ImageMatch]) -> List[ImageMatch]:
        results = []
        for a in matches:
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
        log.info('Setting match posts for %s posts', len(matches))
        results = []
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
                if not match_post:
                    log.error('Failed to find original reddit_post for match')
                    continue
                match.post = match_post
                match.match_id = match_post.id
                results.append(match)
        return results

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
            match.hash_size = len(searched_post.dhash_h)
            match.hamming_match_percent = round(100 - (match.hamming_distance / len(searched_post.dhash_h)) * 100, 2)
        return matches

    def _final_meme_filter(
            self,
            searched_post: Post,
            matches: List[ImageMatch],
            target_hamming
    ) -> List[ImageMatch]:
        results = []
        log.debug('MEME FILTER - Filtering %s matches', len(matches))
        if len(matches) == 0:
            return matches

        try:
            target_hashes = get_image_hashes(searched_post, hash_size=32)
        except Exception as e:
            log.exception('Failed to convert target post for meme check', exc_info=True)
            return matches

        for match in matches:
            start = perf_counter()
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
            match.hamming_match_percent = round(100 - (h_distance / len(target_hashes['dhash_h'])) * 100, 2)
            match.hash_size = len(target_hashes['dhash_h'])
            results.append(match)

        return results

