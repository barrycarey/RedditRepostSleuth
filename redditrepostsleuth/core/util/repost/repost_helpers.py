import logging
import random
from typing import List, Text, Optional

import Levenshtein
import requests
from praw import Reddit
from sqlalchemy.exc import IntegrityError

from redditrepostsleuth.core.celery.task_logic.repost_image import log
from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.db.databasemodels import RepostSearch, Repost, MemeTemplate, Post
from redditrepostsleuth.core.db.uow.unitofwork import UnitOfWork
from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.core.exception import IngestHighMatchMeme
from redditrepostsleuth.core.logging import log
from redditrepostsleuth.core.model.repostmatch import RepostMatch
from redditrepostsleuth.core.model.search.image_search_match import ImageSearchMatch
from redditrepostsleuth.core.model.search.image_search_results import ImageSearchResults
from redditrepostsleuth.core.model.search.search_match import SearchMatch
from redditrepostsleuth.core.model.search.search_results import SearchResults
from redditrepostsleuth.core.util.constants import USER_AGENTS
from redditrepostsleuth.core.util.helpers import set_repost_search_params_from_search_settings
from redditrepostsleuth.core.util.imagehashing import get_image_hashes
from redditrepostsleuth.core.util.repost_filters import filter_same_post, filter_same_author, cross_post_filter, \
    filter_newer_matches, same_sub_filter, filter_title_distance, filter_days_old_matches, filter_removed_posts, \
    filter_removed_posts_util_api

log = logging.getLogger(__name__)
config = Config()

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


def log_search(
        uow: UnitOfWork,
        search_results: SearchResults,
        source: str,
        post_type_name: str
) -> Optional[RepostSearch]:

    try:
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


# TODO - 1/12/2021 - Possibly make the generic. It's messing with auto complete when used for image searches
def filter_search_results(search_results: SearchResults) -> SearchResults:
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

        if search_results.search_settings.filter_dead_matches:
            search_results.search_times.start_timer('filter_deleted_posts_time')
            search_results.matches = filter_removed_posts_util_api(search_results.matches)
            search_results.search_times.stop_timer('filter_deleted_posts_time')
            print(f'Filter dead time: {search_results.search_times.filter_deleted_posts_time}')

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

def check_for_high_match_meme(search_results: ImageSearchResults, uow: UnitOfWork) -> None:
    if search_results.meme_template is not None:
        return

    meme_template = None
    # TODO - 1/12/2021 - Should probably remember the meme in subreddit check and generate more templates
    if len(search_results.matches) > 5 and 'meme' in search_results.checked_post.subreddit.lower():
        try:
            meme_hashes = get_image_hashes(search_results.checked_post.url, hash_size=32)
        except Exception as e:
            log.warning('Failed to get meme hash for %s', search_results.checked_post.post_id)
            return

        try:

            meme_template = MemeTemplate(
                dhash_h=next((post_hash.hash for post_hash in search_results.checked_post.hashes if post_hash.hash_type_id == 1), None),
                dhash_256=meme_hashes['dhash_h'],
                post_id=search_results.checked_post.id
            )

            uow.meme_template.add(meme_template)
            uow.commit()
        except IntegrityError as e:
            log.exception(f'Failed to create meme template. Template already exists for post {search_results.checked_post.post_id}', exc_info=True)
            meme_template = None

    if meme_template:
        log.info('Saved new meme template for post %s in %s', search_results.checked_post.post_id, search_results.checked_post.subreddit)
        # Raise exception so celery will retry the task and use the new meme template
        raise IngestHighMatchMeme('Created meme template.  Post needs to be rechecked')


def save_image_repost_result(
        search_results: ImageSearchResults,
        uow: UnitOfWork,
        source: str,
        high_match_check: bool = False,

) -> None:

    # TODO: This needs to be made generic to support all reposts types

    if not search_results.matches:
        log.debug('Post %s has no matches', search_results.checked_post.post_id)
        return

    # This is used for ingest repost checking.  If a meme template gets created, it intentionally throws a
    # IngestHighMatchMeme exception.  This will cause celery to retry the task so the newly created meme template
    # gets used
    if high_match_check:
        check_for_high_match_meme(search_results, uow) # This intentionally throws if we create a meme template

    log.info('Creating repost. Post %s is a repost of %s', search_results.checked_post.url,
             search_results.matches[0].post.url)

    new_repost = Repost(
        post_id=search_results.checked_post.id,
        repost_of_id=search_results.matches[0].post.id,
        author=search_results.checked_post.author,
        search_id=search_results.logged_search.id if search_results.logged_search else None,
        subreddit=search_results.checked_post.subreddit,
        source=source,
        post_type_id=search_results.checked_post.post_type_id,
        hamming_distance=search_results.closest_match.hamming_distance if search_results.closest_match else None
    )

    uow.repost.add(new_repost)

    try:
        uow.commit()
    except Exception as e:
        log.exception('Failed to save image repost', exc_info=True)


def save_repost(search_results: SearchResults, uow: UnitOfWork, source: str) -> None:
    if not search_results.matches:
        log.info('No search matches, skipping repost save')
        return

    log.info('Found %s matching links', len(search_results.matches))
    log.info('Creating Link Repost. Post %s is a repost of %s', search_results.checked_post.post_id,
             search_results.matches[0].post.post_id)

    repost_of = search_results.matches[0].post

    new_repost = Repost(
        post_id=search_results.checked_post.id,
        repost_of_id=repost_of.id,
        author=search_results.checked_post.author,
        subreddit=search_results.checked_post.subreddit,
        post_type_id=search_results.checked_post.post_type_id,
        source=source,
        search_id=search_results.logged_search.id
    )

    uow.repost.add(new_repost)
    try:
        uow.commit()
        log.debug('Saved repost for post %s', search_results.checked_post.post_id)
    except IntegrityError:
        log.error('Failed to save link repost, it already exists')
    except Exception as e:
        log.exception('Failed to save link repost', exc_info=True)
