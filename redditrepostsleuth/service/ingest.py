import time
from queue import Queue

from celery import group
from praw import Reddit
from prawcore import Forbidden
import webbrowser
from redditrepostsleuth.celery.tasks import save_new_post, update_cross_post_parent, save_new_comment
from redditrepostsleuth.common.logging import log
from redditrepostsleuth.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.util.objectmapping import submission_to_post


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

                            save_new_post.apply_async((post,), queue='postingest')
                    except Forbidden as e:
                        pass
            except Exception as e:
                log.exception('INGEST THREAD DIED', exc_info=True)


    def ingest_new_comments(self):
        while True:
            try:
                for comment in self.reddit.subreddit('all').stream.comments():
                    save_new_comment.apply_async((comment,), queue='commentingest')
            except Exception as e:
                log.exception('Problem in comment ingest thread', exc_info=True)