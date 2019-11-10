from praw.models import Comment, Redditor

from redditrepostsleuth.core.db.databasemodels import BotComment
from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.core.logging import log
from redditrepostsleuth.core.model.comment_reply import CommentReply
from redditrepostsleuth.core.services.eventlogging import EventLogging
from redditrepostsleuth.core.services.reddit_manager import RedditManager


class ResponseHandler:

    def __init__(self, reddit: RedditManager, uowm: UnitOfWorkManager, event_logger: EventLogging, log_response: bool = True):
        self.uowm = uowm
        self.reddit = reddit
        self.log_response = log_response

    def reply_to_submission(self, submission_id: str, comment_body) -> Comment:
        submission = self.reddit.submission(submission_id)
        if not submission:
            log.error('Failed to get submission %s', submission_id)
            return

        try:
            comment = submission.reply(comment_body)
            log.info('Left comment at: https://reddit.com%s', comment.permalink)
            log.debug(comment_bod)
            self._log_response(comment, comment_body, source='submonitor')
            return comment
        except Exception as e:
            log.exception('Failed to leave comment on post https://redd.it/%s', submission_id, exc_info=True)


    def reply_to_comment(self, comment_id: str, comment_body: str, source: str = None, send_pm_on_fail: bool = False) -> CommentReply:
        comment = self.reddit.comment(comment_id)
        comment_reply = CommentReply(body=comment_body, comment=None)
        if not comment:
            comment_reply.body = 'Failed to find comment'
            log.error('Failed to find comment %s', comment_id)
            return comment_reply

        try:
            # TODO - Possibly make dataclass to wrap response info
            response = comment.reply(comment_body)
            comment_reply.comment = response
            self._log_response(comment, comment_body, source=source)
            log.info('Left comment at: https://reddit.com%s', response.permalink)
            return comment_reply
        except Exception as e:
            log.exception('Failed to leave comment', exc_info=True)
            if hasattr(e, 'error_type') and e.error_type in ['DELETED_COMMENT']:
                comment_reply.body = 'DELETED COMMENT'
                return comment_reply
            else:
                if send_pm_on_fail:
                    msg = 'I\'m unable to reply to your comment.  I might be banned in that sub.  Here is my response. \n\n *** \n\n'
                    msg = msg + comment_body
                    msg = self.send_private_message(comment.author, msg)
                    comment_reply.body = msg
                    return comment_reply

    def send_private_message(self, user: Redditor, message_body) -> str:
        try:
            user.message('Repost Check', message_body)
            log.info('Send PM to %s. ', user.name)
            return  message_body
        except Exception as e:
            log.exception('Failed to send PM to %s', user.name, exc_info=True)
            return 'Failed to send PM'

    def _log_response(self, comment: Comment, comment_body: str, source: str = None):
        self._log_response_to_db(comment, comment_body, source=source)
        self._log_response_to_influxdb(comment)

    def _log_response_to_influxdb(self, response):
        """
        Take a given response and log it to InfluxDB
        :param response:
        """
        pass

    def _log_response_to_db(self, comment: Comment, comment_body: str, source: str = None):
        """
        Take a given response and log it to the database
        :param response:
        """
        with self.uowm.start() as uow:
            uow.bot_comment.add(
                BotComment(
                    source=source,
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