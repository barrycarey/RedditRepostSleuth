import json
import logging
import sys
import time
from datetime import datetime
from json import JSONDecodeError

import requests

sys.path.append('./')
from redditrepostsleuth.core.logfilters import ContextFilter
from redditrepostsleuth.core.logging import configure_logger
from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.util.helpers import get_reddit_instance, get_newest_praw_post_id, get_next_ids
from redditrepostsleuth.core.celery.ingesttasks import save_pushshift_results, save_new_post
from redditrepostsleuth.core.util.objectmapping import pushshift_to_post

log = configure_logger(name='redditrepostsleuth')

if __name__ == '__main__':
    log.info('Starting post ingestor')
    config = Config()
    reddit = get_reddit_instance(config)
    newest_id = get_newest_praw_post_id(reddit)

    while True:
        ids_to_get = get_next_ids(newest_id, 100)[0]
        r = requests.get(f'{config.util_api}/reddit/submissions', params={'submission_ids': ','.join(ids_to_get)})
        try:
            results = json.loads(r.text)
        except JSONDecodeError:
            log.error('Failed to decode results')
            continue
        if len(results) == 0:
            log.info('No results')
            time.sleep(60)
            continue

        for submission in results:
            post = pushshift_to_post(submission)
            save_new_post.apply_async((post,), queue='post_ingest')

        log.info('%s sent to ingest queue', len(results))

        ingest_delay = datetime.utcnow() - datetime.utcfromtimestamp(results[0]['created_utc'])
        log.info('Current Delay: %s', ingest_delay)

        newest_id = ids_to_get[-1].replace('t3_', '')