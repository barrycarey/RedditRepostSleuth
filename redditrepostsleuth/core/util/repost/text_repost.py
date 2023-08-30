import json
import logging
from typing import Optional

import requests
from requests.exceptions import ConnectionError
from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.db.databasemodels import Post
from redditrepostsleuth.core.db.db_utils import get_db_engine
from redditrepostsleuth.core.db.uow.unitofwork import UnitOfWork
from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.core.exception import IndexApiException
from redditrepostsleuth.core.model.image_index_api_result import APISearchResults
from redditrepostsleuth.core.model.search.search_match import SearchMatch
from redditrepostsleuth.core.model.search.search_results import SearchResults
from redditrepostsleuth.core.model.search.text_search_match import TextSearchMatch
from redditrepostsleuth.core.model.search_settings import SearchSettings
from redditrepostsleuth.core.util.helpers import get_default_link_search_settings, get_default_text_search_settings

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

def get_text_post_matches(
        post: Post,
        uow: UnitOfWork, # TODO - Start passing UOW instead of UOWM
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



if __name__ == '__main__':
    uowm = UnitOfWorkManager(get_db_engine(config))
    with uowm.start() as uow:
        post = uow.posts.get_by_id(1043928780)

    get_text_post_matches(post, uow, get_default_text_search_settings(config))