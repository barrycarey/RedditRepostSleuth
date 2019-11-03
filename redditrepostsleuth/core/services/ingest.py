import json
import os

import requests
import time
from datetime import datetime

from praw import Reddit
from prawcore import Forbidden
from redditrepostsleuth.core.celery.tasks import save_new_post, save_new_comment, \
    ingest_pushshift_url, save_pushshift_results
from redditrepostsleuth.core.logging import log
from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.core.util.objectmapping import submission_to_post, pushshift_to_post


class Ingest:
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

                            save_new_post.apply_async((post,))
                    except Forbidden as e:
                        pass
            except Exception as e:
                log.exception('INGEST THREAD DIED', exc_info=True)

    def ingest_pushshift(self):
        oldest_id = None
        processed = []
        if os.path.isfile('push_last.txt'):
            with open('push_last.txt', 'r') as f:
                oldest_id = int(f.read())

        while True:
            with self.uowm.start() as uow:
                url = 'https://api.pushshift.io/reddit/search/submission?size=2000&sort_type=created_utc&sort=desc'
                if oldest_id:
                    url += '&before=' + str(oldest_id)
                    log.info('Oldest: %s', datetime.utcfromtimestamp(oldest_id))
                else:
                    oldest_id = round(datetime.utcnow().timestamp())

                oldest_id = oldest_id - 90

                ingest_pushshift_url.apply_async((url,), queue='pushshift')

                with open('push_last.txt', 'w') as f:
                    f.write(str(oldest_id))
                #time.sleep(.1)
                continue

                try:
                    r = requests.get(url)
                except Exception as e:
                    log.exception('Exception getting Push Shift result', exc_info=True)
                    continue

                if r.status_code != 200:
                    log.error('Unexpected status code %s from Push Shift', r.status_code)
                    continue

                data = json.loads(r.text)

                oldest_id = data['data'][-1]['created_utc']
                log.info('Oldest: %s', datetime.utcfromtimestamp(oldest_id))
                with open('push_last.txt', 'w') as f:
                    f.write(str(oldest_id))
                log.info('Total Results: %s', len(data['data']))
                for submission in data['data']:
                    #log.info(datetime.fromtimestamp(submission.get('created_utc', None)))
                    existing = uow.posts.get_by_post_id(submission['id'])
                    if existing:
                        continue
                    post = pushshift_to_post(submission)
                    save_new_post.apply_async((post,), queue='postingest')

    def ingest_pushshift_catch(self):
        while True:
            with self.uowm.start() as uow:
                newest = uow.posts.get_newest_praw()

                url = 'https://api.pushshift.io/reddit/search/submission?size=1000&sort_type=created_utc&sort=desc' + str(newest.created_at.timestamp() - 600)

                try:
                    r = requests.get(url)
                except Exception as e:
                    log.exception('Exception getting Push Shift result', exc_info=True)
                    time.sleep(2)
                    continue

                if r.status_code != 200:
                    log.error('Unexpected status code %s from Push Shift', r.status_code)
                    continue

                data = json.loads(r.text)

                for submission in data['data']:
                    #log.info(datetime.fromtimestamp(submission.get('created_utc', None)))
                    existing = uow.posts.get_by_post_id(submission['id'])
                    if existing:
                        continue
                    log.info('Post %s was missed by PRAW', submission['id'])
                    post = pushshift_to_post(submission)
                    save_new_post.apply_async((post,), queue='postingest')

                time.sleep(60)

    def ingest_pushshift_window(self):

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
                log.info('Oldest: %s', datetime.utcfromtimestamp(oldest_id))

                if not start_time:
                    start_time = data['data'][0]['created_utc']

                save_pushshift_results.apply_async((data['data'],), queue='pushshift')

                start_end_dif = start_time - oldest_id
                if  start_end_dif > 3600:
                    log.info('Reached end of 1 hour window, starting over')
                    break

    def ingest_new_comments(self):
        while True:
            try:
                for comment in self.reddit.subreddit('all').stream.comments():
                    save_new_comment.apply_async((comment,), queue='commentingest')
            except Exception as e:
                log.exception('Problem in comment ingest thread', exc_info=True)