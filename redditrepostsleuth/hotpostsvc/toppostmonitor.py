import time
from time import perf_counter

from praw import Reddit
from redlock import RedLockError

from redditrepostsleuth.common.config.constants import NO_LINK_SUBREDDITS, BANNED_SUBS
from redditrepostsleuth.common.config.replytemplates import REPOST_MESSAGE_TEMPLATE, OC_MESSAGE_TEMPLATE
from redditrepostsleuth.common.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.common.exception import NoIndexException
from redditrepostsleuth.common.logging import log
from redditrepostsleuth.common.model.db.databasemodels import Post
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
                #submissions = submissions + [sub for sub in self.reddit.subreddit('all').rising()]
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
                start = perf_counter()
                results = self.image_service.check_duplicate(post)
                search_time = perf_counter() - start
                total_searched = self.image_service.index.get_n_items()
            except NoIndexException:
                log.error('No available index for image repost check.  Trying again later')
                return
            except RedLockError:
                log.error('Could not get RedLock.  Trying again later')
                return
        elif post.post_type == 'link':
            # TODO - Deal with imgur posts marked as link
            if 'imgur' in post.url:
                log.info('Skipping imgur post marked as link')
                return
            start = perf_counter()
            results = check_link_repost(post, self.uowm).matches
            search_time = perf_counter() - start
            with self.uowm.start() as uow:
                total_searched = uow.posts.count_by_type('link')
        else:
            log.info(f'Post {post.post_id} is a {post.post_type} post.  Skipping')
            return


        self.add_comment(post, results, round(search_time, 4), total_searched)

    def add_comment(self, post: Post, search_results, search_time: float, total_search: int):

        submission = self.reddit.submission(post.post_id)
        log.info('Leaving comment on post %s. %s.  In sub %s', post.post_id, post.shortlink, submission.subreddit)
        with self.uowm.start() as uow:
            newest_post = uow.posts.get_newest_post()
            if search_results:

                msg = REPOST_MESSAGE_TEMPLATE.format(
                                                     searched_posts=self._searched_post_str(post, total_search),
                                                     post_type=post.post_type,
                                                     time=search_time,
                                                     total_posts=f'{newest_post.id:,}',
                                                     oldest=search_results[0].post.created_at,
                                                     count=len(search_results),
                                                     firstseen=self._create_first_seen(search_results[0].post),
                                                     times='times' if len(search_results) > 1 else 'time',
                                                     promo='' if post.subreddit in NO_LINK_SUBREDDITS else 'or visit r/RepostSleuthBot')
            else:
                msg = OC_MESSAGE_TEMPLATE.format(count=f'{total_search:,}',
                                                 time=search_time,
                                                 post_type=post.post_type,
                                                 promo='' if post.subreddit in NO_LINK_SUBREDDITS else 'or visit r/RepostSleuthBot'
                                                 )
            log.info('Leaving message %s', msg)
            try:
                submission.reply(msg)
            except Exception as e:
                log.exception('Failed to leave comment on post %s', post.post_id)
                return

            post.left_comment = True

            uow.posts.update(post)
            uow.commit()

    def _create_first_seen(self, post: Post) -> str:
        if post.subreddit in NO_LINK_SUBREDDITS:
            firstseen = f"First seen in {post.subreddit} on {post.created_at.strftime('%d-%m-%Y')}"
        else:
            if post.shortlink:
                original_link = post.shortlink
            else:
                original_link = 'https://reddit.com' + post.perma_link

            firstseen = f"First seen at [{post.subreddit}]({original_link}) on {post.created_at.strftime('%d-%m-%Y')}"

        log.debug('First Seen String: %s', firstseen)
        return firstseen

    def _searched_post_str(self, post: Post, count: int) -> str:
        # **Searched Images:** {index_size}
        output = '**Searched '
        if post.post_type == 'image':
            output = output + f'Images:** {count:,}'
        elif post.post_type == 'link':
            output = output + f'Links:** {count:,}'

        return output