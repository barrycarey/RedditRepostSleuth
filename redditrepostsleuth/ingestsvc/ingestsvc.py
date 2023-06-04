import json
import sys
import time
from datetime import datetime
from json import JSONDecodeError
from typing import List, Dict, Optional

import requests
from requests.exceptions import ConnectionError

sys.path.append('./')
from redditrepostsleuth.core.db.databasemodels import Post
from redditrepostsleuth.core.db.db_utils import get_db_engine
from redditrepostsleuth.core.db.uow.sqlalchemyunitofworkmanager import SqlAlchemyUnitOfWorkManager
from redditrepostsleuth.core.logfilters import ContextFilter
from redditrepostsleuth.core.logging import configure_logger
from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.util.helpers import get_reddit_instance, get_newest_praw_post_id, get_next_ids, \
    base36decode, chunk_list
from redditrepostsleuth.core.celery.ingesttasks import save_pushshift_results, save_new_post
from redditrepostsleuth.core.util.objectmapping import pushshift_to_post

log = configure_logger(name='redditrepostsleuth')

def startup_backfill(newest_post_id: str, oldest_post_id: str) -> None:

    missing_ids = get_next_ids(oldest_post_id, base36decode(newest_post_id) - base36decode(oldest_post_id))[0]
    log.info('%s missing posts to backfill', len(missing_ids))
    for chunk in chunk_list(missing_ids, 100):
        results = get_submissions(chunk)
        if not results:
            continue
        queue_posts_for_ingest([pushshift_to_post(submission) for submission in results])
    log.info('Finished backfill ')

def get_submissions(submission_ids: List[str]) -> Optional[List[Dict]]:
    try:
        r = requests.get(f'{config.util_api}/reddit/submissions', params={'submission_ids': ','.join(submission_ids)}, timeout=7)
    except ConnectionError as e:
        log.error('Failed to connect to util API')
        time.sleep(10)
        return None
    try:
        results = json.loads(r.text)
    except JSONDecodeError:
        log.error('Failed to decode results')
        return None
    return results

def queue_posts_for_ingest(posts: List[Post]):
    log.info('Sending batch of %s posts to ingest queue', len(posts))
    for post in posts:
        save_new_post.apply_async((post,), queue='post_ingest')



if __name__ == '__main__':
    log.info('Starting post ingestor')
    config = Config()
    reddit = get_reddit_instance(config)
    newest_id = get_newest_praw_post_id(reddit)
    uowm = SqlAlchemyUnitOfWorkManager(get_db_engine(config))

    with uowm.start() as uow:
        oldest_post = uow.posts.get_newest_post()
        oldest_id = oldest_post.post_id

    #threading.Thread(target=startup_backfill, args=(newest_id, oldest_id), name='praw_ingest').start()
   # startup_backfill(newest_id, oldest_id)

    while True:
        ids_to_get = get_next_ids(newest_id, 100)[0]
        results = get_submissions(ids_to_get)
        if not results:
            continue
        if len(results) == 0:
            log.info('No results')
            time.sleep(60)
            continue

        queue_posts_for_ingest([pushshift_to_post(submission) for submission in results])

        log.info('%s sent to ingest queue', len(results))

        ingest_delay = datetime.utcnow() - datetime.utcfromtimestamp(results[0]['created_utc'])
        log.info('Current Delay: %s', ingest_delay)

        newest_id = results[-1]['id']