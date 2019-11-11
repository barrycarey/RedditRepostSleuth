import time

from praw.models import Submission, Comment
from redlock import RedLockError
from sqlalchemy.exc import IntegrityError

from redditrepostsleuth.core.services.reddit_manager import RedditManager
from redditrepostsleuth.core.services.response_handler import ResponseHandler
from redditrepostsleuth.core.util.constants import NO_LINK_SUBREDDITS
from redditrepostsleuth.core.util.replytemplates import DEFAULT_COMMENT_OC
from redditrepostsleuth.core.exception import NoIndexException
from redditrepostsleuth.core.logging import log
from redditrepostsleuth.core.db.databasemodels import Post, MonitoredSub, MonitoredSubChecks, BotComment
from redditrepostsleuth.core.model.imagerepostwrapper import ImageRepostWrapper

from redditrepostsleuth.core.util.helpers import build_msg_values_from_search
from redditrepostsleuth.core.util.objectmapping import submission_to_post
from redditrepostsleuth.core.db.uow.sqlalchemyunitofworkmanager import SqlAlchemyUnitOfWorkManager
from redditrepostsleuth.core.duplicateimageservice import DuplicateImageService
from redditrepostsleuth.core.services.responsebuilder import ResponseBuilder
from redditrepostsleuth.ingestsvc.util import pre_process_post


class SubMonitor:

    def __init__(self, image_service: DuplicateImageService, uowm: SqlAlchemyUnitOfWorkManager, reddit: RedditManager, response_builder: ResponseBuilder, response_handler: ResponseHandler):
        self.image_service = image_service
        self.uowm = uowm
        self.reddit = reddit
        self.response_builder = response_builder
        self.resposne_handler = response_handler
        self.checked_posts = []

    def run(self):
        while True:
            try:
                with self.uowm.start() as uow:
                    monitored_subs = uow.monitored_sub.get_all()
                    for sub in monitored_subs:
                        if len(self.checked_posts) > 10000:
                            self.checked_posts = []
                        if not sub.active:
                            log.debug('Sub %s is disabled', sub.name)
                            continue
                        self._check_sub(sub)
                log.info('Sleeping until next run')
                time.sleep(60)


            except Exception as e:
                log.exception('Sub monitor service crashed', exc_info=True)



    def _check_sub(self, monitored_sub: MonitoredSub):
        log.info('Checking sub %s', monitored_sub.name)
        subreddit = self.reddit.subreddit(monitored_sub.name)
        if not subreddit:
            log.error('Failed to get Subreddit %s', monitored_sub.name)
            return

        submissions = subreddit.new(limit=monitored_sub.search_depth)

        for sub in submissions:
            with self.uowm.start() as uow:
                checked = uow.monitored_sub_checked.get_by_id(sub.id)
                if checked:
                    continue
                post = uow.posts.get_by_post_id(sub.id)
                if not post:
                    log.info('Post %s has not been ingested yet.  Skipping')
                    continue

            if post.left_comment:
                continue

            if post.post_type not in ['image']:
                continue

            if not post.dhash_h:
                log.error('Post %s has no dhash. Post type %s', post.post_id, post.post_type)
                continue

            if post.crosspost_parent:
                log.debug('Skipping crosspost')
                continue

            self._check_for_repost(post, sub, monitored_sub)
            with self.uowm.start() as uow:
                uow.monitored_sub_checked.add(MonitoredSubChecks(post_id=sub.id, subreddit=post.subreddit))
                uow.commit()




    def _check_for_repost(self, post: Post, submission: Submission, monitored_sub: MonitoredSub) -> None:
        """
        Check if provided post is a repost
        :param post: DB Post obj
        :return: None
        """
        try:
            search_results = self.image_service.check_duplicates_wrapped(post,
                                                                         target_annoy_distance=monitored_sub.target_annoy,
                                                                         target_hamming_distance=monitored_sub.target_hamming,
                                                                         date_cutff=monitored_sub.target_days_old,
                                                                         same_sub=monitored_sub.same_sub_only,
                                                                         meme_filter=monitored_sub.meme_filter)
        except NoIndexException:
            log.error('No available index for image repost check.  Trying again later')
            return
        except RedLockError:
            log.error('Failed to get lock to load new index')
            return

        if not search_results.matches and monitored_sub.repost_only:
            log.info('No matches for post %s and comment OC is disabled', f'https://redd.it/{search_results.checked_post.post_id}')
            return

        self._leave_comment(search_results, submission, monitored_sub)
        #time.sleep(3)

        if search_results.matches and monitored_sub.report_submission:
            log.info('Reporting post %s on %s', f'https://redd.it/{post.post_id}', monitored_sub.name)
            try:
                submission.report(monitored_sub.report_msg)
            except Exception as e:
                log.exception('Failed to report submissioni', exc_info=True)


    def _mod_actions(self, monitored_sub: MonitoredSub, **kwargs):
        pass

    def _sticky_reply(self, monitored_sub: MonitoredSub, comment_id: str):
        pass

    def _report_submission(self, monitored_sub: MonitoredSub, submission_id: str):
        pass

    def _leave_comment(self, search_results: ImageRepostWrapper, submission: Submission, monitored_sub: MonitoredSub) -> None:

        msg_values = build_msg_values_from_search(search_results, self.uowm, target_days=monitored_sub.target_days_old)
        if search_results.matches:
            msg = self.response_builder.build_sub_repost_comment(search_results.checked_post.subreddit, msg_values,)
        else:
            msg = self.response_builder.build_sub_oc_comment(search_results.checked_post.subreddit, msg_values)

        log.info('Leaving comment in %s on post %s', search_results.checked_post.subreddit, f'https://redd.it/{search_results.checked_post.post_id}')
        log.debug('Leaving message %s', msg)

        try:
            start = time.perf_counter()
            comment = self.resposne_handler.reply_to_submission(submission.id, msg, source='submonitor')
            log.info('PRAW Comment Time %s', round(time.perf_counter() - start, 4))
            if comment:
                if monitored_sub.sticky_comment:
                    comment.mod.distinguish(sticky=True)
                    log.debug('Made comment sticky')
        except Exception as e:
            log.exception('Failed to leave comment on post %s', search_results.checked_post.post_id)
            return

        search_results.checked_post.left_comment = True
        with self.uowm.start() as uow:
            uow.posts.update(search_results.checked_post)
            uow.commit()

    def _save_unknown_post(self, submission: Submission) -> Post:
        """
        If we received a request on a post we haven't ingest save it
        :param submission: Reddit Submission
        :return:
        """
        post = submission_to_post(submission)
        try:
            post = pre_process_post(post, self.uowm, None)
        except IntegrityError as e:
            log.error('Image post already exists')

        return post
        with self.uowm.start() as uow:
            try:
                uow.posts.add(post)
                uow.commit()
                uow.posts.remove_from_session(post)
                log.debug('Commited Post: %s', post)
            except Exception as e:
                log.exception('Problem saving new post', exc_info=True)

        return post

