import json
import time
from datetime import datetime
from typing import Text

import requests

from redditrepostsleuth.core.celery.tasks.ingest_tasks import save_pushshift_results
from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.db.db_utils import get_db_engine
from redditrepostsleuth.core.db.uow.sqlalchemyunitofworkmanager import SqlAlchemyUnitOfWorkManager
from redditrepostsleuth.core.logging import log


config = Config()
uowm = SqlAlchemyUnitOfWorkManager(get_db_engine(config))

def fetch_results(url: Text):
    try:
        r = requests.get(f'{config.util_api}/pushshift', params={'url': url})
    except Exception as e:
        log.exception('Exception getting Push Shift result', exc_info=True)
        time.sleep(10)
        return

    try:
        response = json.loads(r.text)
    except Exception:
        log.exception('Error decoding json')
        time.sleep(10)
        return

    if response['status'] != 'success':
        log.error('Error from API.  Status code %s, reason %s', response['status_code'],
                  response['message'])
        return

    return response['payload']

def get_from_api(oldest_created = None):
    base_url = 'https://api.pushshift.io/reddit/search/submission?size=2000&sort_type=created_utc&sort=desc'
    if oldest_created:
        url = base_url + '&before=' + str(oldest_created)
    else:
        url = base_url
    return fetch_results(url)

def parse_and_submit_to_queue(data) -> Text:
    log.debug('Oldest: %s | Newest: %s', datetime.utcfromtimestamp(data[-1]['created_utc']),
              datetime.utcfromtimestamp(data[0]['created_utc']))

    try:
        save_pushshift_results.apply_async((data,), queue='pushshift')
    except Exception as e:
        log.exception('Failed to send to celery', exc_info=False)


oldest_created = None
while True:
    results = get_from_api(oldest_created)
    if not results:
        continue
    oldest_created = results['data'][-1]['created_utc']
    parse_and_submit_to_queue(results['data'])

