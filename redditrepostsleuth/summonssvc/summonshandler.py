import re
import time
from datetime import datetime

from redditrepostsleuth.core.db.databasemodels import Summons, Post
from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.core.duplicateimageservice import DuplicateImageService
from redditrepostsleuth.core.exception import NoIndexException
from redditrepostsleuth.core.logging import log
from redditrepostsleuth.core.model.comment_reply import CommentReply
from redditrepostsleuth.core.model.events.influxevent import InfluxEvent
from redditrepostsleuth.core.model.events.summonsevent import SummonsEvent
from redditrepostsleuth.core.model.repostresponse import RepostResponseBase
from redditrepostsleuth.core.responsebuilder import ResponseBuilder
from redditrepostsleuth.core.services.eventlogging import EventLogging
from redditrepostsleuth.core.services.reddit_manager import RedditManager
from redditrepostsleuth.core.services.response_handler import ResponseHandler
from redditrepostsleuth.core.util.constants import NO_LINK_SUBREDDITS
from redditrepostsleuth.core.util.helpers import build_markdown_list, build_msg_values_from_search, create_first_seen
from redditrepostsleuth.core.util.objectmapping import submission_to_post
from redditrepostsleuth.core.util.replytemplates import UNSUPPORTED_POST_TYPE, UNKNOWN_COMMAND, LINK_ALL, \
    REPOST_NO_RESULT, OC_MESSAGE_TEMPLATE, \
    IMAGE_REPOST_ALL
from redditrepostsleuth.core.util.reposthelpers import check_link_repost
from redditrepostsleuth.ingestsvc.util import pre_process_post


class SummonsHandler:
    def __init__(self, uowm: UnitOfWorkManager, image_service: DuplicateImageService, reddit: RedditManager, response_builder: ResponseBuilder, response_handler: ResponseHandler, event_logger: EventLogging = None, summons_disabled=False):
        self.uowm = uowm
        self.image_service = image_service
        self.reddit = reddit
        self.summons_disabled = summons_disabled
        self.response_builder = response_builder
        self.response_handler = response_handler
        self.event_logger = event_logger


    def handle_summons(self):
        """
        Continually check the summons table for new requests.  Handle them as they are found
        """
        while True:
            try:
                with self.uowm.start() as uow:
                    summons = uow.summons.get_unreplied()
                    for s in summons:
                        self.handle_repost_request(s)
                        summons_event = SummonsEvent((datetime.utcnow() - s.summons_received_at).seconds, s.summons_received_at, event_type='summons')
                        self._send_event(summons_event)
                time.sleep(2)
            except Exception as e:
                log.exception('Exception in handle summons thread')

    def handle_repost_request(self, summons: Summons):

        parsed_command = re.search('\?repost\s(?P<command>[^\s]+)(?P<subcommand>\s[^\s]+)?', summons.comment_body, re.IGNORECASE)

        log.info('Processing request for comment %s. Body: %s', summons.comment_id, summons.comment_body)

        with self.uowm.start() as uow:
            post = uow.posts.get_by_post_id(summons.post_id)

        response = RepostResponseBase(summons_id=summons.id)

        if not post:
            response.message = 'Sorry, an error is preventing me from checking this post.'
            self._send_response(summons.comment_id, response)
            return
            log.info('Post ID %s does not exist in database.  Attempting to ingest', summons.post_id)
            post = self.save_unknown_post(summons.post_id)
            if not post.id:
                log.exception('Failed to save unknown post %s', summons.post_id)
                response.message = 'Sorry, an error is preventing me from checking this post.'
                self._send_response(summons.comment_id, response)
                return

        # TODO - Send PM instead of comment reply
        if self.summons_disabled:
            log.info('Sending summons disabled message')
            response.message = 'Bot summons is disabled right now.  We\'re working on feedback from the launch. I\'ll be back in 48 hours'
            self._send_response(summons.comment_id, response)
            return

        if post.post_type is None or post.post_type not in ['image']:
            log.error('Submission has no post hint.  Cannot process summons')
            response.status = 'error'
            response.message = UNSUPPORTED_POST_TYPE
            self._send_response(summons.comment_id, response)
            return

        # We just got the summons flag without a command.  Default to repost check
        if not parsed_command:
            self.process_repost_request(summons, post)
            return

        sub_command = parsed_command.group('subcommand')
        if sub_command:
            sub_command = sub_command.strip()

        # TODO handle case when no command is passed
        if parsed_command.group('command').lower() == 'check':
            self.process_repost_request(summons, post, sub_command=sub_command)
        else:
            log.error('Unknown command')
            response.message = UNKNOWN_COMMAND
            self._send_response(summons.comment_id, response)


    def process_repost_request(self, summons: Summons, post: Post, sub_command: str = None):
        if post.post_type == 'image':
            self.process_image_repost_request(summons, post, sub_command=sub_command)
        elif post.post_type == 'link':
            self.process_link_repost_request(summons, post, sub_command=sub_command)

    def process_link_repost_request(self, summons: Summons, post: Post, sub_command: str = None):

        response = RepostResponseBase(summons_id=summons.id)
        with self.uowm.start() as uow:
            search_count = (uow.posts.get_newest_post()).id
            result = check_link_repost(post, self.uowm)
            if len(result.matches) > 0:
                response.message = LINK_ALL.format(occurrences=len(result.matches),
                                                   searched=search_count,
                                                   original_href='https://reddit.com' + result.matches[0].perma_link,
                                                   link_text=result.matches[0].perma_link)
            else:
                response.message = REPOST_NO_RESULT.format(total=search_count)
            self._send_response(summons.comment_id, response)

    def process_image_repost_request(self, summons: Summons, post: Post, sub_command: str = None):

        response = RepostResponseBase(summons_id=summons.id)

        try:
            search_results = self.image_service.check_duplicates_wrapped(post)
        except NoIndexException:
            log.error('No available index for image repost check.  Trying again later')
            return

        with self.uowm.start() as uow:
            newest_post = uow.posts.get_newest_post()



        if not search_results.matches:
            response.message = OC_MESSAGE_TEMPLATE.format(count=f'{search_results.index_size:,}',
                                                 time=search_results.search_time,
                                                 post_type=post.post_type,
                                                 promo='*' if post.subreddit in NO_LINK_SUBREDDITS else ' or visit r/RepostSleuthBot*'
                                                 )
        else:

            msg_values = msg_values = build_msg_values_from_search(search_results, self.uowm)

            if sub_command == 'all':
                response.message = IMAGE_REPOST_ALL.format(
                    count=len(search_results.matches),
                    searched_posts=self._searched_post_str(post, search_results.index_size),
                    firstseen=create_first_seen(search_results.matches[0].post, summons.subreddit),
                    time=search_results.search_time

                )
                response.message = response.message + build_markdown_list(search_results.matches)
                if len(search_results.matches) > 4:
                    log.info('Sending check all results via PM with %s matches', len(search_results.matches))
                    comment = self.reddit.comment(summons.comment_id)
                    self.response_handler.send_private_message(comment.author, response.message)
                    response.message = f'I found {len(search_results.matches)} matches.  I\'m sending them to you via PM to reduce comment spam'

                response.message = response.message
            else:

                response.message = self.response_builder.build_sub_repost_comment(post.subreddit, msg_values)

        self._send_response(summons.comment_id, response, no_link=post.subreddit in NO_LINK_SUBREDDITS)

    def _send_response(self, comment_id: str, response: RepostResponseBase, no_link=False):
        log.debug('Sending response to summons comment %s. MESSAGE: %s', comment_id, response.message)
        reply = self.response_handler.reply_to_comment(comment_id, response.message, source='summons', send_pm_on_fail=True)
        response.message = reply.body # TODO - I don't like this.  Make save_resposne take a CommentReply
        self._save_response(response, reply)

    def _save_response(self, response: RepostResponseBase, reply: CommentReply, subreddit: str = None):
        with self.uowm.start() as uow:
            summons = uow.summons.get_by_id(response.summons_id)
            if summons:
                summons.comment_reply = response.message
                summons.summons_replied_at = datetime.utcnow()
                summons.comment_reply_id = reply.comment.id if reply.comment else None # TODO: Hacky
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
        # TODO - Deal with case of not finding post ID.  Should be rare since this is triggered directly via a comment
        submission = self.reddit.submission(post_id)
        post = pre_process_post(submission_to_post(submission), self.uowm, None)
        with self.uowm.start() as uow:
            try:
                uow.posts.add(post)
                uow.commit()
                log.debug('Commited Post: %s', post)
            except Exception as e:
                log.exception('Problem saving new post', exc_info=True)

        return post

    def _searched_post_str(self, post: Post, count: int) -> str:
        # TODO - Move to helper. Dupped in host post
        # **Searched Images:** {index_size}
        output = '**Searched '
        if post.post_type == 'image':
            output = output + f'Images:** {count:,}'
        elif post.post_type == 'link':
            output = output + f'Links:** {count:,}'

        return output

    def _send_event(self, event: InfluxEvent):
        if self.event_logger:
            self.event_logger.save_event(event)