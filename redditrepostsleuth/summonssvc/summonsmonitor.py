import json
import logging
import re
import time
from datetime import datetime

import requests
from praw import Reddit
from praw.models import Comment
from prawcore import ResponseException
from sqlalchemy.exc import DataError

from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.logging import log
from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.core.db.databasemodels import Summons



class SummonsMonitor:

    def __init__(self, reddit: Reddit, uowm: UnitOfWorkManager, config: Config):
        self.reddit = reddit
        self.uowm = uowm
        self.config = config
        #self.request_service = request_service

    def monitor_for_summons(self, subreddits: str = 'all'):
        """
        Monitors the subreddits set in the config for comments containing the summoning string
        """
        log.info('Starting praw summons monitor for subs %s', subreddits)
        while True:
            try:
                for comment in self.reddit.subreddit(subreddits).stream.comments():
                    if comment is None:
                        continue
                    if self.check_for_summons(comment.body, '\?repost'):
                        if comment.author.name.lower() in ['sneakpeekbot', 'automoderator']:
                            continue
                        self._save_summons(comment)
            except ResponseException as e:
                if e.response.status_code == 429:
                    log.error('IP Rate limit hit.  Waiting')
                    time.sleep(60)
                    continue
            except Exception as e:
                if 'code: 429' in str(e):
                    log.error('Too many requests from IP.  Waiting')
                    time.sleep(60)
                    continue
                log.exception('Praw summons thread died', exc_info=True)

    @staticmethod
    def check_for_summons(comment: str, summons_string: str) -> bool:
        if re.search(summons_string, comment, re.IGNORECASE):
            log.info('Comment [%s] matches summons string [%s]', comment, summons_string)
            return True
        return False

    def _save_summons(self, comment: Comment):

        with self.uowm.start() as uow:
            if not uow.summons.get_by_comment_id(comment.id):
                summons = Summons(
                    post_id=comment.submission.id,
                    comment_id=comment.id,
                    comment_body=comment.body,
                    summons_received_at=datetime.fromtimestamp(comment.created_utc),
                    requestor=comment.author.name,
                    subreddit=comment.subreddit.display_name
                )
                uow.summons.add(summons)
                uow.commit()

    def monitor_for_mentions(self):
        bad_mentions = []
        while True:
            try:
                for comment in self.reddit.inbox.mentions():
                    if comment.created_utc < datetime.utcnow().timestamp() - 86400:
                        log.debug('Skipping old mention. Created at %s', datetime.fromtimestamp(comment.created_utc))
                        continue

                    if comment.author.name.lower() in ['sneakpeekbot', 'automoderator']:
                        continue

                    if comment.id in bad_mentions:
                        continue

                    with self.uowm.start() as uow:
                        existing_summons = uow.summons.get_by_comment_id(comment.id)
                        if existing_summons:
                            log.debug('Skipping existing mention %s', comment.id)
                            continue
                        summons = Summons(
                            post_id=comment.submission.id,
                            comment_id=comment.id,
                            comment_body=comment.body.replace('\\',''),
                            summons_received_at=datetime.fromtimestamp(comment.created_utc),
                            requestor=comment.author.name,
                            subreddit=comment.subreddit.display_name
                        )
                        uow.summons.add(summons)
                        try:
                            uow.commit()
                        except DataError as e:
                            log.error('SQLAlchemy Data error saving comment')
                            bad_mentions.append(comment.id)
                            continue
            except ResponseException as e:
                if e.response.status_code == 429:
                    log.error('IP Rate limit hit.  Waiting')
                    time.sleep(60)
                    continue
            except AssertionError as e:
                if 'code: 429' in str(e):
                    log.error('Too many requests from IP.  Waiting')
                    time.sleep(60)
                    return
            except Exception as e:
                log.exception('Mention monitor failed', exc_info=True)

            time.sleep(20)


    def monitor_for_summons_pushshift(self):
        try:
            # TODO - Remove try/catch after we find crashes
            while True:
                oldest_id = None
                start_time = None
                base_url = 'https://api.pushshift.io/reddit/search/comment?size=1000&sort_type=created_utc&sort=desc'
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

                    self.process_pushshift_comments(data['data'])

                    if not start_time:
                        start_time = data['data'][0]['created_utc']

                    start_end_dif = start_time - oldest_id
                    if start_end_dif > 600:
                        log.info('Reached end of 30 minute window, starting over')
                        break
        except Exception as e:
            log.exception('Pushshift summons thread crashed', exc_info=True)

    def process_pushshift_comments(self, comments) -> None:
            for comment in comments:
                if self.check_for_summons(comment['body'], '\?repost'):
                    detection_diff = (datetime.utcnow() - datetime.utcfromtimestamp(comment['created_utc'])).seconds / 60
                    log.info('Summons detection diff %s minutes', detection_diff)
                    comment_obj = self.reddit.comment(comment['id'])
                    if not comment_obj:
                        log.error('Error saving summons.  Cannot get Reddit comment with id %s', comment['id'])
                        continue
                    self._save_summons(comment_obj)