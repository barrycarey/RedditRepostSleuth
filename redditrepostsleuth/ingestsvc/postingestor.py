import json

import requests
import time
from datetime import datetime

from praw import Reddit
from prawcore import Forbidden
from redditrepostsleuth.core.logging import log
from redditrepostsleuth.core.celery.ingesttasks import save_new_post, save_pushshift_results
from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.core.util.objectmapping import submission_to_post


class PostIngestor:
    def __init__(self, reddit: Reddit, uowm: UnitOfWorkManager) -> None:
        self.existing_posts = []
        self.reddit = reddit
        self.uowm = uowm

    def ingest_new_posts(self):
        while True:
            sr = self.reddit.subreddit('all')
            try:
                while True:
                    try:
                        for submission in sr.stream.submissions():
                            log.debug('Saving post %s', submission.id)
                            post = submission_to_post(submission)

                            save_new_post.apply_async((post,), queue='postingest')
                    except Forbidden as e:
                        pass
            except Exception as e:
                log.exception('INGEST THREAD DIED', exc_info=True)

    def ingest_pushshift(self):
        while True:
            oldest_id = None
            start_time = None
            base_url = 'https://api.pushshift.io/reddit/search/submission?size=2000&sort_type=created_utc&sort=desc'
            while True:

                if oldest_id:
                    url = base_url + '&before=' + str(oldest_id)
                else:
                    url = base_url

                try:
                    r = requests.post('http://sr2.plxbx.com:8888/crosspost', data={'url': url})
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

                data = json.loads(response['payload'])
                oldest_id = data['data'][-1]['created_utc']
                log.debug('Oldest: %s', datetime.utcfromtimestamp(oldest_id))

                if not start_time:
                    start_time = data['data'][0]['created_utc']

                save_pushshift_results.apply_async((data['data'],), queue='pushshift2')

                start_end_dif = start_time - oldest_id
                if start_end_dif > 3600:
                    log.debug('Reached end of 1 hour window, starting over')
                    break


