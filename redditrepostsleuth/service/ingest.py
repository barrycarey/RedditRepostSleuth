import json

import requests
import time
from queue import Queue
from datetime import datetime

from celery import group
from praw import Reddit
from prawcore import Forbidden
import webbrowser
from redditrepostsleuth.celery.tasks import save_new_post, update_cross_post_parent, save_new_comment
from redditrepostsleuth.common.logging import log
from redditrepostsleuth.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.util.objectmapping import submission_to_post, pushshift_to_post


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
        while True:
            with self.uowm.start() as uow:
                url = 'https://api.pushshift.io/reddit/search/submission?size=10000'
                if oldest_id:
                    url += '&before=' + str((oldest_id + 10))

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
                with open('push_last.txt', 'w') as f:
                    f.write(str(oldest_id))

                for submission in data['data']:
                    #log.info(datetime.fromtimestamp(submission.get('created_utc', None)))
                    existing = uow.posts.get_by_post_id(submission['id'])
                    if existing:
                        log.info('Skipping existing post found by %s', existing.ingested_from)
                    post = pushshift_to_post(submission)
                    save_new_post.apply_async((post,), queue='postingest')

    def ingest_pushshift_catch(self):
        while True:
            with self.uowm.start() as uow:
                url = 'https://api.pushshift.io/reddit/search/submission?size=2000'

                try:
                    r = requests.get(url)
                except Exception as e:
                    log.exception('Exception getting Push Shift result', exc_info=True)
                    continue

                if r.status_code != 200:
                    log.error('Unexpected status code %s from Push Shift', r.status_code)
                    continue

                data = json.loads(r.text)

                for submission in data['data']:
                    log.info(datetime.fromtimestamp(submission.get('created_utc', None)))
                    existing = uow.posts.get_by_post_id(submission['id'])
                    if existing:
                        log.info('Skipping existing post found by %s', existing.ingested_from)
                        continue
                    post = pushshift_to_post(submission)
                    save_new_post.apply_async((post,), queue='testingest')

                time.sleep(30)

    def ingest_new_comments(self):
        while True:
            try:
                for comment in self.reddit.subreddit('all').stream.comments():
                    save_new_comment.apply_async((comment,), queue='commentingest')
            except Exception as e:
                log.exception('Problem in comment ingest thread', exc_info=True)