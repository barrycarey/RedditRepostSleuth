import re
from typing import List

from praw import Reddit
from praw.models import Comment
from datetime import datetime

from redditrepostsleuth.common.exception import ImageConversioinException
from redditrepostsleuth.common.logging import log
from redditrepostsleuth.common.config import UNSUPPORTED_POST_TYPE, REPOST_NO_RESULT, IMAGE_REPOST_ALL, \
    LINK_ALL, \
    WATCH_ENABLED, WATCH_NOT_FOUND, WATCH_DISABLED, UNKNOWN_COMMAND, WATCH_DUPLICATE, STATS, SIGNATURE, \
    IMAGE_REPOST_SHORT, WATCH_NOT_OC
from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.common.model.db import Summons, Post, RepostWatch
from redditrepostsleuth.common.model.repostresponse import RepostResponseBase
from redditrepostsleuth.common.model import ImageMatch
from redditrepostsleuth.service.imagerepost import ImageRepostService
from redditrepostsleuth.common.util.reposthelpers import set_shortlink, verify_oc


class RequestService:
    def __init__(self, uowm: UnitOfWorkManager, image_service: ImageRepostService, reddit: Reddit):
        self.uowm = uowm
        self.image_service = image_service
        self.reddit = reddit

    def handle_repost_request(self, summons: Summons):

        parsed_command = re.search('!repost\s(?P<command>[^\s]+)(?P<subcommand>\s[^\s]+)?', summons.comment_body, re.IGNORECASE)

        log.info('Processing request for comment %s. Body: %s', summons.comment_id, summons.comment_body)
        submission = self.reddit.submission(id=summons.post_id)
        comment = self.reddit.comment(id=summons.comment_id)
        response = RepostResponseBase(summons_id=summons.id)
        if not hasattr(submission, 'post_hint') or submission.post_hint != 'image':
            log.error('Submission has no post hint.  Cannot process summons')
            response.status = 'error'
            response.message = UNSUPPORTED_POST_TYPE
            self._send_response(comment, response)
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
            self.process_repost_request(summons, sub_command=sub_command)
        else:
            log.error('Unknown command')
            response.message = UNKNOWN_COMMAND
            self._send_response(comment, response)


    def process_stat_request(self, summons: Summons):
        response = RepostResponseBase(summons_id=summons.id)
        comment = self.reddit.comment(id=summons.comment_id)
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

        self._send_response(comment, response)

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

    def process_repost_request(self, summons: Summons, sub_command: str = None):
        submission = self.reddit.submission(id=summons.post_id)
        if submission.post_hint == 'image':
            self.process_image_repost_request(summons, sub_command=sub_command)
        elif submission.post_hint == 'link':
            self.process_link_repost_request(summons, sub_command=sub_command)

    def process_link_repost_request(self, summons: Summons, sub_command: str = None):
        submission = self.reddit.submission(id=summons.post_id)
        comment = self.reddit.comment(id=summons.comment_id)
        response = RepostResponseBase(summons_id=summons.id)
        with self.uowm.start() as uow:
            search_count = uow.posts.get_count()
            posts = uow.posts.find_all_by_url(submission.url)
            if len(posts) > 0:
                response.message = LINK_ALL.format(occurrences=len(posts),
                                                   searched=search_count,
                                                   original_href='https://reddit.com' + posts[0].perma_link,
                                                   link_text=posts[0].perma_link)
            else:
                response.message = REPOST_NO_RESULT.format(total=search_count)
            self._send_response(comment, response)

    def process_image_repost_request(self, summons: Summons, sub_command: str = None):
        submission = self.reddit.submission(id=summons.post_id)
        comment = self.reddit.comment(id=summons.comment_id)
        response = RepostResponseBase(summons_id=summons.id)

        with self.uowm.start() as uow:
            post_count = uow.posts.count_by_type('image')

        try:
            result = self.image_service.find_all_occurrences(submission)
        except ImageConversioinException as e:
            log.error('Summons Failure: Failed to convert image for repost checking.  Summons: %s', summons)
            response.message = 'Internal error while checking for reposts. \n\nPlease send me a PM to report this issue'
            self._send_response(comment, response)
            return

        if not result.matches:
            response.message = REPOST_NO_RESULT.format(total=post_count)
        else:
            # TODO: This is temp until database is backfilled with short links
            with self.uowm.start() as uow:
                for match in result.matches:
                    if not match.post.shortlink:
                        set_shortlink(match.post)
                        uow.posts.update(match.post)
                        uow.commit()

            if sub_command and sub_command.lower() == 'all':
                response.message = IMAGE_REPOST_ALL.format(occurrences=len(result.matches),
                                                           search_total=post_count,
                                                           original_link='https://reddit.com' + result.matches[0].post.perma_link,
                                                           link_text=result.matches[0].post.perma_link)
                response.message += self._build_markdown_list(result.matches)
            else:
                response.message = IMAGE_REPOST_SHORT.format(count=len(result.matches), orig_url=result.matches[0].post.shortlink)

        self._send_response(comment, response, shortlink=submission.shortlink)

    def _send_response(self, comment: Comment, response: RepostResponseBase, shortlink: str = ''):
        try:
            log.info('Sending response to summons comment %s. MESSAGE: %s', comment.id, response.message)
            response.message += SIGNATURE.format()
            reply = comment.reply(response.message)
            if reply.id:
                self._save_response(response)
                return
            log.error('Did not receive reply ID when replying to comment')
        except Exception as e:
            log.exception('Problem replying to comment', exc_info=True)


    def _save_response(self, response: RepostResponseBase):
        with self.uowm.start() as uow:
            summons = uow.summons.get_by_id(response.summons_id)
            if summons:
                summons.comment_reply = response.message
                summons.summons_replied_at = datetime.now()
                uow.commit()
                log.debug('Committed summons response to database')

    def _build_markdown_list(self, matches: List[ImageMatch]) -> str:
        result = ''
        for match in matches:
            result += '* {} - [{}]({})\n'.format(match.post.created_at, match.post.shortlink, match.post.shortlink)
        return result

    def _save_post(self, post: Post):
        with self.uowm.start() as uow:
            uow.posts.update(post)
            uow.commit()