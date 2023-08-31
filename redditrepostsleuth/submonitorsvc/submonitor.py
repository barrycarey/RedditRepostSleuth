import logging
from typing import List, Text, NoReturn, Optional

from praw.exceptions import APIException
from praw.models import Submission, Comment, Subreddit
from prawcore import Forbidden

from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.db.databasemodels import Post, MonitoredSub, MonitoredSubChecks
from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.core.model.search.image_search_results import ImageSearchResults
from redditrepostsleuth.core.model.search.search_results import SearchResults
from redditrepostsleuth.core.services.duplicateimageservice import DuplicateImageService
from redditrepostsleuth.core.services.eventlogging import EventLogging
from redditrepostsleuth.core.services.reddit_manager import RedditManager
from redditrepostsleuth.core.services.response_handler import ResponseHandler
from redditrepostsleuth.core.services.responsebuilder import ResponseBuilder
from redditrepostsleuth.core.util.helpers import build_msg_values_from_search, build_image_msg_values_from_search, \
    get_image_search_settings_for_monitored_sub, get_link_search_settings_for_monitored_sub, \
    get_text_search_settings_for_monitored_sub
from redditrepostsleuth.core.util.replytemplates import REPOST_MODMAIL
from redditrepostsleuth.core.util.repost.repost_helpers import filter_search_results, log_search
from redditrepostsleuth.core.util.repost.repost_search import image_search_by_post, link_search, text_search_by_post

log = logging.getLogger(__name__)


class SubMonitor:

    def __init__(
            self,
            image_service: DuplicateImageService,
            uowm: UnitOfWorkManager,
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

    def should_check_post(self, post: Post, monitored_sub: MonitoredSub, title_keyword_filter: List[Text] = None) -> bool:
        """
        Check if a given post should be checked
        :rtype: bool
        :param post: Post to check
        :param title_keyword_filter: Optional list of keywords to skip if in title
        :return: bool
        """
        if post.post_type.name not in self.config.supported_post_types:
            return False

        if post.post_type.name == 'image' and not monitored_sub.check_image_posts:
            return False

        if post.post_type.name == 'link' and not monitored_sub.check_link_posts:
            log.info('Skipping link post')
            return False

        if post.post_type.name == 'text' and not monitored_sub.check_text_posts:
            log.info('Skipping link post')
            return False

        if post.is_crosspost:
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

        if post.post_type.name == 'image':
            search_results = self._check_for_repost(post, monitored_sub)
        elif post.post_type.name == 'link':
            search_results = self._check_for_link_repost(post, monitored_sub)
        elif post.post_type.name == 'text':
            search_results = self._check_for_text_repost(post, monitored_sub)
        else:
            log.warning('Unsupported post type %s', post.post_type.name)
            return

        if not search_results.matches and not monitored_sub.comment_on_oc:
            log.debug('No matches for post %s and comment OC is disabled',
                     f'https://redd.it/{search_results.checked_post.post_id}')
            return search_results

        reply_comment = None

        if monitored_sub.comment_on_repost:
            try:
                reply_comment = self._leave_comment(search_results, monitored_sub)
            except APIException as e:
                if e.error_type == 'THREAD_LOCKED':
                    log.warning('Thread locked, unable to leave comment')
                else:
                    raise

        submission = self.reddit.submission(post.post_id)
        if not submission:
            log.warning('Failed to get submission %s for sub %s.  Cannot perform admin functions', post.post_id, post.subreddit)
            return

        if search_results.matches and self.config.live_responses:
            msg_values = build_msg_values_from_search(search_results, self.uowm,
                                                      target_days_old=monitored_sub.target_days_old)
            if search_results.checked_post.post_type.name == 'image':
                msg_values = build_image_msg_values_from_search(search_results, self.uowm, **msg_values)

            report_msg = self.response_builder.build_report_msg(monitored_sub.name, msg_values)
            self._report_submission(monitored_sub, submission, report_msg)
            self._lock_post(monitored_sub, submission)
            self._remove_post(monitored_sub, submission)
            self._send_mod_mail(monitored_sub, search_results)
        else:
            self._mark_post_as_oc(monitored_sub, submission)

        if reply_comment and self.config.live_responses:
            self._sticky_reply(monitored_sub, reply_comment)
            self._lock_comment(monitored_sub, reply_comment)
        self.create_checked_post(search_results, monitored_sub)


    def create_checked_post(self, results: SearchResults, monitored_sub: MonitoredSub):
        try:
            with self.uowm.start() as uow:
                uow.monitored_sub_checked.add(
                    MonitoredSubChecks(
                        post_id=results.checked_post.id,
                        post_type_id=results.checked_post.post_type_id,
                        monitored_sub=monitored_sub,
                        search=results.logged_search
                    )
                )
                uow.commit()
        except Exception as e:
            log.exception('Failed to create checked post for submission %s', results.checked_post.post_id, exc_info=True)


    def _check_for_text_repost(self, post, monitored_sub: MonitoredSub):
        with self.uowm.start() as uow:
            search_results = text_search_by_post(
                post,
                uow,
                get_text_search_settings_for_monitored_sub(monitored_sub),
                'sub_monitor',
                filter_function=filter_search_results
            )

            return search_results

    def _check_for_link_repost(self, post: Post, monitored_sub: MonitoredSub) -> SearchResults:
        with self.uowm.start() as uow:
            search_results = link_search(
                post.url,
                uow,
                get_link_search_settings_for_monitored_sub(monitored_sub),
        'sub_monitor',
                post=post,
                filter_function=filter_search_results
            )

        return search_results

    def _check_for_repost(self, post: Post, monitored_sub: MonitoredSub) -> ImageSearchResults:
        """
        Check if provided post is a repost
        :param post: DB Post obj
        :return: None
        """
        search_settings = get_image_search_settings_for_monitored_sub(monitored_sub,
                                                                      target_annoy_distance=self.config.default_image_target_annoy_distance)

        with self.uowm.start() as uow:
            search_results = image_search_by_post(
                post,
                uow,
                self.image_service,
                search_settings,
                'sub_monitor',
            )

        log.debug(search_results)
        return search_results

    def _sticky_reply(self, monitored_sub: MonitoredSub, comment: Comment) -> None:
        if monitored_sub.sticky_comment:
            try:
                comment.mod.distinguish(sticky=True)
                log.info('Made comment %s sticky', comment.id)
            except Forbidden:
                log.warning('Failed to sticky comment, no permissions')
            except Exception as e:
                log.exception('Failed to sticky comment', exc_info=True)

    def _lock_comment(self, monitored_sub: MonitoredSub, comment: Comment) -> None:
        if monitored_sub.lock_response_comment:
            log.info('Attempting to lock comment %s on subreddit %s', comment.id, monitored_sub.name)
            try:
                comment.mod.lock()
                log.info('Locked comment')
            except Forbidden:
                log.error('Failed to lock comment, no permission')
            except Exception as e:
                log.exception('Failed to lock comment', exc_info=True)

    def _remove_post(self, monitored_sub: MonitoredSub, submission: Submission) -> None:
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

    def _get_removal_reason_id(self, removal_reason: str, subreddit: Subreddit) -> Optional[str]:
        if not removal_reason:
            return None
        for r in subreddit.mod.removal_reasons:
            if r.title.lower() == removal_reason.lower():
                return r.id
        return None

    def _lock_post(self, monitored_sub: MonitoredSub, submission: Submission) -> None:
        if monitored_sub.lock_post:
            try:
                submission.mod.lock()
            except Forbidden:
                log.error('Failed to lock post https://redd.it/%s, no permission', submission.id)
            except Exception as e:
                log.exception('Failed to lock submission https://redd.it/%s', submission.id, exc_info=True)

    def _mark_post_as_oc(self, monitored_sub: MonitoredSub, submission: Submission) -> None:
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
        self.resposne_handler.send_mod_mail(
            monitored_sub.name,
            message_body,
            f'Repost found in r/{monitored_sub.name}',
            source='Submonitor'
        )

    def _leave_comment(self, search_results: ImageSearchResults, monitored_sub: MonitoredSub, post_db_id: int = None) -> Comment:
        message = self.response_builder.build_sub_comment(monitored_sub, search_results, signature=False)
        return self.resposne_handler.reply_to_submission(search_results.checked_post.post_id, message, 'submonitor')

