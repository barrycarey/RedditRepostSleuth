import time
from time import perf_counter
from typing import Text, NoReturn, Optional

from praw.exceptions import APIException, ClientException
from praw.models import Comment, Redditor
from prawcore import Forbidden, PrawcoreException, ResponseException
from sqlalchemy import func

from redditrepostsleuth.core.db.databasemodels import BotComment, BannedSubreddit
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

    def reply_to_submission(self, submission_id: str, comment_body) -> Optional[Comment]:
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
            self._log_response(comment)
            return comment
        except APIException as e:
            if e.error_type == 'RATELIMIT':
                log.exception('Reddit rate limit')
                raise RateLimitException('Hit rate limit')
            else:
                log.exception('Unknown error type of APIException', exc_info=True)
                raise
        except Forbidden:
            self._save_banned_sub(submission.subreddit.display_name)
        except Exception:
            log.exception('Unknown exception leaving comment on post https://redd.it/%s', submission_id, exc_info=True)
            raise


    def reply_to_comment(self, comment_id: str, comment_body: str) -> Optional[Comment]:
        """
        Post a given reply to a given comment ID
        :rtype: Optional[Comment]
        :param comment_id: ID of comment to reply to
        :param comment_body: Body of the comment to leave in reply
        :return:
        """
        comment = self.reddit.comment(comment_id)
        if not comment:
            log.error('Failed to find comment %s', comment_id)
            return
        try:
            start_time = perf_counter()
            reply_comment = comment.reply(comment_body)
            self._record_api_event(
                float(round(perf_counter() - start_time, 2)),
                'reply_to_comment',
                self.reddit.reddit.auth.limits['remaining']
            )
            self._log_response(comment)
            log.info('Left comment at: https://reddit.com%s', reply_comment.permalink)
            return reply_comment
        except Forbidden:
            log.exception('Forbidden to respond to comment %s', comment_id, exc_info=False)
            self._save_banned_sub(comment.subreddit.display_name)
            raise
        except AssertionError:
            log.exception('Problem leaving comment', exc_info=True)
            raise

    def send_private_message(self, user: Redditor, message_body, subject: Text = 'Repost Check') -> NoReturn:
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
        except Exception:
            log.exception('Failed to send PM to %s', user.name, exc_info=True)
            raise

    def _record_api_event(self, response_time, request_type, remaining_limit):
        api_event = RedditApiEvent(request_type, response_time, remaining_limit, event_type='api_response')
        self.event_logger.save_event(api_event)

    def _log_response(self, comment: Comment):
        self._log_response_to_db(comment)
        self._log_response_to_influxdb(comment)

    def _log_response_to_influxdb(self, comment: Comment):
        """
        Take a given response and log it to InfluxDB
        :param response:
        """
        self.event_logger.save_event(
            ResponseEvent(comment.subreddit.display_name, self.source, event_type='response')
        )

    def _log_response_to_db(self, comment: Comment):
        """
        Take a given response and log it to the database
        :param response:
        """
        with self.uowm.start() as uow:
            uow.bot_comment.add(
                BotComment(
                    source=self.source,
                    comment_id=comment.id,
                    comment_body=comment.body,
                    post_id=comment.submission.id,
                    perma_link=comment.permalink,
                    subreddit=comment.subreddit.display_name
                )
            )
            try:
                uow.commit()
            except Exception as e:
                log.exception('Failed to log comment to DB', exc_info=True)

    def _save_banned_sub(self, subreddit: Text) -> NoReturn:
        with self.uowm.start() as uow:
            banned = uow.banned_subreddit.get_by_subreddit(subreddit)
            if banned:
                banned.last_checked = func.utc_timestamp()
            else:
                log.info('Adding banned sub: %s', subreddit)
                uow.banned_subreddit.add(
                    BannedSubreddit(
                        subreddit=subreddit
                    )
                )
            uow.commit()