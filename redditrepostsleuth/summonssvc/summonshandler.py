import re
import time
from datetime import datetime

from praw import Reddit
from praw.models import Comment

from redditrepostsleuth.core.util.constants import NO_LINK_SUBREDDITS
from redditrepostsleuth.core.util.replytemplates import UNSUPPORTED_POST_TYPE, UNKNOWN_COMMAND, STATS, WATCH_NOT_OC, \
    WATCH_DUPLICATE, WATCH_ENABLED, WATCH_NOT_FOUND, WATCH_DISABLED, LINK_ALL, REPOST_NO_RESULT, OC_MESSAGE_TEMPLATE, \
    IMAGE_REPOST_ALL, FAILED_TO_LEAVE_RESPONSE
from redditrepostsleuth.core.exception import NoIndexException
from redditrepostsleuth.core.logging import log
from redditrepostsleuth.core.model.events.influxevent import InfluxEvent
from redditrepostsleuth.core.model.events.summonsevent import SummonsEvent
from redditrepostsleuth.core.model.repostresponse import RepostResponseBase
from redditrepostsleuth.core.services.eventlogging import EventLogging
from redditrepostsleuth.core.util.helpers import build_markdown_list, build_msg_values_from_search
from redditrepostsleuth.core.util.objectmapping import submission_to_post
from redditrepostsleuth.core.util.reposthelpers import verify_oc, check_link_repost
from redditrepostsleuth.core.db.databasemodels import Summons, RepostWatch, Post, BotComment
from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.core.duplicateimageservice import DuplicateImageService
from redditrepostsleuth.core.responsebuilder import ResponseBuilder
from redditrepostsleuth.ingestsvc.util import pre_process_post


class SummonsHandler:
    def __init__(self, uowm: UnitOfWorkManager, image_service: DuplicateImageService, reddit: Reddit, response_builder: ResponseBuilder, event_logger: EventLogging = None, summons_disabled=False):
        self.uowm = uowm
        self.image_service = image_service
        self.reddit = reddit
        self.summons_disabled = summons_disabled
        self.response_builder = response_builder
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
            log.info('Post ID %s does not exist in database.  Attempting to ingest', summons.post_id)
            post = self.save_unknown_post(summons.post_id)
            if not post.id:
                log.exception('Failed to save unknown post %s', summons.post_id)
                response.message = 'Sorry, an error is preventing me from checking this post.'
                self._send_response(summons.comment_id, response)
                return

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
        if parsed_command.group('command').lower() == 'watch':
            self.process_watch_request(summons, sub_command=sub_command)
        elif parsed_command.group('command').lower() == 'unwatch':
            self.process_unwatch_request(summons)
        elif parsed_command.group('command').lower() == 'stats':
            self.process_stat_request(summons)
        elif parsed_command.group('command').lower() == 'check':
            self.process_repost_request(summons, post, sub_command=sub_command)
        else:
            log.error('Unknown command')
            response.message = UNKNOWN_COMMAND
            self._send_response(summons.comment_id, response)


    def process_stat_request(self, summons: Summons):

        response = RepostResponseBase(summons_id=summons.id)
        with self.uowm.start() as uow:
            video_count = uow.posts.count_by_type('video')
            video_count += uow.posts.count_by_type('hosted:video')
            video_count += uow.posts.count_by_type('rich:video')
            image_count = uow.posts.count_by_type('image')
            text_count = uow.posts.count_by_type('text')
            link_count = uow.posts.count_by_type('link')
            summons_count = uow.summons.get_count()
            post_count = uow.posts.get_count()
            oldest_post = uow.posts.get_oldest_post()

        response.message = STATS.format(
            post_count=post_count,
            images=image_count,
            links=link_count,
            video=video_count,
            text=text_count,
            oldest=str(oldest_post.created_at),
            reposts=0,
            summoned=summons_count
        )

        self._send_response(summons.comment_id, response)

    def process_watch_request(self, summons: Summons, sub_command: str = None):
        # TODO - Add check for existing watch
        response = RepostResponseBase(summons_id=summons.id)
        comment = self.reddit.comment(id=summons.comment_id)
        submission = self.reddit.submission(id=summons.post_id)

        if not verify_oc(submission, self.image_service):
            response.message = WATCH_NOT_OC
            self._send_response(comment, response)
            return

        with self.uowm.start() as uow:
            post_count = uow.posts.count_by_type('image')

        with self.uowm.start() as uow:
            watch = uow.repostwatch.find_existing_watch(comment.author.name, summons.post_id)
            if watch:
                log.info('Found duplicate watch')
                response.message = WATCH_DUPLICATE
                self._send_response(comment, response)
                return

            watch = RepostWatch(post_id=summons.post_id, user=comment.author.name)
            watch.response_type = sub_command if sub_command else 'message'
            log.info('Creating watch request on post %s for user %s', summons.post_id, comment.author.name)
            response.message = WATCH_ENABLED.format(check_count=post_count, response=watch.response_type)

            uow.repostwatch.add(watch)
            # TODO - Probably need to catch exception here
            uow.commit()

        self._send_response(comment, response)

    def process_unwatch_request(self, summons: Summons):
        response = RepostResponseBase(summons_id=summons.id)
        comment = self.reddit.comment(id=summons.comment_id)
        with self.uowm.start() as uow:
            log.debug('Looking up existing watch for post %s from user %s', summons.post_id, comment.author.name)
            watch = uow.repostwatch.find_existing_watch(comment.author.name, summons.post_id)
            if not watch:
                log.debug('Unable to locate existing repost watch')
                response.message = WATCH_NOT_FOUND
                self._send_response(comment, response)
                return
            uow.repostwatch.remove(watch)
            uow.commit()
            response.message = WATCH_DISABLED
            self._send_response(comment, response)

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
                    firstseen=self._create_first_seen(search_results.matches[0].post),
                    time=search_results.search_time

                )
                response.message = response.message + build_markdown_list(search_results.matches)
                if len(search_results.matches) > 4:
                    log.info('Sending check all results via PM with %s matches', len(search_results.matches))
                    comment = self.reddit.comment(summons.comment_id)
                    self._send_direct_message(comment, response)
                    response.message = f'I found {len(search_results.matches)} matches.  I\'m sending them to you via PM to reduce comment spam'

                response.message = response.message
            else:

                response.message = self.response_builder.build_sub_repost_comment(post.subreddit, msg_values)

        self._send_response(summons.comment_id, response, no_link=post.subreddit in NO_LINK_SUBREDDITS)

    def _send_response(self, comment_id: str, response: RepostResponseBase, no_link=False):
        comment = self.reddit.comment(comment_id)
        if not comment.author:
            log.error('Comment has no author')
            response.message = 'NO AUTHOR ON COMMENT'
            self._save_response(response, None)
            return

        try:
            log.debug('Sending response to summons comment %s. MESSAGE: %s', comment.id, response.message)

            reply = comment.reply(response.message)
            if reply.id:
                log.debug(f'Left response at: https://reddit.com{reply.permalink}')
                self._save_response(response, reply)
                return
            log.error('Did not receive reply ID when replying to comment')
        except Exception as e:
            log.exception('Problem replying to comment', exc_info=True)

            if hasattr(e, 'error_type') and e.error_type in ['DELETED_COMMENT']:
                response.message = 'COMMENT DELETED'
            else:
                response.message = FAILED_TO_LEAVE_RESPONSE.format(
                    sub=comment.subreddit_name_prefixed) + response.message
                self._send_direct_message(comment, response)
            self._save_response(response, None)

    def _send_direct_message(self, comment: Comment, response: RepostResponseBase):
        log.info('Sending direct message to %s', comment.author.name)
        try:
            comment.author.message('Repost Check', response.message)
            self._save_response(response, None)
        except Exception as e:
            log.error('Failed to send private message to %s', comment.author.name)


    def _save_response(self, response: RepostResponseBase, reply: Comment, subreddit: str = None):
        with self.uowm.start() as uow:
            summons = uow.summons.get_by_id(response.summons_id)
            if summons:
                summons.comment_reply = response.message
                summons.summons_replied_at = datetime.utcnow()
                summons.comment_reply_id = reply.id if reply else None # TODO: Hacky
                uow.commit()
                log.debug('Committed summons response to database')
            if reply:
                bot_comment = BotComment(
                    post_id=summons.post_id,
                    comment_body=response.message,
                    perma_link=reply.permalink,
                    source='summons',
                    comment_id=reply.id,
                    subreddit=reply.subreddit.display_name
                )
                uow.bot_comment.add(bot_comment)
                uow.commit()

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
        submission = self.reddit.submission(id=post_id)
        post = pre_process_post(submission_to_post(submission), self.uowm, None)
        with self.uowm.start() as uow:
            try:
                uow.posts.add(post)
                uow.commit()
                log.debug('Commited Post: %s', post)
            except Exception as e:
                log.exception('Problem saving new post', exc_info=True)

        return post


    def _create_first_seen(self, post: Post) -> str:
        # TODO - Move to helper. Dupped in hot post
        if post.subreddit in NO_LINK_SUBREDDITS:
            firstseen = f"First seen in {post.subreddit} on {post.created_at.strftime('%Y-%m-%d')} by u/{post.author}"
        else:
            if post.shortlink:
                original_link = post.shortlink
            else:
                original_link = 'https://reddit.com' + post.perma_link

            firstseen = f"First seen at [{post.subreddit}]({original_link}) on {post.created_at.strftime('%Y-%m-%d')}"

        log.debug('First Seen String: %s', firstseen)
        return firstseen

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