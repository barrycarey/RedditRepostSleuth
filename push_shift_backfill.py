import json
import os
from datetime import datetime

import requests

from redditrepostsleuth.core.celery.ingesttasks import save_pushshift_results
from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.db.db_utils import get_db_engine
from redditrepostsleuth.core.db.uow.sqlalchemyunitofworkmanager import SqlAlchemyUnitOfWorkManager
from redditrepostsleuth.core.logging import log



oldest_id = None

config = Config()
uowm = SqlAlchemyUnitOfWorkManager(get_db_engine(config))

if os.path.isfile('push_last1.txt'):
    with open('push_last1.txt', 'r') as f:
        oldest_id = int(f.read())

while True:
    url = 'https://api.pushshift.io/reddit/search/submission?size=2000&sort_type=created_utc&sort=desc'
    if oldest_id:
        url += '&before=' + str(oldest_id)
        log.info('Oldest: %s', datetime.utcfromtimestamp(oldest_id))
    else:
        oldest_id = round(datetime.utcnow().timestamp())


    try:
        r = requests.post('http://sr3.plxbx.com:8888/crosspost', data={'url': url})
    except Exception as e:
        log.exception('Exception getting Push Shift result', exc_info=True)
        continue

    if r.status_code != 200:
        log.error('Unexpected status code %s from Push Shift', r.status_code)
        continue

    try:
        response = json.loads(r.text)
    except Exception:
        oldest_id = oldest_id - 90
        log.exception('Error decoding json')
        continue

    if response['status'] != 'success':
        log.error('Error from API.  Status code {}, reason {}', response['status_code'], response['message'])
        if response['status_code'] == '502':
            continue
        continue

    data = json.loads(response['payload'])
    oldest_id = data['data'][-1]['created_utc']
    with open('push_last1.txt', 'w') as f:
        f.write(str(oldest_id))
    log.info('Oldest: %s', datetime.utcfromtimestamp(oldest_id))

    log.info('Total Results: %s', len(data['data']))
    save_pushshift_results.apply_async((data['data'],), queue='pushshift')
    """
    start = perf_counter()
    with uowm.start() as uow:
        for submission in data['data']:

            existing = uow.posts.get_by_post_id(submission['id'])
            if existing:
                continue
            post = pushshift_to_post(submission)
            save_new_post.apply_async((post,), queue='postingest')

    log.info('Query took {}', perf_counter() - start)
    """