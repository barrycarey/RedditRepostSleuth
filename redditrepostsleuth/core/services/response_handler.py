import logging
import os
from time import perf_counter
from typing import Text, NoReturn, Optional, Union

from praw import Reddit
from praw.exceptions import APIException, RedditAPIException
from praw.models import Comment, Redditor, Message, Subreddit
from prawcore import Forbidden, TooManyRequests
from sqlalchemy import func

from redditrepostsleuth.core.db.databasemodels import BotComment, BannedSubreddit, BotPrivateMessage
from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.core.exception import RateLimitException
from redditrepostsleuth.core.model.dummy_comment import DummyComment
from redditrepostsleuth.core.model.events.reddit_api_event import RedditApiEvent
from redditrepostsleuth.core.model.events.response_event import ResponseEvent
from redditrepostsleuth.core.notification.notification_service import NotificationService
from redditrepostsleuth.core.services.eventlogging import EventLogging
from redditrepostsleuth.core.util.replytemplates import REPLY_TEST_MODE

log = logging.getLogger(__name__)

class ResponseHandler:

    def __init__(
            self,
            reddit: Reddit,
            uowm: UnitOfWorkManager,
            event_logger: EventLogging,
            notification_svc: NotificationService = None,
            live_response: bool = False,
            log_response: bool = True,
            source='unknown'
    ):
        self.notification_svc = notification_svc
        self.live_response = live_response
        self.uowm = uowm
        self.reddit = reddit
        self.log_response = log_response
        self.event_logger = event_logger
        self.source = source

        if os.getenv('RESPONSE_TEST', None):
            self.test_mode = True
        else:
            self.test_mode = False

    def reply_to_submission(self, submission_id: str, comment_body, source: str) -> Optional[Comment]:
        submission = self.reddit.submission(submission_id)
        if not submission:
            log.warning('Failed to get submission %s', submission_id)
            return

        if self.test_mode:
            comment_body = REPLY_TEST_MODE + comment_body

        try:
            start_time = perf_counter()
            if self.live_response:
                comment = submission.reply(comment_body)
            else:
                comment = DummyComment(comment_body, submission.subreddit.display_name, submission_id)
            self._record_api_event(
                float(round(perf_counter() - start_time, 2)),
                'reply_to_submission',
                self.reddit.auth.limits['remaining']
            )
            log.info('Left comment at: https://reddit.com%s', comment.permalink)
            log.debug(comment_body)
            self._log_response(comment, source)
            return comment
        except APIException as e:
            if e.error_type == 'RATELIMIT':
                log.warning('Error Type=%s Message=Reddit rate limit', e.error_type, exc_info=False)
                raise RateLimitException('Hit rate limit')
            else:
                raise
        except Forbidden:
            self._save_banned_sub(submission.subreddit.display_name)
        except TooManyRequests:
            raise
        except Exception as e:
            log.exception('Unknown exception leaving comment on post https://redd.it/%s', submission_id, exc_info=True)
            raise

    def reply_to_comment(self, comment_id: str, comment_body: str, source: str, subreddit: Text = None) -> Optional[Comment]:
        """
                Post a given reply to a given comment ID
                :rtype: Optional[Comment]
                :param comment_id: ID of comment to reply to
                :param comment_body: Body of the comment to leave in reply
                :return:
                """
        if self.test_mode:
            comment_body = REPLY_TEST_MODE + comment_body

        comment = self.reddit.comment(comment_id)
        if not comment:
            log.error('Failed to find comment %s', comment_id)
            return
        try:
            start_time = perf_counter()
            if self.live_response:
                reply_comment = comment.reply(comment_body)
            else:
                reply_comment = DummyComment(comment_body, comment.submission.subreddit.display_name, comment.submission.id)
            self._record_api_event(
                float(round(perf_counter() - start_time, 2)),
                'reply_to_comment',
                self.reddit.auth.limits['remaining']
            )

            log.info('Left comment at: https://reddit.com%s', reply_comment.permalink)
            return self._log_response_to_db(reply_comment, source)

        except Forbidden:
            log.warning('Forbidden to respond to comment %s', comment_id, exc_info=False)
            # If we get Forbidden there's a chance we don't have hte comment data to get subreddit
            if subreddit:
                self._save_banned_sub(subreddit)
            raise
        except AssertionError:
            log.exception('Problem leaving comment', exc_info=True)
            raise

    def send_private_message(
            self,
            user: Union[Redditor, Subreddit],
            message_body,
            subject: str,
            source: str,
            comment_id: str = None
    ) -> Optional[BotPrivateMessage]:

        if not user:
            log.error('No user provided to send private message')
            return

        try:
            start_time = perf_counter()
            if self.live_response:
                user.message(subject, message_body)
            self._record_api_event(
                float(round(perf_counter() - start_time, 2)),
                'private_message',
                self.reddit.auth.limits['remaining']
            )
            log.info('Sent PM to %s. ', user.name)
        except Exception as e:
            log.exception('Failed to send PM to %s', user.name, exc_info=True)
            raise

        bot_message = BotPrivateMessage(
            subject=subject,
            body=message_body,
            in_response_to_comment=comment_id,
            triggered_from=source,
            recipient=user.name
        )
        self._save_private_message(bot_message)
        return bot_message

    def reply_to_private_message(self, message: Message, body: str) -> NoReturn:
        log.debug('Replying to private message from %s with subject %s', message.dest.name, message.subject)
        try:
            if self.live_response:
                message.reply(body)
            self._save_private_message(
                BotPrivateMessage(
                    subject=message.subject,
                    body=body,
                    triggered_from='inbox_reply',
                    recipient=message.author.name
                )
            )
        except RedditAPIException:
            log.exception('Problem replying to private message', exc_info=True)

    def send_mod_mail(self, subreddit_name: str, message_body: str, subject: str, source: str = None) -> None:
        """
        Send a modmail message
        :rtype: NoReturn
        :param subreddit_name: name of subreddit
        :param subject: Message Subject
        :param message_body: Message Body
        """
        subreddit = self.reddit.subreddit(subreddit_name)
        if not subreddit:
            log.error('Failed to get Subreddit %s when attempting to send modmail')
            return

        if self.test_mode:
            message_body = REPLY_TEST_MODE + message_body

        try:
            if self.live_response:
                subreddit.message(subject, message_body)
            self._save_private_message(
                BotPrivateMessage(
                    subject=subject,
                    body=message_body,
                    triggered_from=source,
                    recipient=f'r/{subreddit_name}'
                )
            )
        except RedditAPIException:
            log.exception('Problem sending modmail message', exc_info=True)

    def _save_private_message(self, bot_message: BotPrivateMessage) -> NoReturn:
        """
        Save a private message to the database
        :param bot_message: BotMessage obj
        """
        try:
            with self.uowm.start() as uow:
                uow.bot_private_message.add(bot_message)
                uow.commit()
        except Exception as e:
            # TODO - Get specific exc
            log.exception('Failed to save private message to DB', exc_info=True)



    def _record_api_event(self, response_time, request_type, remaining_limit):
        api_event = RedditApiEvent(request_type, response_time, remaining_limit, event_type='api_response')
        self.event_logger.save_event(api_event)

    def _log_response(self, comment: Comment, source: str):
        self._log_response_to_db(comment, source)
        self._log_response_to_influxdb(comment, source)

    def _log_response_to_influxdb(self, comment: Comment, source: str):
        """
        Take a given response and log it to InfluxDB
        :param response:
        """
        self.event_logger.save_event(
            ResponseEvent(comment.subreddit.display_name, source, event_type='response')
        )

    def _log_response_to_db(self, comment: Comment, source: str) -> Optional[BotComment]:
        """
        Take a given response and log it to the database
        :param response:
        """
        with self.uowm.start() as uow:
            bot_comment = BotComment(
                    source=source,
                    comment_id=comment.id,
                    comment_body=comment.body,
                    reddit_post_id=comment.submission.id,
                    perma_link=comment.permalink,
                    subreddit=comment.subreddit.display_name
                )
            uow.bot_comment.add(bot_comment)
            try:
                uow.commit()
                return bot_comment
            except Exception as e:
                log.exception('Failed to log comment to DB', exc_info=True)

    def _save_banned_sub(self, subreddit: str) -> None:
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

        if self.notification_svc:
            self.notification_svc.send_notification(f'Subreddit https://reddit.com/r/{subreddit} added to ban list', subject='Added Banned Sub')