import json
import os

import requests
import time
from datetime import datetime

from praw import Reddit
from prawcore import Forbidden
from redditrepostsleuth.common.celery.tasks import save_new_post, save_new_comment, \
    ingest_pushshift_url
from redditrepostsleuth.common.logging import log
from redditrepostsleuth.common.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.common.util.objectmapping import submission_to_post, pushshift_to_post


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


                time.sleep(60)



    def ingest_new_comments(self):
        while True:
            try:
                for comment in self.reddit.subreddit('all').stream.comments():
                    save_new_comment.apply_async((comment,), queue='commentingest')
            except Exception as e:
                log.exception('Problem in comment ingest thread', exc_info=True)