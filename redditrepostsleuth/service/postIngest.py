import time
from datetime import datetime
from queue import Queue
from typing import List

from celery import group
from praw import Reddit
from praw.models import Submission
from prawcore import Forbidden

from redditrepostsleuth.celery.tasks import save_new_post, update_cross_post_parent
from redditrepostsleuth.common.logging import log
from redditrepostsleuth.model.db.databasemodels import Post
from redditrepostsleuth.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.util import submission_to_post, submission_to_postdto


class PostIngest:
    def __init__(self, reddit: Reddit, uowm: UnitOfWorkManager) -> None:
        self.existing_posts = []
        self.reddit = reddit
        self.uowm = uowm
        self.submission_queue = Queue(maxsize=0)

    def run(self):
        sr = self.reddit.subreddit('all')
        for post in sr.stream.submissions():

            self.store_post(post)

    def ingest_new_posts(self):
        while True:
            sr = self.reddit.subreddit('all')
            try:
                while True:
                    try:
                        for submission in sr.stream.submissions():
                            self.submission_queue.put(submission)
                    except Forbidden as e:
                        pass
            except Exception as e:
                log.exception('INGEST THREAD DIED', exc_info=True)


    def _flush_submission_queue(self):
        # TODO - Not used I don't think
        """
        with self.uowm.start() as uow:
            unique_subs = [sub for sub in submissions if uow.posts.get_by_post_id(sub.id) is None]
            posts = [submission_to_post(sub) for sub in unique_subs]
            log.info('Commiting %s unique posts to database', len(unique_subs))
            uow.posts.bulk_save(posts)
            uow.commit()
        """
        while True:
            submissions = []
            try:
                while len(submissions) <= 300:
                    try:
                        submissions.append(self.submission_queue.get())
                    except Exception as e:
                        log.exception('Problem getting post from queue.', exc_info=True)
                        break

                if not submissions:
                    continue

                log.debug('Flush queue to database')
                with self.uowm.start() as uow:
                    unique_subs = [sub for sub in submissions if uow.posts.get_by_post_id(sub.id) is None]
                    posts = [submission_to_post(sub) for sub in unique_subs]
                    log.info('Commiting %s unique posts to database', len(unique_subs))
                    uow.posts.bulk_save(posts)
                    uow.commit()
            except Exception as e:
                print("")

    def _flush_submission_queue_test(self):
        """
        with self.uowm.start() as uow:
            unique_subs = [sub for sub in submissions if uow.posts.get_by_post_id(sub.id) is None]
            posts = [submission_to_post(sub) for sub in unique_subs]
            log.info('Commiting %s unique posts to database', len(unique_subs))
            uow.posts.bulk_save(posts)
            uow.commit()
        """
        while True:
            try:
                #log.debug('Ingest Queue Size: %s', self.submission_queue.qsize())
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



    def store_post(self, reddit_post: Submission):
        with self.uowm.start() as uow:
            if uow.posts.get_by_post_id(reddit_post.id):
                return
            post = Post()
            post.post_id = reddit_post.id
            post.url = reddit_post.url
            post.author = reddit_post.author.name if reddit_post.author else None
            post.created_at = datetime.fromtimestamp(reddit_post.created)
            post.subreddit = reddit_post.subreddit.display_name
            post.title = reddit_post.title
            post.perma_link = reddit_post.permalink
            if reddit_post.is_self:
                post.post_type = 'text'
            else:
                try:
                    post.post_type = reddit_post.post_hint
                except Exception as e:
                    print('Missing Post Hint')

            try:
                if hasattr(reddit_post, 'crosspost_parent'):
                    post.crosspost_parent = reddit_post.crosspost_parent
            except Exception as e:
                pass

            uow.posts.add(post)
            try:
                uow.commit()
            except Exception as e:
                print('Failed to commit')
                uow.rollback()