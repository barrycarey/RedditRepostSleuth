import json

import requests
import time
from datetime import datetime

from praw import Reddit
from prawcore import Forbidden, ResponseException
from redditrepostsleuth.core.logging import log
from redditrepostsleuth.core.celery.ingesttasks import save_new_post, save_pushshift_results
from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.core.util.helpers import post_type_from_url
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
                            if not post.post_type:
                                post.post_type = post_type_from_url(post.url)
                                log.error('Last resort post type %s', post.post_type)
                                log.error(post.url)
                            save_new_post.apply_async((post,), queue='postingest')
                    except Forbidden as e:
                        pass
            except Exception as e:
                log.exception('INGEST THREAD DIED', exc_info=True)

    def ingest_without_stream(self):
        seen_posts = []
        while True:
            try:
                if len(seen_posts) > 10000:
                    seen_posts = []
                try:
                    submissions = [sub for sub in self.reddit.subreddit('all').new(limit=500)]
                except ResponseException as e:
                    if e.response.status_code == 429:
                        log.error('Too many requests from IP.  Waiting')
                        time.sleep(60)
                        continue
                except Exception as e:
                    if 'code: 429' in str(e):
                        log.error('Too many requests from IP.  Waiting')
                        time.sleep(60)
                        continue

                log.debug('%s posts from API', len(submissions))
                for submission in submissions:
                    if submission.id in seen_posts:
                        continue
                    #log.debug('Saving post %s', submission.id)
                    post = submission_to_post(submission)
                    if not post.post_type:
                        post.post_type = post_type_from_url(post.url)
                        #log.debug('Last resort post type %s', post.post_type)
                        #log.debug(post.url)
                    save_new_post.apply_async((post,), queue='postingest')
                    seen_posts.append(post.post_id)
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
                    r = requests.post('http://sr3.plxbx.com:8888/crosspost', data={'url': url})
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

                try:
                    save_pushshift_results.apply_async((data['data'],), queue='pushshift')
                except Exception as e:
                    log.exception('Failed to send to pushshift', exc_info=False)
                    time.sleep(5)
                    try:
                        save_pushshift_results.apply_async((data['data'],), queue='pushshift')
                    except Exception:
                        pass


                start_end_dif = start_time - oldest_id
                if start_end_dif > 3600:
                    log.debug('Reached end of 1 hour window, starting over')
                    break


