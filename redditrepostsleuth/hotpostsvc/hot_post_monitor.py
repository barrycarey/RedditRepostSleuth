import time
from typing import Text, NoReturn, Optional

from praw.exceptions import APIException
from praw.models import Comment, Submission

from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.db.databasemodels import Post, BotComment
from redditrepostsleuth.core.db.db_utils import get_db_engine
from redditrepostsleuth.core.db.uow.sqlalchemyunitofworkmanager import SqlAlchemyUnitOfWorkManager
from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.core.exception import NoIndexException
from redditrepostsleuth.core.logging import log
from redditrepostsleuth.core.model.search.search_results import SearchResults
from redditrepostsleuth.core.services.duplicateimageservice import DuplicateImageService
from redditrepostsleuth.core.services.eventlogging import EventLogging
from redditrepostsleuth.core.services.reddit_manager import RedditManager
from redditrepostsleuth.core.services.response_handler import ResponseHandler
from redditrepostsleuth.core.services.responsebuilder import ResponseBuilder
from redditrepostsleuth.core.util.helpers import get_default_link_search_settings
from redditrepostsleuth.core.util.reddithelpers import get_reddit_instance
from redditrepostsleuth.core.util.replytemplates import TOP_POST_WATCH_BODY, \
    TOP_POST_WATCH_SUBJECT
from redditrepostsleuth.core.util.repost_helpers import get_link_reposts, filter_search_results


class TopPostMonitor:

    def __init__(
            self,
            reddit: RedditManager,
            uowm: UnitOfWorkManager,
            image_service: DuplicateImageService,
            response_builder: ResponseBuilder,
            response_handler: ResponseHandler,
            config: Config = None,
    ):

        self.reddit = reddit
        self.uowm = uowm
        self.image_service = image_service
        self.response_builder = response_builder
        self.response_handler = response_handler
        if config:
            self.config = config
        else:
            self.config = Config()


    def monitor(self):
        while True:
            with self.uowm.start() as uow:
                submissions = [sub for sub in self.reddit.subreddit('all').top('day')]
                submissions = submissions + [sub for sub in self.reddit.subreddit('all').rising()]
                submissions = submissions + [sub for sub in self.reddit.subreddit('all').controversial('day')]
                submissions = submissions + [sub for sub in self.reddit.subreddit('all').hot()]
                for sub in submissions:
                    post = uow.posts.get_by_post_id(sub.id)
                    if not post:
                        continue

                    if post and post.left_comment:
                        continue

                    if post.crosspost_parent:
                        log.info('Skipping cross post')
                        continue

                    results = self.check_for_repost(post)
                    if not results:
                        continue
                    if not results.matches:
                        continue

                    self._add_comment(post, results)
                    if post.post_type == 'image' and len(results.matches) == 0:
                        self._offer_watch(sub)

                    time.sleep(0.2)

            log.info('Processed all top posts.  Sleeping')
            time.sleep(3600)

    def _is_banned_sub(self, subreddit: Text) -> bool:
        with self.uowm.start() as uow:
            banned = uow.banned_subreddit.get_by_subreddit(subreddit)
            if banned:
                return True
            return False

    def check_for_repost(self, post: Post) -> Optional[SearchResults]:
        """
        Take a given post and check if it's a repost
        :rtype: SearchResults
        :param post: Post obj
        :return: Search results
        """
        if post.post_type == 'image':
            try:
                return self.image_service.check_image(
                    post.url,
                    post=post,
                )
            except NoIndexException:
                log.error('No available index for image repost check.  Trying again later')
                return

        elif post.post_type == 'link':
            search_results = get_link_reposts(
                post.url,
                self.uowm,
                get_default_link_search_settings(self.config),
                post=post,
                get_total=True
            )
            return filter_search_results(
                search_results,
                reddit=self.reddit.reddit,
                uitl_api=f'{self.config.util_api}/maintenance/removed'
            )
        else:
            log.info(f'Post {post.post_id} is a {post.post_type} post.  Skipping')
            return

    def _add_comment(self, post: Post, search_results: SearchResults) -> NoReturn:
        """
        Add a comment to the post
        :rtype: NoReturn
        :param post: Post to comment on
        :param search_results: Results
        :return: NoReturn
        """

        if self._is_banned_sub(post.subreddit):
            log.info('Skipping banned sub %s', post.subreddit)
            with self.uowm.start() as uow:
                post.left_comment = True
                uow.posts.update(post)
                uow.commit()
            return

        if self._left_comment(post.post_id):
            log.info('Already left comment on %s', post.post_id)
            return

        with self.uowm.start() as uow:
            monitored_sub = uow.monitored_sub.get_by_sub(post.subreddit)
            if monitored_sub:
                log.info('Skipping monitored sub %s', post.subreddit)
                return

        msg = self.response_builder.build_default_comment(search_results)

        try:
            self.response_handler.reply_to_submission(post.post_id, msg)
        except APIException:
            log.error('Failed to leave comment on %s in %s. ', post.post_id, post.subreddit)
        except Exception:
            pass

        with self.uowm.start() as uow:
            post.left_comment = True
            uow.posts.update(post)
            uow.commit()

    def _offer_watch(self, submission: Submission) -> NoReturn:
        """
        Offer to add watch to OC post
        :param search:
        """
        if not self.config.top_post_offer_watch:
            log.debug('Top Post Offer Watch Disabled')
            return

        log.info('Offer watch to %s on post %s', submission.author.name, submission.id)

        with self.uowm.start() as uow:
            existing_response = uow.bot_private_message.get_by_user_source_and_post(
                submission.author.name,
                'toppost',
                submission.id
            )

        if existing_response:
            log.info('Already sent a message to %s', submission.author.name)
            return

        try:
            self.response_handler.send_private_message(
                submission.author,
                TOP_POST_WATCH_BODY.format(shortlink=f'https://redd.it/{submission.id}'),
                subject=TOP_POST_WATCH_SUBJECT,
                source='toppost',
                post_id=submission.id
            )
        except APIException as e:
            if e.error_type == 'NOT_WHITELISTED_BY_USER_MESSAGE':
                log.error('Not whitelisted API error')
            else:
                log.exception('Unknown error sending PM to %s', submission.author.name, exc_info=True)

    def _left_comment(self, post_id: Text) -> bool:
        """
        Check if we have already comments on a given post
        :param post_id: Post ID to check
        """
        with self.uowm.start() as uow:
            comment = uow.bot_comment.get_by_post_id_and_type(post_id=post_id, response_type='toppost')
        return True if comment else False

    def _log_comment(self, comment: Comment, post: Post):
        """
        Log reply comment to database
        :param comment:
        """
        bot_comment = BotComment(
            post_id=post.post_id,
            comment_body=comment.body,
            perma_link=comment.permalink,
            source='toppost',
            comment_id=comment.id,
            subreddit=post.subreddit
        )
        with self.uowm.start() as uow:
            uow.bot_comment.add(bot_comment)
            try:
                uow.commit()
            except Exception as e:
                log.exception('Failed to save bot comment', exc_info=True)

if __name__ == '__main__':
    config = Config()
    uowm = SqlAlchemyUnitOfWorkManager(get_db_engine(config))
    event_logger = EventLogging(config=config)
    dup = DuplicateImageService(uowm, event_logger, config=config)
    response_builder = ResponseBuilder(uowm)
    reddit_manager = RedditManager(get_reddit_instance(config))
    top = TopPostMonitor(
        reddit_manager,
        uowm,
        dup,
        response_builder,
        ResponseHandler(reddit_manager, uowm, event_logger, source='toppost', live_response=config.live_responses),
        config=config
    )
    top.monitor()