import re
import time
from datetime import datetime

from praw import Reddit

from redditrepostsleuth.core.celery.tasks import save_new_comment
from redditrepostsleuth.common.logging import log
from redditrepostsleuth.common.config import config
from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.common.model.db import Summons
from redditrepostsleuth.service.requestservice import RequestService


class CommentMonitor:

    def __init__(self, reddit: Reddit, request_service: RequestService, uowm: UnitOfWorkManager):
        self.reddit = reddit
        self.uowm = uowm
        self.request_service = request_service

    def monitor_for_summons(self):
        """
        Monitors the subreddits set in the config for comments containing the summoning string
        """
        for comment in self.reddit.subreddit(config.subreddit_summons).stream.comments():
            if comment is None:
                continue
            #log.info('COMMENT %s: %s', datetime.fromtimestamp(comment.created_utc), comment.body)
            if re.search(config.summon_command, comment.body, re.IGNORECASE):
                log.info('Received summons from %s in comment %s. Comment: %s', comment.author.name, comment.id, comment.body)
                with self.uowm.start() as uow:
                    if not uow.summons.get_by_comment_id(comment.id):
                        summons = Summons(
                            post_id=comment.submission.id,
                            comment_id=comment.id,
                            comment_body=comment.body,
                            summons_received_at=datetime.fromtimestamp(comment.created_utc),
                            requestor=comment.author.name
                        )
                        uow.summons.add(summons)
                        uow.commit()

    def handle_summons(self):
        """
        Continually check the summons table for new requests.  Handle them as they are found
        """
        while True:
            try:
                with self.uowm.start() as uow:
                    summons = uow.summons.get_unreplied()
                    for s in summons:
                        self.request_service.handle_repost_request(s)
                time.sleep(2)
            except Exception as e:
                log.exception('Exception in handle summons thread')


    def ingest_new_comments(self):
        while True:
            try:
                for comment in self.reddit.subreddit('all').stream.comments():
                    save_new_comment.apply_async((comment,), queue='commentingest')
            except Exception as e:
                log.exception('Problem in comment ingest thread', exc_info=True)

