import time
from datetime import datetime, timedelta
from typing import Tuple, Text, NoReturn, Optional

from praw.exceptions import APIException
from prawcore import Forbidden
from sqlalchemy.exc import InternalError

from redditrepostsleuth.core.celery.helpers.repost_image import save_image_repost_general
from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.db.databasemodels import Summons, Post, RepostWatch, BannedUser
from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.core.services.duplicateimageservice import DuplicateImageService
from redditrepostsleuth.core.exception import NoIndexException, InvalidCommandException, InvalidImageUrlException
from redditrepostsleuth.core.logging import log
from redditrepostsleuth.core.model.commands.repost_base_cmd import RepostBaseCmd
from redditrepostsleuth.core.model.commands.repost_image_cmd import RepostImageCmd
from redditrepostsleuth.core.model.events.influxevent import InfluxEvent
from redditrepostsleuth.core.model.events.summonsevent import SummonsEvent
from redditrepostsleuth.core.model.repostresponse import SummonsResponse
from redditrepostsleuth.core.services.eventlogging import EventLogging
from redditrepostsleuth.core.services.reddit_manager import RedditManager
from redditrepostsleuth.core.services.response_handler import ResponseHandler
from redditrepostsleuth.core.services.responsebuilder import ResponseBuilder
from redditrepostsleuth.core.util.helpers import build_markdown_list, build_msg_values_from_search, create_first_seen, \
    searched_post_str, build_image_msg_values_from_search, save_link_repost
from redditrepostsleuth.core.util.objectmapping import submission_to_post
from redditrepostsleuth.core.util.replytemplates import UNSUPPORTED_POST_TYPE, IMAGE_REPOST_ALL, WATCH_ENABLED, \
    WATCH_ALREADY_ENABLED, WATCH_DISABLED_NOT_FOUND, WATCH_DISABLED, \
    SUMMONS_ALREADY_RESPONDED, BANNED_SUB_MSG, OVER_LIMIT_BAN
from redditrepostsleuth.core.util.repost_helpers import check_link_repost
from redditrepostsleuth.ingestsvc.util import pre_process_post
from redditrepostsleuth.summonssvc.commandparsing.command_parser import CommandParser


class SummonsHandler:
    def __init__(
            self,
            uowm: UnitOfWorkManager,
            image_service: DuplicateImageService,
            reddit: RedditManager,
            response_builder: ResponseBuilder,
            response_handler: ResponseHandler,
            config: Config = None,
            event_logger: EventLogging = None,
            summons_disabled=False
    ):
        self.uowm = uowm
        self.image_service = image_service
        self.reddit = reddit
        self.summons_disabled = summons_disabled
        self.response_builder = response_builder
        self.response_handler = response_handler
        self.event_logger = event_logger
        self.config = config or Config()
        self.command_parser = CommandParser(config=self.config)

    def handle_summons(self):
        """
        Continually check the summons table for new requests.  Handle them as they are found
        """
        while True:
            try:
                with self.uowm.start() as uow:
                    summons = uow.summons.get_unreplied()
                    for s in summons:
                        log.info('Starting summons %s', s.id)
                        post = uow.posts.get_by_post_id(s.post_id)
                        if not post:
                            post = self.save_unknown_post(s.post_id)

                        if not post:
                            response = SummonsResponse(summons=summons)
                            response.message = 'Sorry, I\'m having trouble with this post. Please try again later'
                            log.info('Failed to ingest post %s.  Sending error response', s.post_id)
                            self._send_response(response)
                            continue

                        self.process_summons(s, post)
                        # TODO - This sends completed summons events to influx even if they fail
                        summons_event = SummonsEvent((datetime.utcnow() - s.summons_received_at).seconds,
                                                     s.summons_received_at, s.requestor, event_type='summons')
                        self._send_event(summons_event)
                        log.info('Finished summons %s', s.id)
                time.sleep(2)
            except Exception:
                log.exception('Exception in handle summons thread', exc_info=True)

    def _get_summons_cmd(self, cmd_body: Text, post_type: Text) -> RepostBaseCmd:
        cmd_str = self._strip_summons_flags(cmd_body)
        try:
            base_command = self.command_parser.parse_root_command(cmd_str)
            if base_command == 'repost' or base_command is None:
                return self._get_repost_cmd(post_type, cmd_str)
            elif base_command == 'watch':
                return self.command_parser.parse_watch_cmd(cmd_str)
            elif base_command == 'unwatch':
                pass
            else:
                return self._get_repost_cmd(post_type, cmd_str)
        except InvalidCommandException:
            log.error('Summons has no base command.  Defaulting to repost')

        return self._get_repost_cmd(post_type, cmd_str)

    def _get_repost_cmd(self, post_type: Text, cmd_body: Text) -> RepostBaseCmd:
        if cmd_body:
            cmd_body = cmd_body.strip('repost ')
        if post_type == 'image':
            return self._get_image_repost_cmd(cmd_body)
        elif post_type == 'link':
            return self._get_link_repost_cmd(cmd_body)

    def _get_image_repost_cmd(self, cmd_body: Text) -> RepostImageCmd:
        return self.command_parser.parse_repost_image_cmd(cmd_body)

    def _get_link_repost_cmd(self, cmd_body: Text):
        return self.command_parser.parse_repost_link_cmd(cmd_body)

    def _strip_summons_flags(self, comment_body: Text) -> Optional[Text]:
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

    def process_summons(self, summons: Summons, post: Post):
        if self.summons_disabled:
            self._send_summons_disable_msg(summons)

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
            monitored_sub = uow.monitored_sub.get_by_sub(summons.subreddit)

            if monitored_sub:
                if monitored_sub.disable_summons_after_auto_response:
                    log.info('Sub %s has summons disabled after auto response', summons.subreddit)
                    auto_response = uow.bot_comment.get_by_post_id_and_type(summons.post_id, 'submonitor')
                    if auto_response:
                        self._send_already_responded_msg(summons, f'https://reddit.com{auto_response.perma_link}')
                        if monitored_sub.remove_additional_summons:
                            self._delete_mention(summons.comment_id)
                        return

                if monitored_sub.only_allow_one_summons and summons.requestor != 'barrycarey':
                    response = uow.bot_comment.get_by_post_id_and_type(summons.post_id, 'summons')
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
            log.error('Invalid command in summons: %s', summons.comment_body)
            base_command = 'repost'

        if post.post_type is None or post.post_type not in self.config.supported_post_types:
            log.error('Post %s: Type %s not support', f'https://redd.it/{post.post_id}', post.post_type)
            self._send_unsupported_msg(summons, post.post_type)
            return

        # TODO - Create command registry instead of manually defining
        if base_command == 'stats':
            pass
        elif base_command == 'watch':
            self._enable_watch(summons)
            return
        elif base_command == 'unwatch':
            self._disable_watch(summons)
            return
        elif base_command == 'repost':
            self.process_repost_request(summons, post)
            return

    def _delete_mention(self, comment_id: Text) -> NoReturn:
        log.info('Attempting to delete mention %s', comment_id)
        comment = self.reddit.comment(comment_id)
        if not comment:
            log.error('Failed to load comment %s', comment_id)
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
                post_id=summons.post_id,
                comment_id=summons.comment_id,
                source='summons'
            )
        except APIException as e:
            if e.error_type == 'NOT_WHITELISTED_BY_USER_MESSAGE':
                response.message = 'NOT_WHITELISTED_BY_USER_MESSAGE'
        self._save_response(response)

    def _send_unsupported_msg(self, summons: Summons, post_type: Text):
        response = SummonsResponse(summons=summons)
        response.status = 'error'
        response.message = UNSUPPORTED_POST_TYPE.format(post_type=post_type)
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
            existing_watch = uow.repostwatch.find_existing_watch(summons.requestor, summons.post_id)
            if not existing_watch or (existing_watch and not existing_watch.enabled):
                response.message = WATCH_DISABLED_NOT_FOUND
                self._send_response(response)
                return
            existing_watch.enabled = False
            try:
                uow.commit()
                response.message = WATCH_DISABLED
                log.info('Disabled watch for post %s for user %s', summons.post_id, summons.requestor)
            except Exception as e:
                log.exception('Failed to disable watch %s', existing_watch.id, exc_info=True)
                response.message = 'An error prevented me from removing your watch on this post.  Please try again'
            self._send_response(response)

    def _enable_watch(self, summons: Summons) -> NoReturn:

        cmd = self._get_summons_cmd(summons.comment_body, '')
        response = SummonsResponse(summons=summons)
        with self.uowm.start() as uow:
            existing_watch = uow.repostwatch.find_existing_watch(summons.requestor, summons.post_id)
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
            post_id=summons.post_id,
            user=summons.requestor,
            expire_after=cmd.expire,
            same_sub=cmd.same_sub,
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

    def process_repost_request(self, summons: Summons, post: Post):
        if post.post_type == 'image':
            self.process_image_repost_request(summons, post)
        elif post.post_type == 'link':
            self.process_link_repost_request(summons, post)

    def process_link_repost_request(self, summons: Summons, post: Post):
        response = SummonsResponse(summons=summons)
        cmd = self._get_repost_cmd(post.post_type, summons.comment_body)
        search_results = check_link_repost(post, self.uowm, get_total=True)
        msg_values = build_msg_values_from_search(search_results, self.uowm)

        if not search_results.matches:
            response.message = self.response_builder.build_default_oc_comment(msg_values, post.post_type)
        else:
            save_link_repost(post, search_results.matches[0].post, self.uowm, 'summons')
        # TODO - Move this to message builder
            if cmd.all_matches:
                response.message = IMAGE_REPOST_ALL.format(
                    count=len(search_results.matches),
                    searched_posts=searched_post_str(post, search_results.index_size),
                    firstseen=create_first_seen(search_results.matches[0].post, summons.subreddit),
                    time=search_results.total_search_time

                )
                response.message = response.message + build_markdown_list(search_results.matches)
                if len(search_results.matches) > 4:
                    log.info('Sending check all results via PM with %s matches', len(search_results.matches))
                    comment = self.reddit.comment(summons.comment_id)
                    self.response_handler.send_private_message(
                        comment.author,
                        response.message,
                        post_id=summons.post_id,
                        comment_id=summons.comment_id,
                        source='summons'
                    )
                    response.message = f'I found {len(search_results.matches)} matches.  ' \
                                       f'I\'m sending them to you via PM to reduce comment spam'

                response.message = response.message
            else:
                response.message = self.response_builder.build_sub_repost_comment(post.subreddit, msg_values, post.post_type)

        self._send_response(response)

    def process_image_repost_request(self, summons: Summons, post: Post):

        with self.uowm.start() as uow:
            monitored_sub = uow.monitored_sub.get_by_sub(summons.subreddit)


        cmd = self._get_summons_cmd(summons.comment_body, post.post_type)
        response = SummonsResponse(summons=summons)

        target_image_match, target_meme_match, target_annoy_distance = self._get_target_distances(
            post.subreddit,
            override_target_match_percent=cmd.strictness
        )

        try:
            search_results = self.image_service.check_image(
                post.url,
                post=post,
                target_annoy_distance=target_annoy_distance,
                target_match_percent=target_image_match,
                target_meme_match_percent=target_meme_match,
                meme_filter=monitored_sub.meme_filter if monitored_sub else cmd.meme_filter,
                same_sub=monitored_sub.same_sub_only if monitored_sub else cmd.same_sub,
                date_cutoff=monitored_sub.target_days_old if monitored_sub else cmd.match_age,
                max_matches=250,
                max_depth=-1,
                source='summons'
            )
        except NoIndexException:
            log.error('No available index for image repost check.  Trying again later')
            time.sleep(10)
            return

        msg_values = build_msg_values_from_search(search_results, self.uowm)
        msg_values = build_image_msg_values_from_search(search_results, self.uowm, **msg_values)

        if not search_results.matches:
            response.message = self.response_builder.build_default_oc_comment(msg_values, post.post_type)
        else:
            save_image_repost_general(search_results, self.uowm, 'summons')
            # TODO - Move this to message builder
            if cmd.all_matches:
                response.message = IMAGE_REPOST_ALL.format(
                    count=len(search_results.matches),
                    searched_posts=searched_post_str(post, search_results.total_searched),
                    firstseen=create_first_seen(search_results.matches[0].post, summons.subreddit),
                    time=search_results.total_search_time

                )
                response.message = response.message + build_markdown_list(search_results.matches)
                if len(search_results.matches) > 4:
                    log.info('Sending check all results via PM with %s matches', len(search_results.matches))
                    comment = self.reddit.comment(summons.comment_id)
                    self.response_handler.send_private_message(
                        comment.author,
                        response.message,
                        post_id=summons.post_id,
                        comment_id=summons.comment_id,
                        source='summons'
                    )
                    response.message = f'I found {len(search_results.matches)} matches.  ' \
                                       f'I\'m sending them to you via PM to reduce comment spam'

                response.message = response.message
            else:

                response.message = self.response_builder.build_sub_repost_comment(
                    post.subreddit, msg_values,
                    post.post_type
                )

        self._send_response(response)

    def _get_target_distances(self, subreddit: str, override_target_match_percent: int = None) -> Tuple[int, int, float]:
        """
        Check if the post we were summoned on is in a monitored sub.  If it is get the target distances for that sub
        :rtype: Tuple[int,float]
        :param subreddit: Subreddit name
        :return: Tuple with target hamming and annoy
        """
        target_match_percent = None
        target_meme_match_percent = None
        target_annoy_distance = None
        with self.uowm.start() as uow:
            monitored_sub = uow.monitored_sub.get_by_sub(subreddit)
            if monitored_sub:
                target_match_percent = override_target_match_percent or monitored_sub.target_image_match
                target_meme_match_percent = monitored_sub.target_image_meme_match
                target_annoy_distance = monitored_sub.target_annoy
                return target_match_percent, target_meme_match_percent, target_annoy_distance
            return override_target_match_percent or self.config.target_image_match, self.config.target_image_meme_match, self.config.default_annoy_distance

    def _send_response(self, response: SummonsResponse) -> NoReturn:
        """
        Take a response object and send a response to the summons.  If we're banned on the sub send a PM instead
        :param response: SummonsResponse Object
        """

        with self.uowm.start() as uow:
            banned = uow.banned_subreddit.get_by_subreddit(response.summons.subreddit)
        if banned or (self.config.summons_send_pm_subs and response.summons.subreddit in self.config.summons_send_pm_subs):
            try:
                self._send_private_message(response)
            except APIException as e:
                if e.error_type == 'NOT_WHITELISTED_BY_USER_MESSAGE':
                    response.message = 'NOT_WHITELISTED_BY_USER_MESSAGE'
        else:
            try:
                self._reply_to_comment(response)
            except Forbidden:
                log.info('Banned on %s, sending PM', response.summons.subreddit)
                self._send_private_message(response)
        self._save_response(response)

    def _reply_to_comment(self, response: SummonsResponse) -> SummonsResponse:
        log.debug('Sending response to summons comment %s. MESSAGE: %s', response.summons.comment_id, response.message)
        try:
            reply_comment = self.response_handler.reply_to_comment(response.summons.comment_id, response.message)
            response.comment_reply_id = reply_comment.id
        except APIException as e:
            if e.error_type == 'DELETED_COMMENT':
                log.debug('Comment %s has been deleted', response.summons.comment_id)
                response.message = 'DELETED COMMENT'
            elif e.error_type == 'THREAD_LOCKED':
                log.info('Comment %s is in a locked thread', response.summons.comment_id)
                response.message = 'THREAD LOCKED'
            elif e.error_type == 'TOO_OLD':
                log.info('Comment %s is too old to reply to', response.summons.comment_id)
                response.message = 'TOO OLD'
            elif e.error_type == 'RATELIMIT':
                log.exception('PRAW Ratelimit exception', exc_info=False)
                raise
            else:
                log.exception('APIException without error_type', exc_info=True)
                raise
        except Exception:
            log.exception('Problem leaving response', exc_info=True)
            raise

        return response

    def _send_private_message(self, response: SummonsResponse) -> SummonsResponse:
        redditor = self.reddit.redditor(response.summons.requestor)
        log.info('Sending private message to %s for summons in sub %s', response.summons.requestor, response.summons.subreddit)
        msg = BANNED_SUB_MSG.format(post_id=response.summons.post_id, subreddit=response.summons.subreddit)
        msg = msg + response.message
        self.response_handler.send_private_message(
            redditor,
            msg,
            post_id=response.summons.post_id,
            comment_id=response.summons.comment_id,
            source='summons'
        )
        response.message = msg
        return response

    def _save_response(self, response: SummonsResponse):
        with self.uowm.start() as uow:
            summons = uow.summons.get_by_id(response.summons.id)
            if summons:
                summons.comment_reply = response.message
                summons.summons_replied_at = datetime.utcnow()
                summons.comment_reply_id = response.comment_reply_id
                try:
                    uow.commit()
                    log.debug('Committed summons response to database')
                except InternalError:
                    log.exception('Failed to save response to summons', exc_info=True)

    def _save_post(self, post: Post):
        with self.uowm.start() as uow:
            uow.posts.update(post)
            uow.commit()

    def save_unknown_post(self, post_id: Text) -> Optional[Post]:
        """
        If we received a request on a post we haven't ingest save it
        :rtype: Optional[Post]
        :param post_id: Submission ID
        :return: Post object
        """
        submission = self.reddit.submission(post_id)
        try:
            post = pre_process_post(submission_to_post(submission), self.uowm, None)
        except InvalidImageUrlException:
            return
        except Forbidden:
            log.error('Failed to download post %s, appears we are banned', post_id)
            return

        if not post or post.post_type != 'image':
            log.error('Problem ingesting post.  Either failed to save or it is not an image')
            return

        return post

    def _send_event(self, event: InfluxEvent):
        if self.event_logger:
            self.event_logger.save_event(event)

    def _send_ban_notification(self, summons: Summons) -> NoReturn:
        response = SummonsResponse(summons=summons)
        response.status = 'success'
        response.message = OVER_LIMIT_BAN.format(ban_expires=datetime.utcnow() + timedelta(hours=1))
        redditor = self.reddit.redditor(summons.requestor)
        self.response_handler.send_private_message(redditor, response.message, subject='Temporary RepostSleuth Ban')
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
