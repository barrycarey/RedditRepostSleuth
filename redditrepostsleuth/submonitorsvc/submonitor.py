import time
from time import perf_counter
from typing import List, Text, NoReturn, Optional

from praw.exceptions import APIException, RedditAPIException
from praw.models import Submission, Comment, Subreddit
from prawcore import Forbidden
from redlock import RedLockError

from redditrepostsleuth.core.celery.helpers.repost_image import save_image_repost_result
from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.db.databasemodels import Post, MonitoredSub, MonitoredSubChecks
from redditrepostsleuth.core.db.uow.sqlalchemyunitofworkmanager import SqlAlchemyUnitOfWorkManager
from redditrepostsleuth.core.exception import NoIndexException, RateLimitException, InvalidImageUrlException
from redditrepostsleuth.core.logging import log
from redditrepostsleuth.core.model.events.sub_monitor_event import SubMonitorEvent
from redditrepostsleuth.core.model.search.image_search_results import ImageSearchResults
from redditrepostsleuth.core.model.search.search_results import SearchResults
from redditrepostsleuth.core.services.duplicateimageservice import DuplicateImageService
from redditrepostsleuth.core.services.eventlogging import EventLogging
from redditrepostsleuth.core.services.reddit_manager import RedditManager
from redditrepostsleuth.core.services.response_handler import ResponseHandler
from redditrepostsleuth.core.services.responsebuilder import ResponseBuilder
from redditrepostsleuth.core.util.helpers import build_msg_values_from_search, build_image_msg_values_from_search, \
    save_link_repost, get_image_search_settings_for_monitored_sub, get_link_search_settings_for_monitored_sub
from redditrepostsleuth.core.util.objectmapping import submission_to_post
from redditrepostsleuth.core.util.replytemplates import REPOST_MODMAIL
from redditrepostsleuth.core.util.repost_helpers import get_link_reposts, filter_search_results
from redditrepostsleuth.ingestsvc.util import pre_process_post


class SubMonitor:

    def __init__(
            self,
            image_service: DuplicateImageService,
            uowm: SqlAlchemyUnitOfWorkManager,
            reddit: RedditManager,
            response_builder: ResponseBuilder,
            response_handler: ResponseHandler,
            event_logger: EventLogging = None,
            config: Config = None
    ):
        self.image_service = image_service
        self.uowm = uowm
        self.reddit = reddit
        self.response_builder = response_builder
        self.resposne_handler = response_handler
        self.event_logger = event_logger
        if config:
            self.config = config
        else:
            self.config = Config()

    def has_post_been_checked(self, post_id: Text) -> bool:
        """
        Check if a given post ID has been checked already
        :param post_id: ID of post to check
        """
        with self.uowm.start() as uow:
            checked = uow.monitored_sub_checked.get_by_id(post_id)
            if checked:
                return True
        return False

    def should_check_post(self, post: Post, check_image: bool, check_link: bool, title_keyword_filter: List[Text] = None) -> bool:
        """
        Check if a given post should be checked
        :rtype: bool
        :param post: Post to check
        :param title_keyword_filter: Optional list of keywords to skip if in title
        :return: bool
        """
        if post.left_comment:
            return False

        if post.post_type not in self.config.supported_post_types:
            return False

        if post.post_type == 'image' and not check_image:
            return False

        if post.post_type == 'link' and not check_link:
            log.info('Skipping link post')
            return False

        if post.crosspost_parent:
            log.debug('Skipping crosspost')
            return False

        if title_keyword_filter:
            for kw in title_keyword_filter:
                if kw in post.title.lower():
                    log.debug('Skipping post with keyword %s in title %s', kw, post.title)
                    return False

        return True

    def check_submission(self, monitored_sub: MonitoredSub, post: Post) -> Optional[SearchResults]:
        log.info('Checking %s', post.post_id)
        if post.post_type == 'image' and post.dhash_h is None:
            log.error('Post %s has no dhash', post.post_id)
            return

        try:
            if post.post_type == 'image':
                search_results = self._check_for_repost(post, monitored_sub)
            elif post.post_type == 'link':
                search_results = self._check_for_link_repost(post, monitored_sub)
                if search_results.matches:
                    # TODO - 1/12/2021 - Why are we doing this?
                    save_link_repost(post, search_results.matches[0].post, self.uowm, 'sub_monitor')
            else:
                log.error('Unsuported post type %s', post.post_type)
                return
        except NoIndexException:
            log.error('No search index available.  Cannot check post %s in %s', post.post_id, post.subreddit)
            return
        except RedLockError:
            log.error('New search index is being loaded. Cannot check post %s in %s', post.post_id, post.subreddit)
            return

        if not search_results.matches and not monitored_sub.comment_on_oc:
            log.debug('No matches for post %s and comment OC is disabled',
                     f'https://redd.it/{search_results.checked_post.post_id}')
            self._create_checked_post(post)
            return search_results

        reply_comment = None
        try:
            if monitored_sub.comment_on_repost:
                reply_comment = self._leave_comment(search_results, monitored_sub)
        except APIException as e:
            error_type = None
            if hasattr(e, 'error_type'):
                error_type = e.error_type
            log.exception('Praw API Exception.  Error Type: %s', error_type, exc_info=True)
            return
        except RateLimitException:
            time.sleep(10)
            return
        except RedditAPIException:
            log.error('Other API exception')
            return
        except Exception as e:
            log.exception('Failed to leave comment on %s in %s', post.post_id, post.subreddit)
            return

        submission = self.reddit.submission(post.post_id)
        if not submission:
            log.error('Failed to get submission %s for sub %s.  Cannot perform admin functions', post.post_id, post.subreddit)
            return

        if search_results.matches:
            msg_values = build_msg_values_from_search(search_results, self.uowm,
                                                      target_days_old=monitored_sub.target_days_old)
            if search_results.checked_post.post_type == 'image':
                msg_values = build_image_msg_values_from_search(search_results, self.uowm, **msg_values)

            report_msg = self.response_builder.build_report_msg(monitored_sub.name, msg_values)
            self._report_submission(monitored_sub, submission, report_msg)
            self._lock_post(monitored_sub, submission)
            self._remove_post(monitored_sub, submission)
            self._send_mod_mail(monitored_sub, search_results)
        else:
            self._mark_post_as_oc(monitored_sub, submission)

        if reply_comment:
            self._sticky_reply(monitored_sub, reply_comment)
            self._lock_comment(monitored_sub, reply_comment)
        self._mark_post_as_comment_left(post)
        self._create_checked_post(post)

    def _mark_post_as_comment_left(self, post: Post):
        try:
            with self.uowm.start() as uow:
                post.left_comment = True
                uow.posts.update(post)
                uow.commit()
        except Exception as e:
            log.exception('Failed to mark post %s as checked', post.id, exc_info=True)

    def _create_checked_post(self, post: Post):
        try:
            with self.uowm.start() as uow:
                uow.monitored_sub_checked.add(
                    MonitoredSubChecks(post_id=post.post_id, subreddit=post.subreddit)
                )
                uow.commit()
        except Exception as e:
            log.exception('Failed to create checked post for submission %s', post.post_id, exc_info=True)

    def _check_for_link_repost(self, post: Post, monitored_sub: MonitoredSub) -> SearchResults:
        search_results = get_link_reposts(
            post.url,
            self.uowm,
            get_link_search_settings_for_monitored_sub(monitored_sub),
            post=post,
            get_total=False
        )
        return filter_search_results(
            search_results,
            reddit=self.reddit.reddit,
            uitl_api=f'{self.config.util_api}/maintenance/removed'
        )

    def _check_for_repost(self, post: Post, monitored_sub: MonitoredSub) -> ImageSearchResults:
        """
        Check if provided post is a repost
        :param post: DB Post obj
        :return: None
        """

        search_results = self.image_service.check_image(
            post.url,
            post=post,
            source='sub_monitor',
            search_settings=get_image_search_settings_for_monitored_sub(monitored_sub,
                                                                        target_annoy_distance=self.config.default_image_target_annoy_distance)
        )
        if search_results.matches:
            save_image_repost_result(search_results ,self.uowm, source='sub_monitor')

        log.debug(search_results)
        return search_results

    def _sticky_reply(self, monitored_sub: MonitoredSub, comment: Comment) -> NoReturn:
        if monitored_sub.sticky_comment:
            try:
                comment.mod.distinguish(sticky=True)
                log.info('Made comment %s sticky', comment.id)
            except Forbidden:
                log.error('Failed to sticky comment, no permissions')
            except Exception as e:
                log.exception('Failed to sticky comment', exc_info=True)

    def _lock_comment(self, monitored_sub: MonitoredSub, comment: Comment) -> NoReturn:
        if monitored_sub.lock_response_comment:
            log.info('Attempting to lock comment %s on subreddit %s', comment.id, monitored_sub.name)
            try:
                comment.mod.lock()
                log.info('Locked comment')
            except Forbidden:
                log.error('Failed to lock comment, no permission')
            except Exception as e:
                log.exception('Failed to lock comment', exc_info=True)

    def _remove_post(self, monitored_sub: MonitoredSub, submission: Submission) -> NoReturn:
        """
        Check if given sub wants posts removed.  Remove is enabled
        @param monitored_sub: Monitored sub
        @param submission: Submission to remove
        """
        if monitored_sub.remove_repost:
            try:
                removal_reason_id = self._get_removal_reason_id(monitored_sub.removal_reason, submission.subreddit)
                log.info('Attempting to remove post %s with removal ID %s', submission.id, removal_reason_id)
                submission.mod.remove(reason_id=removal_reason_id)
            except Forbidden:
                log.error('Failed to remove post https://redd.it/%s, no permission', submission.id)
            except Exception as e:
                log.exception('Failed to remove submission https://redd.it/%s', submission.id, exc_info=True)

    def _get_removal_reason_id(self, removal_reason: Text, subreddit: Subreddit) -> Optional[Text]:
        if not removal_reason:
            return None
        for r in subreddit.mod.removal_reasons:
            if r.title.lower() == removal_reason.lower():
                return r.id
        return None

    def _lock_post(self, monitored_sub: MonitoredSub, submission: Submission) -> NoReturn:
        if monitored_sub.lock_post:
            try:
                submission.mod.lock()
            except Forbidden:
                log.error('Failed to lock post https://redd.it/%s, no permission', submission.id)
            except Exception as e:
                log.exception('Failed to lock submission https://redd.it/%s', submission.id, exc_info=True)

    def _mark_post_as_oc(self, monitored_sub: MonitoredSub, submission: Submission):
        if monitored_sub.mark_as_oc:
            try:
                submission.mod.set_original_content()
            except Forbidden:
                log.error('Failed to set post OC https://redd.it/%s, no permission', submission.id)
            except Exception as e:
                log.exception('Failed to set post OC https://redd.it/%s', submission.id, exc_info=True)


    def _report_submission(self, monitored_sub: MonitoredSub, submission: Submission, report_msg: Text) -> NoReturn:
        if not monitored_sub.report_reposts:
            return
        log.info('Reporting post %s on %s', f'https://redd.it/{submission.id}', monitored_sub.name)
        try:
            submission.report(report_msg)
        except Exception as e:
            log.exception('Failed to report submission', exc_info=True)

    def _send_mod_mail(self, monitored_sub: MonitoredSub, search_results: SearchResults) -> NoReturn:
        """
        Send a mod mail alerting to a repost
        :param monitored_sub: Monitored sub
        :param search_results: Search Results
        """
        if not monitored_sub.send_repost_modmail:
            return
        message_body = REPOST_MODMAIL.format(post_id=search_results.checked_post.post_id,
                                             match_count=len(search_results.matches))
        self.resposne_handler.send_mod_mail(monitored_sub.name, f'Repost found in r/{monitored_sub.name}', message_body,
                                            triggered_from='Submonitor')

    def _leave_comment(self, search_results: ImageSearchResults, monitored_sub: MonitoredSub) -> Comment:
        message = self.response_builder.build_sub_comment(monitored_sub, search_results, signature=False)
        return self.resposne_handler.reply_to_submission(search_results.checked_post.post_id, message)

    def save_unknown_post(self, post_id: str) -> Post:
        """
        If we received a request on a post we haven't ingest save it
        :param submission: Reddit Submission
        :return:
        """
        log.info('Post %s does not exist, attempting to ingest', post_id)
        submission = self.reddit.submission(post_id)
        post = None
        try:
            post = pre_process_post(submission_to_post(submission), self.uowm, None)
        except InvalidImageUrlException:
            log.error('Failed to ingest post %s.  URL appears to be bad', post_id)
        if not post:
            log.error('Problem ingesting post.  Either failed to save or it is not an image')
            return

        return post


    def log_run(self, process_time: float, post_count: int, subreddit: str):
        self.event_logger.save_event(
            SubMonitorEvent(
                event_type='subreddit_monitor',
                process_time=process_time,
                post_count=post_count,
                subreddit=subreddit
            )
        )

