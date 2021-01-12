from datetime import datetime
import random
import random
from datetime import datetime
from time import perf_counter
from typing import List, Text

import Levenshtein
import requests
from praw import Reddit

from redditrepostsleuth.core.db.databasemodels import Post
from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.core.logging import log
from redditrepostsleuth.core.model.repostmatch import RepostMatch
from redditrepostsleuth.core.model.repostwrapper import RepostWrapper
from redditrepostsleuth.core.model.search.image_search_match import ImageSearchMatch
from redditrepostsleuth.core.model.search.search_match import SearchMatch
from redditrepostsleuth.core.model.search.search_results import SearchResults
from redditrepostsleuth.core.util.constants import USER_AGENTS
from redditrepostsleuth.core.util.objectmapping import post_to_link_post_search_match
from redditrepostsleuth.core.util.repost_filters import filter_same_post, filter_same_author, cross_post_filter, \
    filter_newer_matches, same_sub_filter, filter_title_distance, filter_days_old_matches, filter_dead_urls_remote, \
    filter_removed_posts


def filter_matching_images(raw_list: List[RepostMatch], post_being_checked: Post) -> List[Post]:
    """
    Take a raw list if matched images.  Filter one ones meeting the following criteria.
        Same Author as post being checked - Gets rid of people posting to multiple subreddits
        If it has a crosspost parent - A cross post isn't considered a respost
        Same post ID as post being checked - The image list will contain the original image being checked
    :param raw_list: List of all matches
    :param post_being_checked: The posts we're checking is a repost
    """
    # TODO - Clean this up
    return [x for x in raw_list if x.post.crosspost_parent is None and post_being_checked.author != x.author]


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


def get_closest_image_match(posts: List[ImageSearchMatch], reverse=True, check_url=True) -> ImageSearchMatch:
    if not posts:
        return None
    if not check_url:
        return sorted(posts, key=lambda x: x.hamming_match_percent, reverse=reverse)[0]
    sorted_matches = sorted(posts, key=lambda x: x.hamming_match_percent, reverse=reverse)
    return get_first_active_match(sorted_matches)

def check_link_repost(
        post: Post,
        uowm: UnitOfWorkManager,
        get_total: bool = False,
        target_title_match: int = None,
        same_sub: bool = False,
        date_cutoff: int = None,
        filter_dead_matches: bool = True,
        only_older_matches: bool = True
        ) -> SearchResults:
    with uowm.start() as uow:
        start = perf_counter()
        search_results = SearchResults()
        search_results.checked_post = post
        raw_results = uow.posts.find_all_by_url_hash(post.url_hash)
        search_results.total_search_time = round(perf_counter() - start, 3)
        log.debug('Query time: %s', search_results.total_search_time)
        search_results.matches = [post_to_link_post_search_match(match, post.id) for match in raw_results]
        search_results.matches = filter_repost_results(
            search_results.matches,
            post,
            target_title_match=target_title_match,
            same_sub=same_sub,
            date_cutoff=date_cutoff,
            filter_dead_matches=filter_dead_matches,
            only_older_matches=only_older_matches
        )
        if get_total:
            search_results.total_searched = uow.posts.count_by_type('link')
        #search.total_search_time = perf_counter() - start

    return search_results


def check_link_repost_by_post_id(post_id: str, uowm: UnitOfWorkManager) -> RepostWrapper:
    with uowm.start() as uow:
        post = uow.posts.get_by_post_id(post_id)
        if post is None:
            return
    return check_link_repost(post, uowm)


def filter_search_results(
        search_results: SearchResults,
        reddit: Reddit = None,
        uitl_api: Text = None
) -> SearchResults:
    """
    Filter a set of search results based on the image search settings
    :param reddit: Used for filter removed post
    :param uitl_api: Used for filtering removed posts
    :param search_results: SearchResults obj
    """
    log.debug('%s results pre-filter', len(search_results.matches))
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

    if reddit and uitl_api:
        if search_results.search_settings.filter_dead_matches:
            search_results.matches = filter_dead_urls_remote(
                uitl_api,
                search_results.matches
            )

    if search_results.search_settings.filter_removed_matches and reddit:
        search_results.matches = filter_removed_posts(reddit, search_results.matches)

    log.debug('%s results post-filter', len(search_results.matches))
    return search_results

def filter_repost_results(
        matches: List[RepostMatch],
        checked_post: Post,
        target_title_match: int = None,
        same_sub: bool = False,
        date_cutoff: int = None,
        filter_dead_matches: bool = True,
        only_older_matches: bool = True,
        exclude_crossposts: bool = True

) -> List[RepostMatch]:
    results = []
    if target_title_match:
        matches = set_all_title_similarity(checked_post.title, matches)

    for match in matches:

        if match.post.post_id == checked_post.post_id:
            continue

        if match.post.author == checked_post.author:
            log.debug('Author Cutoff Reject')
            continue

        if same_sub and match.post.subreddit != checked_post.subreddit:
            log.debug('Same Sub Reject: Orig sub: %s - Match Sub: %s - %s', checked_post.subreddit, match.post.subreddit, f'https://redd.it/{match.post.post_id}')
            continue

        if only_older_matches and match.post.created_at > checked_post.created_at:
            log.debug('Date Filter Reject: Target: %s Actual: %s - %s', checked_post.created_at.strftime('%Y-%d-%m'),
                      match.post.created_at.strftime('%Y-%d-%m'), f'https://redd.it/{match.post.post_id}')
            continue

        if date_cutoff and (datetime.utcnow() - match.post.created_at).days > date_cutoff:
            log.debug('Date Cutoff Reject: Target: %s Actual: %s - %s', date_cutoff,
                      (datetime.utcnow() - match.post.created_at).days, f'https://redd.it/{match.post.post_id}')
            continue

        if exclude_crossposts and match.post.crosspost_parent is not None:
            log.debug('Crosspost Reject: %s', f'https://redd.it/{match.post.post_id}')
            continue

        if target_title_match and match.title_similarity <= target_title_match:
            log.debug('Title Similarity Filter Reject: Target: %s Actual: %s', target_title_match, match.title_similarity)
            continue

        results.append(match)

    return results


def get_first_active_match(matches: List[SearchMatch]) -> SearchMatch:
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

