import logging
from typing import Optional

from praw import Reddit
from praw.exceptions import APIException
from praw.models import Submission, Comment, Subreddit
from prawcore import Forbidden

from redditrepostsleuth.core.celery.tasks.reddit_action_tasks import leave_comment_task, report_submission_task, \
    mark_as_oc_task, lock_submission_task, remove_submission_task, send_modmail_task, ban_user_task
from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.db.databasemodels import Post, MonitoredSub, MonitoredSubChecks, UserWhitelist
from redditrepostsleuth.core.db.uow.unitofwork import UnitOfWork
from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.core.model.search.image_search_results import ImageSearchResults
from redditrepostsleuth.core.model.search.search_results import SearchResults
from redditrepostsleuth.core.notification.notification_service import NotificationService
from redditrepostsleuth.core.services.duplicateimageservice import DuplicateImageService
from redditrepostsleuth.core.services.eventlogging import EventLogging
from redditrepostsleuth.core.services.response_handler import ResponseHandler
from redditrepostsleuth.core.services.responsebuilder import ResponseBuilder
from redditrepostsleuth.core.util.helpers import build_msg_values_from_search, build_image_msg_values_from_search, \
    get_image_search_settings_for_monitored_sub, get_link_search_settings_for_monitored_sub, \
    get_text_search_settings_for_monitored_sub
from redditrepostsleuth.core.util.replytemplates import REPOST_MODMAIL, NO_BAN_PERMISSIONS, HIGH_VOLUME_REPOSTER_FOUND, \
    ADULT_PROMOTER_SUBMISSION_FOUND
from redditrepostsleuth.core.util.repost.repost_helpers import filter_search_results
from redditrepostsleuth.core.util.repost.repost_search import image_search_by_post, link_search, text_search_by_post

log = logging.getLogger(__name__)


class MonitoredSubService:

    def __init__(
            self,
            image_service: DuplicateImageService,
            uowm: UnitOfWorkManager,
            reddit: Reddit,
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
        self.notification_svc = NotificationService(config)
        if config:
            self.config = config
        else:
            self.config = Config()

    def _ban_user(self, username: str, subreddit_name: str, ban_reason: str, note: str = None) -> None:
        log.info('Banning user %s from %s', username, subreddit_name)
        ban_user_task.apply_async((username, subreddit_name, ban_reason, note))

    def handle_only_fans_check(
            self,
            post: Post,
            uow: UnitOfWork,
            monitored_sub: MonitoredSub,
            whitelisted_user: UserWhitelist = None
    ):
        """
        Check if a given username has been flagged as an adult content promoter.  If it has take action per
        the monitored subreddit settings
        :param whitelisted_user: A whitelisted user to see if they should be omitted from check
        :param post: Post in question
        :param uow: database connection
        :param monitored_sub: Subreddit the post is from
        :return:
        """

        if whitelisted_user and whitelisted_user.ignore_adult_promoter_detection:
            log.info('User %s is whitelisted, skipping adult promoter check')
            return

        if not monitored_sub.adult_promoter_remove_post and not monitored_sub.adult_promoter_ban_user:
            log.debug('No adult promoter settings active, skipping check')
            return

        log.debug('Checking if user %s is flagged', post.author)
        user = uow.user_review.get_by_username(post.author)
        if not user:
            log.info('No user review record for %s', post.author)
            return

        if not user.content_links_found:
            log.info('User %s has no adult content links', post.author)
            return

        log.info('User %s is flagged as an adult promoter, taking action', user.username)
        if monitored_sub.adult_promoter_remove_post:
            if self.notification_svc:
                self.notification_svc.send_notification(
                    f'[Post](https://redd.it/{post.post_id}) by [{post.author}](https://reddit.com/u/{post.author}) removed from [r/{post.subreddit}](https://reddit.com/r/{post.subreddit})',
                    subject='Onlyfans Removal'
                )

            self._remove_submission(
                monitored_sub.adult_promoter_removal_reason,
                self.reddit.submission(post.post_id)
            )

        if monitored_sub.adult_promoter_ban_user:
            if self.notification_svc:
                self.notification_svc.send_notification(
                    f'User [{post.author}](https://reddit.com/u/{post.author}) banned from [r/{post.subreddit}](https://reddit.com/r/{post.subreddit}) for [this post](https://redd.it/{post.post_id})',
                    subject='Onlyfans Ban Issued'
                )
            self._ban_user(post.author, monitored_sub.name, monitored_sub.adult_promoter_ban_reason or user.notes)

        if monitored_sub.adult_promoter_notify_mod_mail:
            message_body = ADULT_PROMOTER_SUBMISSION_FOUND.format(
                username=post.author,
                subreddit=monitored_sub.name,
                post_id=post.post_id,
            )

            send_modmail_task.apply_async(
                (monitored_sub.name, message_body, f'New Submission From Adult Content Promoter')
            )


    def handle_high_volume_reposter_check(
            self,
            post: Post,
            uow: UnitOfWork,
            monitored_sub: MonitoredSub,
            whitelisted_user: UserWhitelist = None
    ) -> None:
        """
        Check if a submission was created by someone flagged as a high volume reposter
        :param whitelisted_user: Whitelisted user to see if we should omit check
        :param post: Submission in question
        :param uow: Database connection
        :param monitored_sub: Monitored sub the submission is from
        :return: None
        """
        if not monitored_sub.high_volume_reposter_remove_post and not monitored_sub.high_volume_reposter_ban_user and not monitored_sub.high_volume_reposter_notify_mod_mail:
            log.debug('No High Volume Repost settings enabled for %s, skipping', monitored_sub.name)
            return

        if whitelisted_user and whitelisted_user.ignore_high_volume_repost_detection:
            log.info('User %s is whitelisted, skipping high volume check', post.author)
            return

        repost_count = uow.stat_top_reposter.get_total_reposts_by_author_and_day_range(post.author, 7)

        if not repost_count:
            log.debug('User %s has no reposts, skipping high volume check', post.author)
            return

        if monitored_sub.high_volume_reposter_threshold < 10:
            log.info('High volume threshold failsafe.  Skipping check')
            return

        if repost_count < monitored_sub.high_volume_reposter_threshold:
            log.info('User %s has %s reposts which is under the threshold of %s', post.author, repost_count,
                     monitored_sub.high_volume_reposter_threshold)
            return

        if monitored_sub.high_volume_reposter_remove_post:
            if self.notification_svc:
                self.notification_svc.send_notification(
                    f'Post by [{post.author}](https://reddit.com/u/{post.author}) removed from [r/{post.subreddit}](https://reddit.com/r/{post.subreddit})',
                    subject='High Volume Removal'
                )
            self._remove_submission(
                monitored_sub.high_volume_reposter_removal_reason,
                self.reddit.submission(post.post_id),
                mod_note='High volume of reposts detected by Repost Sleuth'
            )

        if monitored_sub.high_volume_reposter_ban_user:
            if self.notification_svc:
                self.notification_svc.send_notification(
                    f'User [{post.author}](https://reddit.com/u/{post.author}) banned from [r/{post.subreddit}](https://reddit.com/r/{post.subreddit})',
                    subject='High Volume Reposter Ban Issued'
                )
            self._ban_user(
                post.author,
                monitored_sub.name,
                monitored_sub.high_volume_reposter_ban_reason or 'High volume of reposts detected by Repost Sleuth'
            )

        if monitored_sub.high_volume_reposter_notify_mod_mail:
            message_body = HIGH_VOLUME_REPOSTER_FOUND.format(
                username=post.author,
                subreddit=monitored_sub.name,
                post_id=post.post_id,
                repost_count=repost_count
            )

            send_modmail_task.apply_async(
                (monitored_sub.name, message_body, f'New Submission From High Volume Reposter')
            )

    def has_post_been_checked(self, post_id: str) -> bool:
        """
        Check if a given post ID has been checked already
        :param post_id: ID of post to check
        """
        with self.uowm.start() as uow:
            checked = uow.monitored_sub_checked.get_by_id(post_id)
            if checked:
                return True
        return False

    def should_check_post(
            self,
            post: Post,
            monitored_sub: MonitoredSub,
            whitelisted_user: UserWhitelist = None,
            title_keyword_filter: list[str] = None
    ) -> bool:
        """
        Check if a given post should be checked
        :rtype: bool
        :param post: Post to check
        :param title_keyword_filter: Optional list of keywords to skip if in title
        :return: bool
        """

        if whitelisted_user and whitelisted_user.ignore_repost_detection:
            log.debug('User %s is whitelisted on %s', post.author, post.subreddit)
            return False

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


        if monitored_sub.comment_on_repost:
            self._leave_comment(search_results, monitored_sub)

        submission = self.reddit.submission(post.post_id)

        if search_results.matches:
            msg_values = build_msg_values_from_search(search_results, self.uowm,
                                                      target_days_old=monitored_sub.target_days_old)
            if search_results.checked_post.post_type.name == 'image':
                msg_values = build_image_msg_values_from_search(search_results, self.uowm, **msg_values)

            report_msg = self.response_builder.build_report_msg(monitored_sub.name, msg_values)
            self._report_submission(monitored_sub, submission, report_msg)
            self._lock_submission(monitored_sub, submission)
            if monitored_sub.remove_repost:
                self._remove_submission(monitored_sub.removal_reason, submission)
            self._send_mod_mail(monitored_sub, search_results)
        else:
            self._mark_post_as_oc(monitored_sub, submission)

        self.create_checked_post(search_results, monitored_sub)


    def create_checked_post(self, results: SearchResults, monitored_sub: MonitoredSub):
        try:
            with self.uowm.start() as uow:
                uow.monitored_sub_checked.add(
                    MonitoredSubChecks(
                        post_id=results.checked_post.id,
                        post_type_id=results.checked_post.post_type_id,
                        monitored_sub_id=monitored_sub.id,
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


    def _remove_submission(self, removal_reason: str, submission: Submission, mod_note: str = None) -> None:
        """
        Check if given sub wants posts removed.  Remove is enabled
        @param monitored_sub: Monitored sub
        @param submission: Submission to remove
        """
        remove_submission_task.apply_async((submission, removal_reason), {'mod_note': mod_note})


    def _lock_submission(self, monitored_sub: MonitoredSub, submission: Submission) -> None:
        if monitored_sub.lock_post:
            lock_submission_task.apply_async((submission,))

    def _mark_post_as_oc(self, monitored_sub: MonitoredSub, submission: Submission) -> None:
        if monitored_sub.mark_as_oc:
            mark_as_oc_task.apply_async((submission,))


    def _report_submission(self, monitored_sub: MonitoredSub, submission: Submission, report_msg: str) -> None:
        if not monitored_sub.report_reposts:
            return
        log.info('Reporting post %s on %s', f'https://redd.it/{submission.id}', monitored_sub.name)
        report_submission_task.apply_async((submission, report_msg))

    def _send_mod_mail(self, monitored_sub: MonitoredSub, search_results: SearchResults) -> None:
        """
        Send a mod mail alerting to a repost
        :param monitored_sub: Monitored sub
        :param search_results: Search Results
        """
        if not monitored_sub.send_repost_modmail:
            return

        message_body = REPOST_MODMAIL.format(
            subreddit=monitored_sub.name,
            match_count=len(search_results.matches),
            author=search_results.checked_post.author,
            perma_link=search_results.checked_post.perma_link,
            oldest_match=search_results.matches[0].post.perma_link if search_results.matches else None,
            title=search_results.checked_post.title
        )

        send_modmail_task.apply_async((monitored_sub.name, message_body, f'Repost found in r/{monitored_sub.name}'), {'source': 'sub_monitor'})

    def _leave_comment(self, search_results: ImageSearchResults, monitored_sub: MonitoredSub) -> None:
        message = self.response_builder.build_sub_comment(monitored_sub, search_results, signature=False)
        leave_comment_task.apply_async(
            (search_results.checked_post.post_id, message),
            {'sticky_comment': monitored_sub.sticky_comment, 'lock_comment': monitored_sub.lock_response_comment}
        )


