import time
from datetime import datetime
from typing import Tuple, Text, NoReturn

from praw.exceptions import APIException
from praw.models import Redditor
from prawcore import ResponseException

from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.db.databasemodels import Summons, Post, RepostWatch
from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.core.duplicateimageservice import DuplicateImageService
from redditrepostsleuth.core.exception import NoIndexException, InvalidCommandException, InvalidImageUrlException
from redditrepostsleuth.core.logging import log
from redditrepostsleuth.core.model.commands.repost_base_cmd import RepostBaseCmd
from redditrepostsleuth.core.model.commands.repost_image_cmd import RepostImageCmd
from redditrepostsleuth.core.model.comment_reply import CommentReply
from redditrepostsleuth.core.model.events.influxevent import InfluxEvent
from redditrepostsleuth.core.model.events.summonsevent import SummonsEvent
from redditrepostsleuth.core.model.repostresponse import RepostResponseBase
from redditrepostsleuth.core.services.eventlogging import EventLogging
from redditrepostsleuth.core.services.reddit_manager import RedditManager
from redditrepostsleuth.core.services.response_handler import ResponseHandler
from redditrepostsleuth.core.services.responsebuilder import ResponseBuilder
from redditrepostsleuth.core.util.constants import NO_LINK_SUBREDDITS
from redditrepostsleuth.core.util.helpers import build_markdown_list, build_msg_values_from_search, create_first_seen, \
    searched_post_str, build_image_msg_values_from_search
from redditrepostsleuth.core.util.objectmapping import submission_to_post
from redditrepostsleuth.core.util.replytemplates import UNSUPPORTED_POST_TYPE, LINK_ALL, \
    REPOST_NO_RESULT, IMAGE_REPOST_ALL, WATCH_ENABLED, WATCH_ALREADY_ENABLED, WATCH_DISABLED_NOT_FOUND, WATCH_DISABLED, \
    SUMMONS_ALREADY_RESPONDED
from redditrepostsleuth.core.util.reposthelpers import check_link_repost
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
                            response = RepostResponseBase(summons_id=s.id)
                            response.message = 'Sorry, I\'m having trouble with this post. Please try again later'
                            log.info('Failed to ingest post %s.  Sending error response', s.post_id)
                            self._send_response(s.comment_id, response)
                            continue

                        self.process_summons(s, post)
                        # TODO - This sends completed summons events to influx even if they fail
                        summons_event = SummonsEvent((datetime.utcnow() - s.summons_received_at).seconds,
                                                     s.summons_received_at, s.requestor, event_type='summons')
                        self._send_event(summons_event)
                        log.info('Finished summons %s', s.id)
                time.sleep(2)
            except Exception as e:
                log.exception('Exception in handle summons thread')

    def _get_summons_cmd(self, cmd_body: Text, post_type: Text) -> RepostBaseCmd:
        cmd_str = self._strip_summons_flags(cmd_body)
        try:
            base_command = self.command_parser.parse_root_command(cmd_str)
            if base_command == 'repost':
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
        cmd_body = cmd_body.strip('repost ')
        if post_type == 'image':
            return self._get_image_repost_cmd(cmd_body)
        elif post_type == 'link':
            return self._get_link_repost_cmd(cmd_body)

    def _get_image_repost_cmd(self, cmd_body: Text) -> RepostImageCmd:
        return self.command_parser.parse_repost_image_cmd(cmd_body)

    def _get_link_repost_cmd(self, cmd_body: Text):
        return self.command_parser.parse_repost_link_cmd(cmd_body)

    def _strip_summons_flags(self, comment_body: Text) -> Text:
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

                if monitored_sub.only_allow_one_summons:
                    response = uow.bot_comment.get_by_post_id_and_type(summons.post_id, 'summons')
                    if response:
                        log.info('Sub %s only allows one summons.  Existing response found at %s', summons.subreddit, response.perma_link)
                        self._send_already_responded_msg(summons, f'https://reddit.com{response.perma_link}')
                        if monitored_sub.remove_additional_summons:
                            self._delete_mention(summons.comment_id)
                        return


        stripped_comment = self._strip_summons_flags(summons.comment_body)
        try:
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
        response = RepostResponseBase(summons_id=summons.id)
        response.status = 'success'
        response.message = SUMMONS_ALREADY_RESPONDED.format(perma_link=perma_link)
        redditor = self.reddit.redditor(summons.requestor)
        self.response_handler.send_private_message(redditor, response.message)
        self._save_response(response, CommentReply(body=response.message, comment=None))


    def _send_unsupported_msg(self, summons: Summons, post_type: Text):
        response = RepostResponseBase(summons_id=summons.id)
        response.status = 'error'
        response.message = UNSUPPORTED_POST_TYPE.format(post_type=post_type)
        self._send_response(summons.comment_id, response)

    def _send_summons_disable_msg(self, summons: Summons):
        # TODO - Send PM instead of comment reply
        response = RepostResponseBase(summons_id=summons.id)
        log.info('Sending summons disabled message')
        response.message = 'I\m currently down for maintenance, check back in an hour'
        self._send_response(summons.comment_id, response)
        return

    def _disable_watch(self, summons: Summons) -> NoReturn:
        response = RepostResponseBase(summons_id=summons.id)

        with self.uowm.start() as uow:
            existing_watch = uow.repostwatch.find_existing_watch(summons.requestor, summons.post_id)

            if not existing_watch or (existing_watch and not existing_watch.enabled):
                response.message = WATCH_DISABLED_NOT_FOUND
                self._send_response(summons.comment_id, response)
                return

            existing_watch.enabled = False

            try:
                uow.commit()
                response.message = WATCH_DISABLED
                log.info('Disabled watch for post %s for user %s', summons.post_id, summons.requestor)
            except Exception as e:
                log.exception('Failed to disable watch %s', existing_watch.id, exc_info=True)
                response.message = 'An error prevented me from removing your watch on this post.  Please try again'

            self._send_response(summons.comment_id, response)

    def _enable_watch(self, summons: Summons) -> NoReturn:

        cmd = self._get_summons_cmd(summons.comment_body, '')

        response = RepostResponseBase(summons_id=summons.id)

        with self.uowm.start() as uow:
            existing_watch = uow.repostwatch.find_existing_watch(summons.requestor, summons.post_id)

            if existing_watch:
                if not existing_watch.enabled:
                    log.info('Found existing watch that is disabled.  Enabling watch %s', existing_watch.id)
                    existing_watch.enabled = True
                    response.message = WATCH_ENABLED
                    uow.commit()
                    self._send_response(summons.comment_id, response)
                    return
                else:
                    response.message = WATCH_ALREADY_ENABLED
                    self._send_response(summons.comment_id, response)
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

        self._send_response(summons.comment_id, response)

    def process_repost_request(self, summons: Summons, post: Post):
        if post.post_type == 'image':
            self.process_image_repost_request(summons, post)
        elif post.post_type == 'link':
            self.process_link_repost_request(summons, post)

    def process_link_repost_request(self, summons: Summons, post: Post):

        response = RepostResponseBase(summons_id=summons.id)
        cmd = self._get_repost_cmd(post.post_type, summons.comment_body)
        search_results = check_link_repost(post, self.uowm, get_total=True)
        msg_values = build_msg_values_from_search(search_results, self.uowm)

        if not search_results.matches:
            response.message = self.response_builder.build_default_oc_comment(msg_values, post.post_type)
        else:
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
                    self.response_handler.send_private_message(comment.author, response.message)
                    response.message = f'I found {len(search_results.matches)} matches.  I\'m sending them to you via PM to reduce comment spam'

                response.message = response.message
            else:
                response.message = self.response_builder.build_sub_repost_comment(post.subreddit, msg_values, post.post_type)

        self._send_response(summons.comment_id, response)

    def process_image_repost_request(self, summons: Summons, post: Post):

        #cmd = self._get_repost_cmd(post.post_type, summons.comment_body)
        cmd = self._get_summons_cmd(summons.comment_body, post.post_type)

        response = RepostResponseBase(summons_id=summons.id)

        target_hamming_distance, target_annoy_distance = self._get_target_distances(
            post.subreddit,
            override_hamming_distance=cmd.strictness
        )

        try:
            search_results = self.image_service.check_duplicates_wrapped(
                post,
                target_annoy_distance=target_annoy_distance,
                target_hamming_distance=target_hamming_distance,
                meme_filter=cmd.meme_filter,
                same_sub=cmd.same_sub,
                date_cutoff=cmd.match_age,
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
                    self.response_handler.send_private_message(comment.author, response.message)
                    response.message = f'I found {len(search_results.matches)} matches.  I\'m sending them to you via PM to reduce comment spam'

                response.message = response.message
            else:

                response.message = self.response_builder.build_sub_repost_comment(post.subreddit, msg_values, post.post_type)

        if summons.subreddit in self.config.summons_send_pm_subs:
            self._send_private_message(summons, response)
        else:
            self._send_response(summons.comment_id, response, no_link=post.subreddit in NO_LINK_SUBREDDITS)


    def _get_target_distances(self, subreddit: str, override_hamming_distance: int = None) -> Tuple[int, float]:
        """
        Check if the post we were summoned on is in a monitored sub.  If it is get the target distances for that sub
        :rtype: Tuple[int,float]
        :param subreddit: Subreddit name
        :return: Tuple with target hamming and annoy
        """
        with self.uowm.start() as uow:
            monitored_sub = uow.monitored_sub.get_by_sub(subreddit)
            if monitored_sub:
                return override_hamming_distance or monitored_sub.target_hamming, monitored_sub.target_annoy
            return override_hamming_distance or self.config.default_hamming_distance, self.config.default_annoy_distance

    def _send_response(self, comment_id: str, response: RepostResponseBase, no_link=False):
        log.debug('Sending response to summons comment %s. MESSAGE: %s', comment_id, response.message)
        try:
            reply = self.response_handler.reply_to_comment(comment_id, response.message, send_pm_on_fail=True)
        except (APIException, AssertionError) as e:
            raise
        except Exception as e:
            pass

        if reply:
            response.message = reply.body  # TODO - I don't like this.  Make save_resposne take a CommentReply
        else:
            log.error('Failed to get reply from comment %s', comment_id)
            response.message = 'FAILED REPLY' \
                               ''
        self._save_response(response, reply)

    def _send_private_message(self, summons: Summons, response: RepostResponseBase) -> NoReturn:
        redditor = self.reddit.redditor(summons.requestor)
        log.info('Sending private message to %s for summons in sub %s', summons.requestor, summons.subreddit)
        msg = f'I\'m unable to reply to your comment at https://redd.it/{summons.post_id}.  I\'m probably banned from r/{summons.subreddit}.  Here is my response. \n\n *** \n\n'
        msg = msg + response.message
        try:
            comment_reply = CommentReply(body=None, comment=None)
            comment_reply.body = self.response_handler.send_private_message(redditor, msg)
        except Exception:
            raise
        # TODO - Shouldn't need to send response seperately
        self._save_response(response, comment_reply)

    def _save_response(self, response: RepostResponseBase, reply: CommentReply):
        with self.uowm.start() as uow:
            summons = uow.summons.get_by_id(response.summons_id)
            if summons:
                summons.comment_reply = response.message
                summons.summons_replied_at = datetime.utcnow()
                summons.comment_reply_id = reply.comment.id if reply.comment else None  # TODO: Hacky
                uow.commit()
                log.debug('Committed summons response to database')

    def _save_post(self, post: Post):
        with self.uowm.start() as uow:
            uow.posts.update(post)
            uow.commit()

    def save_unknown_post(self, post_id: str) -> Post:
        """
        If we received a request on a post we haven't ingest save it
        :param submission: Reddit Submission
        :return:
        """
        submission = self.reddit.submission(post_id)
        try:
            post = pre_process_post(submission_to_post(submission), self.uowm, None)
        except (InvalidImageUrlException):
            return

        if not post or post.post_type != 'image':
            log.error('Problem ingesting post.  Either failed to save or it is not an image')
            return

        return post

    def _send_event(self, event: InfluxEvent):
        if self.event_logger:
            self.event_logger.save_event(event)
