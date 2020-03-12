import time
from time import perf_counter
from typing import Text

from praw.exceptions import APIException
from praw.models import Comment, Redditor
from prawcore import Forbidden, PrawcoreException, ResponseException

from redditrepostsleuth.core.db.databasemodels import BotComment
from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.core.exception import RateLimitException
from redditrepostsleuth.core.logging import log
from redditrepostsleuth.core.model.comment_reply import CommentReply
from redditrepostsleuth.core.model.events.reddit_api_event import RedditApiEvent
from redditrepostsleuth.core.model.events.response_event import ResponseEvent
from redditrepostsleuth.core.services.eventlogging import EventLogging
from redditrepostsleuth.core.services.reddit_manager import RedditManager


class ResponseHandler:

    def __init__(
            self,
            reddit: RedditManager,
            uowm: UnitOfWorkManager,
            event_logger: EventLogging,
            log_response: bool = True,
            source='unknown'
    ):
        self.uowm = uowm
        self.reddit = reddit
        self.log_response = log_response
        self.event_logger = event_logger
        self.source = source

    def reply_to_submission(self, submission_id: str, comment_body) -> Comment:
        submission = self.reddit.submission(submission_id)
        if not submission:
            log.error('Failed to get submission %s', submission_id)
            return

        try:
            start_time = perf_counter()
            comment = submission.reply(comment_body)
            self._record_api_event(
                float(round(perf_counter() - start_time, 2)),
                'reply_to_submission',
                self.reddit.reddit.auth.limits['remaining']
            )
            log.info('Left comment at: https://reddit.com%s', comment.permalink)
            log.debug(comment_body)
            self._log_response(comment, comment_body)
            return comment
        except APIException as e:
            if e.error_type == 'RATELIMIT':
                log.exception('Reddit rate limit')
                raise RateLimitException('Hit rate limit')
            else:
                log.exception('Unknown error type of APIException', exc_info=True)
                raise
        except Exception as e:
            log.exception('Unknown exception leaving comment on post https://redd.it/%s', submission_id, exc_info=True)
            raise


    def reply_to_comment(self, comment_id: str, comment_body: str, send_pm_on_fail: bool = False) -> CommentReply:
        comment = self.reddit.comment(comment_id)
        comment_reply = CommentReply(body=comment_body, comment=None)
        if not comment:
            comment_reply.body = 'Failed to find comment'
            log.error('Failed to find comment %s', comment_id)
            return comment_reply

        try:
            # TODO - Possibly make dataclass to wrap response info
            start_time = perf_counter()
            response = comment.reply(comment_body)
            self._record_api_event(
                float(round(perf_counter() - start_time, 2)),
                'reply_to_comment',
                self.reddit.reddit.auth.limits['remaining']
            )
            comment_reply.comment = response
            self._log_response(comment, comment_body)
            log.info('Left comment at: https://reddit.com%s', response.permalink)
            return comment_reply
        except APIException as e:
            if hasattr(e, 'error_type'):
                if e.error_type == 'DELETED_COMMENT':
                    log.debug('Comment %s has been deleted', comment_id)
                    comment_reply.body = 'DELETED COMMENT'
                    return comment_reply
                elif e.error_type == 'THREAD_LOCKED':
                    log.info('Comment %s is in a locked thread', comment_id)
                    comment_reply.body = 'THREAD LOCKED'
                    return comment_reply
                elif e.error_type == 'RATELIMIT':
                    log.exception('PRAW Ratelimit exception', exc_info=False)
                    raise
                else:
                    log.exception('APIException without error_type', exc_info=True)
                    raise
        except Forbidden:
            log.exception('Forbidden to respond to comment %s', comment_id, exc_info=False)
            if send_pm_on_fail:
                try:
                    msg = f'I\'m unable to reply to your comment at https://redd.it/{comment.submission.id}.  I\'m probably banned from r/{comment.submission.subreddit.display_name}.  Here is my response. \n\n *** \n\n'
                    msg = msg + comment_body
                    msg = self.send_private_message(comment.author, msg)
                    comment_reply.body = msg
                    return comment_reply
                except (PrawcoreException,) as e:
                    log.error('Failed to send PM', exc_info=True)
                    comment_reply.body = 'FAILED TO LEAVE COMMENT OR PM'
                    return comment_reply

        except AssertionError as e:
            log.exception('Problem leaving comment', exc_info=True)
            raise
        except ResponseException as e:
            raise

    def send_private_message(self, user: Redditor, message_body, subject: Text = 'Repost Check') -> str:
        if not user:
            log.error('No user provided to send private message')
            return

        try:
            start_time = perf_counter()
            user.message(subject, message_body)
            self._record_api_event(
                float(round(perf_counter() - start_time, 2)),
                'private_message',
                self.reddit.reddit.auth.limits['remaining']
            )
            log.info('Sent PM to %s. ', user.name)
            return message_body
        except Exception as e:
            log.exception('Failed to send PM to %s', user.name, exc_info=True)
            return 'Failed to send PM'

    def _record_api_event(self, response_time, request_type, remaining_limit):
        api_event = RedditApiEvent(request_type, response_time, remaining_limit, event_type='api_response')
        self.event_logger.save_event(api_event)

    def _log_response(self, comment: Comment, comment_body: str):
        self._log_response_to_db(comment, comment_body)
        self._log_response_to_influxdb(comment)

    def _log_response_to_influxdb(self, comment: Comment):
        """
        Take a given response and log it to InfluxDB
        :param response:
        """
        self.event_logger.save_event(
            ResponseEvent(comment.subreddit.display_name, self.source, event_type='response')
        )

    def _log_response_to_db(self, comment: Comment, comment_body: str):
        """
        Take a given response and log it to the database
        :param response:
        """
        with self.uowm.start() as uow:
            uow.bot_comment.add(
                BotComment(
                    source=self.source,
                    comment_id=comment.id,
                    comment_body=comment_body,
                    post_id=comment.submission.id,
                    perma_link=comment.permalink,
                    subreddit=comment.subreddit.display_name
                )
            )
            try:
                uow.commit()
            except Exception as e:
                log.exception('Failed to log comment to DB', exc_info=True)