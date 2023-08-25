import logging
import time
from datetime import datetime, timedelta
from typing import Tuple, Text, NoReturn, Optional

from praw import Reddit
from praw.exceptions import APIException
from prawcore import Forbidden
from sqlalchemy.exc import InternalError

from redditrepostsleuth.core.celery.task_logic.repost_image import save_image_repost_result
from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.db.databasemodels import Summons, RepostWatch, BannedUser, MonitoredSub
from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.core.exception import NoIndexException, InvalidCommandException
from redditrepostsleuth.core.model.events.influxevent import InfluxEvent
from redditrepostsleuth.core.model.repostresponse import SummonsResponse
from redditrepostsleuth.core.notification.notification_service import NotificationService
from redditrepostsleuth.core.services.duplicateimageservice import DuplicateImageService
from redditrepostsleuth.core.services.eventlogging import EventLogging
from redditrepostsleuth.core.services.response_handler import ResponseHandler
from redditrepostsleuth.core.services.responsebuilder import ResponseBuilder
from redditrepostsleuth.core.util.helpers import save_link_repost, get_default_image_search_settings, \
    get_default_link_search_settings
from redditrepostsleuth.core.util.replytemplates import UNSUPPORTED_POST_TYPE, WATCH_ENABLED, \
    WATCH_ALREADY_ENABLED, WATCH_DISABLED_NOT_FOUND, WATCH_DISABLED, \
    SUMMONS_ALREADY_RESPONDED, BANNED_SUB_MSG, OVER_LIMIT_BAN
from redditrepostsleuth.core.util.repost_helpers import get_link_reposts, filter_search_results
from redditrepostsleuth.summonssvc.commandparsing.command_parser import CommandParser

log = logging.getLogger(__name__)

class SummonsHandler:
    def __init__(
            self,
            uowm: UnitOfWorkManager,
            image_service: DuplicateImageService,
            reddit: Reddit,
            response_builder: ResponseBuilder,
            response_handler: ResponseHandler,
            config: Config = None,
            event_logger: EventLogging = None,
            notification_svc: NotificationService = None,
            summons_disabled=False
    ):
        self.notification_svc = notification_svc
        self.uowm = uowm
        self.image_service = image_service
        self.reddit = reddit
        self.summons_disabled = summons_disabled
        self.response_builder = response_builder
        self.response_handler = response_handler
        self.event_logger = event_logger
        self.config = config or Config()
        self.command_parser = CommandParser(config=self.config)


    @staticmethod
    def _strip_summons_flags(comment_body: Text) -> Optional[Text]:
        """
        Take the body of a comment where the bot is tagged and remove the tag
        :rtype: Optional[Text]
        :param comment_body: Body of comment
        :return: The remainder of comment without the tag
        """
        log.debug('Attempting to parse summons comment')
        log.debug(comment_body)
        user_tag = comment_body.lower().find('repostsleuthbot')
        keyword_tag = comment_body.lower().find('?repost')
        if user_tag > 1:
            # TODO - Possibly return none if len > 100
            return comment_body[user_tag + 15:].strip()
        elif keyword_tag >= 0:
            return comment_body[keyword_tag + 7:].strip()
        else:
            log.error('Unable to find summons tag in: %s', comment_body)
            return

    def process_summons(self, summons: Summons):
        if self.summons_disabled:
            self._send_summons_disable_msg(summons)

        if summons.post.post_type.name is None or summons.post.post_type.name not in self.config.supported_post_types:
            log.warning('Post %s: Type %s not supported', f'https://redd.it/{summons.post.post_id}', summons.post.post_type.name)
            self._send_unsupported_msg(summons)
            return

        if self._is_banned(summons.requestor):
            log.info('User %s is currently banned', summons.requestor)
            response = SummonsResponse(summons=summons, message='USER BANNED')
            self._save_response(response)
            return

        if self._has_user_exceeded_limit(summons.requestor):
            self._ban_user(summons.requestor)
            self._send_ban_notification(summons)
            return

        with self.uowm.start() as uow:
            monitored_sub = uow.monitored_sub.get_by_sub(summons.post.subreddit)
            if monitored_sub:
                if monitored_sub.disable_summons_after_auto_response:
                    log.info('Sub %s has summons disabled after auto response', summons.post.subreddit)
                    auto_response = uow.bot_comment.get_by_post_id_and_type(summons.post.id, 'submonitor')
                    if auto_response:
                        self._send_already_responded_msg(summons, f'https://reddit.com{auto_response.perma_link}')
                        if monitored_sub.remove_additional_summons:
                            self._delete_mention(summons.comment_id)
                        return

                if monitored_sub.only_allow_one_summons and summons.requestor != 'barrycarey':
                    response = uow.bot_comment.get_by_post_id_and_type(summons.post.id, 'summons')
                    if response:
                        log.info('Sub %s only allows one summons.  Existing response found at %s',
                                 summons.subreddit, response.perma_link)
                        self._send_already_responded_msg(summons, f'https://reddit.com{response.perma_link}')
                        if monitored_sub.remove_additional_summons:
                            self._delete_mention(summons.comment_id)
                        return

        stripped_comment = self._strip_summons_flags(summons.comment_body)
        try:
            if not stripped_comment:
                base_command = 'repost'
            else:
                base_command = self.command_parser.parse_root_command(stripped_comment)
        except InvalidCommandException:
            log.warning('Invalid command. Body=%s', summons.comment_body)
            base_command = 'repost'

        if base_command == 'watch':
            self._enable_watch(summons)
            return
        elif base_command == 'unwatch':
            self._disable_watch(summons)
            return
        else:
            self.process_repost_request(summons, monitored_sub=monitored_sub)
            return

    def _delete_mention(self, comment_id: Text) -> NoReturn:
        log.info('Attempting to delete mention %s', comment_id)
        comment = self.reddit.comment(comment_id)
        if not comment:
            log.warning('Failed to load comment %s', comment_id)
            return
        try:
            comment.mod.remove()
            log.info('Removed mention %s', comment_id)
        except Exception as e:
            log.exception('Failed to delete comment %s', comment_id, exc_info=True)
            return

    def _send_already_responded_msg(self, summons: Summons, perma_link: Text) -> NoReturn:
        response = SummonsResponse(summons=summons)
        response.status = 'success'
        response.message = SUMMONS_ALREADY_RESPONDED.format(perma_link=perma_link)
        redditor = self.reddit.redditor(summons.requestor)
        try:
            self.response_handler.send_private_message(
                redditor,
                response.message,
                'Repost Check',
                'summons',
                comment_id=summons.comment_id,
            )
        except APIException as e:
            if e.error_type == 'NOT_WHITELISTED_BY_USER_MESSAGE':
                response.message = 'NOT_WHITELISTED_BY_USER_MESSAGE'
        self._save_response(response)

    def _send_unsupported_msg(self, summons: Summons):
        response = SummonsResponse(summons=summons)
        response.status = 'error'
        response.message = UNSUPPORTED_POST_TYPE.format(post_type=summons.post.post_type.name)
        self._send_response(response)

    def _send_summons_disable_msg(self, summons: Summons):
        response = SummonsResponse(summons=summons)
        log.info('Sending summons disabled message')
        response.message = 'I\'m currently down for maintenance, check back in an hour'
        self._send_response(response)
        return

    def _disable_watch(self, summons: Summons) -> NoReturn:
        response = SummonsResponse(summons=summons)
        with self.uowm.start() as uow:
            existing_watch = uow.repostwatch.find_existing_watch(summons.requestor, summons.post.id)
            if not existing_watch or (existing_watch and not existing_watch.enabled):
                response.message = WATCH_DISABLED_NOT_FOUND
                self._send_response(response)
                return
            existing_watch.enabled = False
            try:
                uow.commit()
                response.message = WATCH_DISABLED
                log.info('Disabled watch for user %s', summons.requestor)
            except Exception as e:
                log.exception('Failed to disable watch %s', existing_watch.id, exc_info=True)
                response.message = 'An error prevented me from removing your watch on this post.  Please try again'
            self._send_response(response)

    def _enable_watch(self, summons: Summons) -> NoReturn:

        response = SummonsResponse(summons=summons)
        with self.uowm.start() as uow:
            existing_watch = uow.repostwatch.find_existing_watch(summons.requestor, summons.post.id)
            if existing_watch:
                if not existing_watch.enabled:
                    log.info('Found existing watch that is disabled.  Enabling watch %s', existing_watch.id)
                    existing_watch.enabled = True
                    response.message = WATCH_ENABLED
                    uow.commit()
                    self._send_response(response)
                    return
                else:
                    response.message = WATCH_ALREADY_ENABLED
                    self._send_response(response)
                    return

        repost_watch = RepostWatch(
            post_id=summons.post.id,
            user=summons.requestor,
            enabled=True
        )

        with self.uowm.start() as uow:
            uow.repostwatch.add(repost_watch)
            try:
                uow.commit()
                response.message = WATCH_ENABLED
            except Exception as e:
                log.exception('Failed save repost watch', exc_info=True)
                response.message = 'An error prevented me from creating a watch on this post.  Please try again'

        self._send_response(response)

    def process_repost_request(self, summons: Summons, monitored_sub: MonitoredSub = None):
        if summons.post.post_type.name == 'image':
            self.process_image_repost_request(summons, monitored_sub=monitored_sub)
        elif summons.post.post_type.name == 'link':
            self.process_link_repost_request(summons)

    def process_link_repost_request(self, summons: Summons, monitored_sub: MonitoredSub = None):
        response = SummonsResponse(summons=summons)

        search_results = get_link_reposts(
            summons.post.url,
            self.uowm,
            get_default_link_search_settings(self.config),
            post=summons.post,
            get_total=True
        )
        search_results = filter_search_results(
            search_results,
            reddit=self.reddit,
            uitl_api=f'{self.config.util_api}/maintenance/removed'
        )

        if not monitored_sub:
            response.message = self.response_builder.build_default_comment(search_results, signature=False)
        else:
            response.message = self.response_builder.build_sub_comment(monitored_sub, search_results, signature=False)

        if search_results.matches:
            save_link_repost(search_results.checked_post, search_results.matches[0].post, self.uowm, 'summons')

        self._send_response(response)

    def process_image_repost_request(self, summons: Summons, monitored_sub: MonitoredSub = None):

        response = SummonsResponse(summons=summons)
        # TODO - THis doesn't honor monitored sub settings
        search_settings = get_default_image_search_settings(self.config)
        target_image_match, target_meme_match, target_annoy_distance = self._get_target_distances(
            monitored_sub
        )
        search_settings.target_match_percent = target_image_match
        search_settings.target_meme_match_percent = target_meme_match

        try:
            search_results = self.image_service.check_image(
                summons.post.url,
                post=summons.post,
                search_settings=search_settings,
                source='summons'
            )
        except NoIndexException:
            log.error('No available index for image repost check.  Trying again later')
            time.sleep(10)
            return

        if monitored_sub:
            response.message = self.response_builder.build_sub_comment(monitored_sub, search_results, signature=False)
        else:
            response.message = self.response_builder.build_default_comment(search_results, signature=False)

        if search_results.matches:
            save_image_repost_result(search_results, self.uowm, source='summons')

        self._send_response(response)

    def _get_target_distances(self, monitored_sub: MonitoredSub) -> Tuple[int, int, float]:
        """
        Check if the post we were summoned on is in a monitored sub.  If it is get the target distances for that sub
        :rtype: Tuple[int,float]
        :param monitored_sub: Subreddit name
        :return: Tuple with target hamming and annoy
        """
        if monitored_sub:
            target_match_percent = monitored_sub.target_image_match
            target_meme_match_percent = monitored_sub.target_image_meme_match
            target_annoy_distance = monitored_sub.target_annoy
            return target_match_percent, target_meme_match_percent, target_annoy_distance
        return self.config.default_image_target_match, self.config.default_image_target_meme_match, self.config.default_image_target_annoy_distance

    def _send_response(self, response: SummonsResponse) -> NoReturn:
        """
        Take a response object and send a response to the summons.  If we're banned on the sub send a PM instead
        :param response: SummonsResponse Object
        """

        with self.uowm.start() as uow:
            banned = uow.banned_subreddit.get_by_subreddit(response.summons.post.subreddit)
        if banned:
            try:
                self._send_private_message(response)
            except APIException as e:
                if e.error_type == 'NOT_WHITELISTED_BY_USER_MESSAGE':
                    response.message = 'NOT_WHITELISTED_BY_USER_MESSAGE'
        else:
            try:
                self._reply_to_comment(response)
            except Forbidden:
                log.info('Banned on %s, sending PM', response.summons.post.subreddit)
                self._send_private_message(response)
        self._save_response(response)

    def _reply_to_comment(self, response: SummonsResponse) -> SummonsResponse:
        log.debug('Sending response to summons comment %s. MESSAGE: %s', response.summons.comment_id, response.message)
        try:
            reply_comment = self.response_handler.reply_to_comment(response.summons.comment_id, response.message, 'summons',
                                                                   subreddit=response.summons.post.subreddit)
            if reply_comment:
                response.comment_reply_id = reply_comment.id
        except APIException as e:
            if e.error_type == 'DELETED_COMMENT':
                log.debug('Comment %s has been deleted', response.summons.comment_id)
                response.reply_failure_reason = 'DELETED COMMENT'
            elif e.error_type == 'THREAD_LOCKED':
                log.info('Comment %s is in a locked thread', response.summons.comment_id)
                response.reply_failure_reason = 'THREAD LOCKED'
            elif e.error_type == 'TOO_OLD':
                log.info('Comment %s is too old to reply to', response.summons.comment_id)
                response.reply_failure_reason = 'TOO OLD'
            elif e.error_type == 'RATELIMIT':
                log.exception('PRAW Ratelimit exception', exc_info=False)
                raise
            else:
                log.exception('APIException without error_type', exc_info=True)
                raise
        except Forbidden:
            raise
        except Exception:
            log.exception('Problem leaving response', exc_info=True)
            raise

        return response

    def _send_private_message(self, response: SummonsResponse) -> SummonsResponse:
        redditor = self.reddit.redditor(response.summons.requestor)
        log.info('Sending private message to %s', response.summons.requestor)
        msg = BANNED_SUB_MSG.format(post_id=response.summons.post.post_id, subreddit=response.summons.post.subreddit)
        msg = msg + response.message
        reply_pm = self.response_handler.send_private_message(
            redditor,
            msg,
            'Repost Check',
            'summons',
            comment_id=response.summons.comment_id,
        )
        response.message = msg
        if reply_pm:
            response.pm_reply_id = reply_pm.id
        return response

    def _save_response(self, response: SummonsResponse):
        with self.uowm.start() as uow:
            summons = uow.summons.get_by_id(response.summons.id)
            if summons:
                summons.reply_comment_id = response.comment_reply_id,
                summons.reply_pm_id = response.pm_reply_id
                summons.reply_failure_reason = response.reply_failure_reason
                summons.summons_replied_at = datetime.utcnow()
                try:
                    uow.commit()
                    log.debug('Committed summons response to database')
                except InternalError:
                    log.exception('Failed to save response to summons', exc_info=True)

    def _send_event(self, event: InfluxEvent):
        if self.event_logger:
            self.event_logger.save_event(event)

    def _send_ban_notification(self, summons: Summons) -> NoReturn:
        response = SummonsResponse(summons=summons)
        response.status = 'success'
        response.message = OVER_LIMIT_BAN.format(ban_expires=datetime.utcnow() + timedelta(hours=1))
        redditor = self.reddit.redditor(summons.requestor)
        reply_message = self.response_handler.send_private_message(redditor, response.message, 'Temporary RepostSleuth Ban', 'summons')
        self._save_response(response)

    def _ban_user(self, requestor: Text) -> NoReturn:
        ban_expires = datetime.utcnow() + timedelta(hours=1)
        log.info('Banning user %s until %s', requestor, ban_expires)
        with self.uowm.start() as uow:
            uow.banned_user.add(
                BannedUser(
                    name=requestor,
                    reason='Exceeded Summons Count',
                    expires_at=ban_expires
                )
            )
            uow.commit()

        if self.notification_svc:
            self.notification_svc.send_notification(f'User banned until {ban_expires}', subject=f'Banned {requestor}')

    def _has_user_exceeded_limit(self, requestor: Text) -> bool:
        with self.uowm.start() as uow:
            summons_last_hour = uow.summons.get_by_user_interval(requestor, 1)
            log.debug('Summons Per Hour: User - %s | Summons: %s', requestor, len(summons_last_hour))
            if len(summons_last_hour) > self.config.summons_max_per_hour:
                log.info('User %s has submitted %s summons in last hour.  Skipping this summons', requestor,
                         len(summons_last_hour))
                return True
            return False

    def _is_banned(self, requestor: Text) -> bool:
        """
        Check if a given requestor is allowed to summon the bot.  First by checking the ban list and then seeing if
        they have exceeded the summons count
        :rtype: bool
        :param requestor: Name of requestor
        :return: True/False
        """
        with self.uowm.start() as uow:
            banned = uow.banned_user.get_by_user(requestor)
        return True if banned else False
