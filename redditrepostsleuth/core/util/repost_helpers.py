import logging
import logging
import random
from hashlib import md5
from typing import List, Text, Optional

import Levenshtein
import requests
from praw import Reddit

from redditrepostsleuth.core.db.databasemodels import Post, RepostSearch
from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.core.model.link_search_times import LinkSearchTimes
from redditrepostsleuth.core.model.repostmatch import RepostMatch
from redditrepostsleuth.core.model.search.image_search_match import ImageSearchMatch
from redditrepostsleuth.core.model.search.link_search_results import LinkSearchResults
from redditrepostsleuth.core.model.search.search_match import SearchMatch
from redditrepostsleuth.core.model.search.search_results import SearchResults
from redditrepostsleuth.core.model.search_settings import SearchSettings
from redditrepostsleuth.core.util.constants import USER_AGENTS
from redditrepostsleuth.core.util.helpers import set_repost_search_params_from_search_settings
from redditrepostsleuth.core.util.repost_filters import filter_same_post, filter_same_author, cross_post_filter, \
    filter_newer_matches, same_sub_filter, filter_title_distance, filter_days_old_matches, filter_removed_posts, \
    filter_removed_posts_util_api

log = logging.getLogger(__name__)


def sort_reposts(posts: List[RepostMatch], reverse=False, sort_by='created') -> List[RepostMatch]:
    """
    Take a list of reposts and sort them by date
    :param posts:
    """
    if sort_by == 'created':
        return sorted(posts, key=lambda x: x.post.created_at, reverse=reverse)
    elif sort_by == 'percent':
        return sorted(posts, key=lambda x: x.hamming_match_percent, reverse=True)
    else:
        return sorted(posts, key=lambda x: x.post.created_at, reverse=reverse)


def get_closest_image_match(
        posts: list[ImageSearchMatch],
        reverse: bool =True,
        validate_url: bool =True
) -> Optional[ImageSearchMatch]:
    if not posts:
        return
    sorted_matches = sorted(posts, key=lambda x: x.hamming_match_percent, reverse=reverse)
    if not validate_url:
        return sorted_matches[0]
    return get_first_active_match(sorted_matches)


def log_search(uowm: UnitOfWorkManager, search_results: SearchResults, source: str, post_type_name: str) -> Optional[RepostSearch]:
    try:
        with uowm.start() as uow:
            post_type = uow.post_type.get_by_name(post_type_name)
            if not post_type:
                log.warning('Failed to find post_type %s for search from source %s', post_type, source)
            logged_search = RepostSearch(
                post_id=search_results.checked_post.id if search_results.checked_post else None,
                subreddit=search_results.checked_post.subreddit if search_results.checked_post else None,
                source=source,
                matches_found=len(search_results.matches),
                search_time=search_results.search_times.total_search_time,
                post_type=post_type
            )
            set_repost_search_params_from_search_settings(search_results.search_settings, logged_search)
            uow.repost_search.add(logged_search)
            uow.commit()
            search_results.logged_search = logged_search
    except Exception as e:
        log.exception('Failed to save repost search')

def get_link_reposts(
        url: str,
        uowm: UnitOfWorkManager,
        search_settings: SearchSettings,
        post: Post = None,
        get_total: bool = False,
        ) -> LinkSearchResults:

    url_hash = md5(url.encode('utf-8'))
    url_hash = url_hash.hexdigest()
    with uowm.start() as uow:
        search_results = LinkSearchResults(url, search_settings, checked_post=post, search_times=LinkSearchTimes())
        search_results.search_times.start_timer('query_time')
        search_results.search_times.start_timer('total_search_time')
        raw_results: list[Post] = uow.posts.find_all_by_url(url_hash)
        search_results.search_times.stop_timer('query_time')
        log.debug('Query time: %s', search_results.search_times.query_time)
        search_results.matches = [SearchMatch(url, post) for post in raw_results]

        if get_total:
            search_results.total_searched = uow.posts.count_by_type(3)

    return search_results


# TODO - 1/12/2021 - Possibly make the generic. It's messing with auto complete when used for image searches
def filter_search_results(
        search_results: SearchResults,
        reddit: Reddit = None,
        uitl_api: Text = None,
) -> SearchResults:
    """
    Filter a set of search results based on the image search settings
    :param reddit: Used for filter removed post
    :param uitl_api: Used for filtering removed posts
    :param search_results: SearchResults obj
    """
    log.debug('%s results pre-filter', len(search_results.matches))
    search_results.search_times.start_timer('total_filter_time')
    # Only run these if we are search for an existing post
    if search_results.checked_post:
        search_results.matches = list(filter(filter_same_post(search_results.checked_post.post_id), search_results.matches))

        if search_results.search_settings.filter_same_author:
            search_results.matches = list(filter(filter_same_author(search_results.checked_post.author), search_results.matches))

        if search_results.search_settings.filter_crossposts:
            search_results.matches = list(filter(cross_post_filter, search_results.matches))

        if search_results.search_settings.only_older_matches:
            search_results.matches = list(filter(filter_newer_matches(search_results.checked_post.created_at), search_results.matches))

        if search_results.search_settings.same_sub:
            search_results.matches = list(filter(same_sub_filter(search_results.checked_post.subreddit), search_results.matches))

        if search_results.search_settings.target_title_match:
            search_results.matches = list(filter(filter_title_distance(search_results.search_settings.target_title_match), search_results.matches))

        if search_results.search_settings.max_days_old:
            search_results.matches = list(filter(filter_days_old_matches(search_results.search_settings.max_days_old), search_results.matches))

        if search_results.search_settings.filter_dead_matches and uitl_api:
            search_results.search_times.start_timer('filter_deleted_posts_time')
            search_results.matches = filter_removed_posts_util_api(
                uitl_api,
                search_results.matches
            )
            search_results.search_times.stop_timer('filter_deleted_posts_time')
            print(f'Filter dead time: {search_results.search_times.filter_deleted_posts_time}')

    if search_results.search_settings.filter_removed_matches and reddit:
        search_results.search_times.start_timer('filter_removed_posts_time')
        search_results.matches = filter_removed_posts(reddit, search_results.matches)
        search_results.search_times.stop_timer('filter_removed_posts_time')

    search_results.search_times.stop_timer('total_filter_time')
    log.debug('%s results post-filter', len(search_results.matches))
    return search_results


def get_first_active_match(matches: List[ImageSearchMatch]) -> ImageSearchMatch:
    for match in matches:
        try:
            headers = {'User-Agent': random.choice(USER_AGENTS)}
            r = requests.head(match.post.url, timeout=3, headers=headers)
            if r.status_code == 200:
                return match
        except Exception as e:
            continue


def get_title_similarity(title1: Text, title2: Text) -> float:
    result = Levenshtein.ratio(title1, title2)
    log.debug('Difference between %s and %s: %s', title1, title2, result)
    return round(result * 100, 0)

def set_all_title_similarity(title: Text, matches: List[SearchMatch]) -> List[SearchMatch]:
    """
    Take a list of repost matches and set the title similarity vs the provided title
    :param title: Title to measure each match against
    :param matches: List of matches to check
    :return: List of RepostMatches
    """
    for match in matches:
        match.title_similarity = get_title_similarity(title, match.post.title)
    return matches

