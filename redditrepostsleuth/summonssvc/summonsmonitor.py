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
                        post = uow.posts.get_by_post_id(comment.submission.id)
                        if not post:
                            log.error('Failed to find post %s for summons', comment.submission.id)
                            continue
                        summons = Summons(
                            post_id=post.id,
                            comment_id=comment.id,
                            comment_body=comment.body.replace('\\',''),
                            summons_received_at=datetime.fromtimestamp(comment.created_utc),
                            requestor=comment.author.name,
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

