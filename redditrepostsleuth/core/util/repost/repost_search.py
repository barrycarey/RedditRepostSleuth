import json
import logging
from hashlib import md5
from typing import Optional, Callable

import requests
from requests.exceptions import ConnectionError

from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.db.databasemodels import Post
from redditrepostsleuth.core.db.db_utils import get_db_engine
from redditrepostsleuth.core.db.uow.unitofwork import UnitOfWork
from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.core.exception import IndexApiException
from redditrepostsleuth.core.model.image_index_api_result import APISearchResults
from redditrepostsleuth.core.model.image_search_settings import ImageSearchSettings
from redditrepostsleuth.core.model.link_search_times import LinkSearchTimes
from redditrepostsleuth.core.model.search.image_search_results import ImageSearchResults
from redditrepostsleuth.core.model.search.link_search_results import LinkSearchResults
from redditrepostsleuth.core.model.search.search_match import SearchMatch
from redditrepostsleuth.core.model.search.search_results import SearchResults
from redditrepostsleuth.core.model.search.text_search_match import TextSearchMatch
from redditrepostsleuth.core.model.search_settings import SearchSettings
from redditrepostsleuth.core.services.duplicateimageservice import DuplicateImageService
from redditrepostsleuth.core.util.helpers import get_default_text_search_settings
from redditrepostsleuth.core.util.repost.repost_helpers import save_image_repost_result, log, log_search, save_repost

config = Config()
log = logging.getLogger(__name__)

def get_text_matches(text: str) -> APISearchResults:

    try:
        res = requests.post(f'{config.index_api}/text', json={'text': text})
    except ConnectionError:
        log.error('Failed to connect to Index API')
        raise

    if res.status_code != 200:
        log.error('Unexpected status code %s from Index API', res.status_code)
        raise IndexApiException(f'Unexpected Status {res.status_code} from Index API')

    return APISearchResults(**json.loads(res.text))

def text_search_by_post(
        post: Post,
        uow: UnitOfWork,
        search_settings: SearchSettings
) -> Optional[SearchResults]:

    search_results = SearchResults(post.url, checked_post=post, search_settings=search_settings)
    api_results = get_text_matches(post.selftext)
    for index_results in api_results.results:
        for match in index_results.matches:
            post = uow.posts.get_by_id(match.id)
            if not post:
                log.warning('Failed to find post for index match with ID %s', match.id)
                continue
            search_results.matches.append(TextSearchMatch(post, match.distance))

    search_results.search_times.total_search_time = api_results.total_search_time

    return search_results


def image_search_by_post(
        post: Post,
        uow: UnitOfWork,
        dup_image_src: DuplicateImageService,
        search_settings: ImageSearchSettings,
        source: str,
        high_match_meme_check: bool = False
) -> ImageSearchResults:
    search_results = dup_image_src.check_image(
        post.url,
        post=post,
        source=source,
        search_settings=search_settings
    )
    if search_results.matches:
        save_image_repost_result(search_results, uow, source, high_match_check=high_match_meme_check)

    log.debug(search_results)
    return search_results

if __name__ == '__main__':
    uowm = UnitOfWorkManager(get_db_engine(config))
    with uowm.start() as uow:
        post = uow.posts.get_by_id(1043928780)

    text_search_by_post(post, uow, get_default_text_search_settings(config))


def link_search(
        url: str,
        uow: UnitOfWork,
        search_settings: SearchSettings,
        source: str,
        filter_function: Callable[[SearchResults], SearchResults] = None,
        post: Post = None,
        get_total: bool = False,
        ) -> LinkSearchResults:

    url_hash = md5(url.encode('utf-8'))
    url_hash = url_hash.hexdigest()

    search_results = LinkSearchResults(url, search_settings, checked_post=post, search_times=LinkSearchTimes())
    search_results.search_times.start_timer('query_time')
    search_results.search_times.start_timer('total_search_time')
    raw_results: list[Post] = uow.posts.find_all_by_url(url_hash)
    search_results.search_times.stop_timer('query_time')
    log.debug('Query time: %s', search_results.search_times.query_time)
    search_results.matches = [SearchMatch(url, post) for post in raw_results]

    if get_total:
        search_results.total_searched = uow.posts.count_by_type(3)

    if filter_function:
        search_results = filter_function(search_results)

    log_search(uow, search_results, source, 'link')
    save_repost(search_results, uow, source)

    return search_results
