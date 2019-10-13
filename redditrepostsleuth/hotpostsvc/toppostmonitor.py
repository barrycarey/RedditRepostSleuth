import time
from time import perf_counter

from praw import Reddit

from redditrepostsleuth.common.config.replytemplates import REPOST_MESSAGE_TEMPLATE, OC_MESSAGE_TEMPLATE
from redditrepostsleuth.common.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.common.exception import NoIndexException
from redditrepostsleuth.common.logging import log
from redditrepostsleuth.common.model.db.databasemodels import Post
from redditrepostsleuth.core.duplicateimageservice import DuplicateImageService


class TopPostMonitor:

    def __init__(self, reddit: Reddit, uowm: UnitOfWorkManager, image_service: DuplicateImageService):
        self.reddit = reddit
        self.uowm = uowm
        self.image_service = image_service


    def monitor(self):
        while True:
            with self.uowm.start() as uow:
                submissions = [sub for sub in self.reddit.subreddit('all').top('day')]
                submissions = submissions + [sub for sub in self.reddit.subreddit('all').rising()]
                submissions = submissions + [sub for sub in self.reddit.subreddit('all').controversial('day')]
                submissions = submissions + [sub for sub in self.reddit.subreddit('all').hot()]
                for sub in submissions:
                    post = uow.posts.get_by_post_id(sub.id)
                    if post and post.left_comment:
                        continue

                    if not post.dhash_h:
                        log.info('Post %s has no dhash value, skipping', post.post_id)
                        continue
                    self.check_for_repost(post)
                    time.sleep(0.2)

            log.info('Processed all top posts.  Sleeping')
            time.sleep(3600)

    def check_for_repost(self, post: Post):
        if post.post_type != 'image':
            log.info(f'Post {post.post_id} is a {post.post_type} post.  Skipping')
            return

        try:
            start = perf_counter()
            results = self.image_service.check_duplicate(post)
            search_time = perf_counter() - start
        except NoIndexException:
            log.error('No available index for image repost check.  Trying again later')
            return

        self.add_comment(post, results, round(search_time, 4))

    def add_comment(self, post: Post, search_results, search_time: float):
        log.info('Leaving comment on post %s. %s', post.post_id, post.shortlink)
        submission = self.reddit.submission(post.post_id)
        with self.uowm.start() as uow:
            newest_post = uow.posts.get_newest_post()
            if search_results:
                if search_results[0].post.shortlink:
                    original_link = search_results[0].post.shortlink
                else:
                    original_link = 'https://reddit.com' + search_results[0].post.perma_link

                msg = REPOST_MESSAGE_TEMPLATE.format(index_size=self.image_service.index.get_n_items(),
                                                     time=search_time,
                                                     total_posts=newest_post.id,
                                                     oldest=search_results[0].post.created_at,
                                                     count=len(search_results),
                                                     link_text=search_results[0].post.post_id,
                                                     original_link=original_link)
            else:
                msg = OC_MESSAGE_TEMPLATE.format(count=self.image_service.index.get_n_items(), time=search_time,
                                                  total_posts=newest_post.id)
            log.info('Leaving message %s', msg)
            try:
                submission.reply(msg)
            except Exception as e:
                log.exception('Failed to leave comment on post %s', post.post_id)
                return

            post.left_comment = True

            uow.posts.update(post)
            uow.commit()
