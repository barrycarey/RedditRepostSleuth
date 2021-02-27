import json
import os
import time
from datetime import datetime

import requests

from redditrepostsleuth.core.celery.ingesttasks import save_pushshift_results
from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.db.db_utils import get_db_engine
from redditrepostsleuth.core.db.uow.sqlalchemyunitofworkmanager import SqlAlchemyUnitOfWorkManager
from redditrepostsleuth.core.logging import log



oldest_timestamp = None

config = Config()
uowm = SqlAlchemyUnitOfWorkManager(get_db_engine(config))

while True:
    oldest_id = None
    start_time = None
#            base_url = 'https://api.pushshift.io/reddit/search/submission?size=2000&sort_type=created_utc&sort=desc'
    base_url = 'https://beta.pushshift.io/search/reddit/submissions?size=1000&sort_type=created_utc&sort=desc'
    while True:

        if oldest_id:
            url = base_url + '&max_sid=' + str(oldest_id)
        else:
            url = base_url

        try:
            r = requests.get(f'{config.util_api}/pushshift', params={'url': url})
        except Exception as e:
            log.exception('Exception getting Push Shift result', exc_info=True)
            time.sleep(10)
            continue

        if r.status_code != 200:
            log.error('Unexpected status code %s from Push Shift', r.status_code)
            time.sleep(10)
            continue

        try:
            response = json.loads(r.text)
        except Exception:
            oldest_id = oldest_id - 90
            log.exception('Error decoding json')
            time.sleep(10)
            continue

        if response['status'] != 'success':
            log.error('Error from API.  Status code %s, reason %s', response['status_code'],
                      response['message'])
            if response['status_code'] == '502':
                continue
            continue

        data = response['payload']
        oldest_id = data['data'][-1]['sid']
        oldest_created_time = data['data'][-1]['created_utc']
        log.debug('Oldest: %s | Newest: %s', datetime.utcfromtimestamp(data['data'][-1]['created_utc']), datetime.utcfromtimestamp(data['data'][0]['created_utc']))

        try:
            save_pushshift_results.apply_async((data['data'],), queue='pushshift')
        except Exception as e:
            log.exception('Failed to send to pushshift', exc_info=False)
