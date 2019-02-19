from queue import Queue

from celery import group
from praw import Reddit
from prawcore import Forbidden

from redditrepostsleuth.celery.tasks import save_new_post, update_cross_post_parent
from redditrepostsleuth.common.logging import log
from redditrepostsleuth.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.util.objectmapping import submission_to_post


class PostIngest:
    def __init__(self, reddit: Reddit, uowm: UnitOfWorkManager) -> None:
        self.existing_posts = []
        self.reddit = reddit
        self.uowm = uowm
        self.submission_queue = Queue(maxsize=0)


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

    def flush_submission_queue(self):

        while True:
            try:
                log.debug('Ingest Queue Size: %s', self.submission_queue.qsize())
                sub = self.submission_queue.get()
                save_new_post.delay(submission_to_post(sub))
            except Exception as e:
                log.exception('Problem getting post from queue.', exc_info=True)
                continue


    def check_cross_posts(self):
        """
        Due to how slow pulling cross post parent is this method runs in a thread to update them in the database
        :return:
        """
        while True:
            with self.uowm.start() as uow:
                posts = uow.posts.find_all_unchecked_crosspost(limit=10)
                jobs = [update_cross_post_parent.s(post.post_id) for post in posts]
                log.debug('Starting 200 cross post check tasks')
                job = group(jobs)
                pending_results = job.apply_async()
                pending_results.join_native()

