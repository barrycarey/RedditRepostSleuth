import time
from time import perf_counter

from praw import Reddit
from redlock import RedLockError

from redditrepostsleuth.common.config import config
from redditrepostsleuth.common.config.constants import NO_LINK_SUBREDDITS, BANNED_SUBS, ONLY_COMMENT_REPOST_SUBS, \
    CUSTOM_FILTER_LEVELS
from redditrepostsleuth.common.config.replytemplates import REPOST_MESSAGE_TEMPLATE, OC_MESSAGE_TEMPLATE
from redditrepostsleuth.common.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.common.exception import NoIndexException
from redditrepostsleuth.common.logging import log
from redditrepostsleuth.common.model.db.databasemodels import Post
from redditrepostsleuth.common.util.helpers import searched_post_str, create_first_seen
from redditrepostsleuth.common.util.reposthelpers import check_link_repost
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
                #submissions = submissions + [sub for sub in self.reddit.subreddit('all').controversial('day')]
                submissions = submissions + [sub for sub in self.reddit.subreddit('all').hot()]
                for sub in submissions:
                    post = uow.posts.get_by_post_id(sub.id)
                    if not post:
                        continue

                    if post and post.left_comment:
                        continue

                    if post.subreddit.lower() in BANNED_SUBS:
                        log.info('Post %s is in a banned sub, %s.', post.post_id, post.subreddit)
                        continue

                    if post.crosspost_parent:
                        log.info('Skipping cross post')
                        continue

                    self.check_for_repost(post)
                    time.sleep(0.2)

            log.info('Processed all top posts.  Sleeping')
            time.sleep(3600)

    def check_for_repost(self, post: Post):

        if post.post_type == 'image':
            if not post.dhash_h:
                log.info('Post %s has no dhash value, skipping', post.post_id)
                return
            try:
                target_annoy = None
                target_hamming = None
                if post.subreddit in CUSTOM_FILTER_LEVELS:
                    log.info('Using custom filter values for sub %s', post.subreddit)
                    target_annoy = CUSTOM_FILTER_LEVELS.get(post.subreddit)['annoy']
                    target_hamming = CUSTOM_FILTER_LEVELS.get(post.subreddit)['hamming']
                results = self.image_service.check_duplicates_wrapped(post, target_hamming_distance=target_hamming,
                                                                      target_annoy_distance=target_annoy)
            except NoIndexException:
                log.error('No available index for image repost check.  Trying again later')
                return
            except RedLockError:
                log.error('Could not get RedLock.  Trying again later')
                return
            self.add_comment(post, results.matches, round(results.search_time, 5), results.index_size)
        elif post.post_type == 'link':
            return
            # TODO - Deal with imgur posts marked as link
            # TODO - Change link reposts to use same wrapper as image reposts
            if 'imgur' in post.url:
                log.info('Skipping imgur post marked as link')
                return
            start = perf_counter()
            results = check_link_repost(post, self.uowm).matches
            search_time = perf_counter() - start
            with self.uowm.start() as uow:
                total_searched = uow.posts.count_by_type('link')
            self.add_comment(post, results, search_time, total_searched)
        else:
            log.info(f'Post {post.post_id} is a {post.post_type} post.  Skipping')
            return




    def add_comment(self, post: Post, search_results, search_time: float, total_search: int):
        # TODO - Use new wrapper dup search method
        submission = self.reddit.submission(post.post_id)

        with self.uowm.start() as uow:
            newest_post = uow.posts.get_newest_post()
            if search_results:

                msg = REPOST_MESSAGE_TEMPLATE.format(
                                                     searched_posts=searched_post_str(post, total_search),
                                                     post_type=post.post_type,
                                                     time=search_time,
                                                     total_posts=f'{newest_post.id:,}',
                                                     oldest=search_results[0].post.created_at,
                                                     count=len(search_results),
                                                     firstseen=create_first_seen(search_results[0].post),
                                                     times='times' if len(search_results) > 1 else 'time',
                                                     promo='*' if post.subreddit in NO_LINK_SUBREDDITS else ' or visit r/RepostSleuthBot*',
                                                     percent=f'{(100 - search_results[0].hamming_distance) / 100:.2%}')
            else:
                if post.subreddit in ONLY_COMMENT_REPOST_SUBS or not config.comment_on_oc:
                    log.info('Sub %s is set to repost comment only.  Skipping OC comment', post.subreddit)
                    return

                msg = OC_MESSAGE_TEMPLATE.format(count=f'{total_search:,}',
                                                 time=search_time,
                                                 post_type=post.post_type,
                                                 promo='*' if post.subreddit in NO_LINK_SUBREDDITS else ' or visit r/RepostSleuthBot*'
                                                 )
            log.info('Leaving comment on post %s. %s.  In sub %s', post.post_id, post.shortlink, submission.subreddit)
            log.debug('Leaving message %s', msg)
            try:
                comment = submission.reply(msg)
                if comment:
                    log.info(f'https://reddit.com{comment.permalink}')
            except Exception as e:
                log.exception('Failed to leave comment on post %s', post.post_id)
                return

            post.left_comment = True

            uow.posts.update(post)
            uow.commit()
