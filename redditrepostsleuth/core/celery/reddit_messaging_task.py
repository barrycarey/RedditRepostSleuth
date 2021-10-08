from datetime import datetime

from celery import Task
from praw.exceptions import APIException
from praw.models import Redditor
from prawcore import Forbidden
from sqlalchemy.exc import InternalError

from redditrepostsleuth.core.celery import celery
from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.db.db_utils import get_db_engine
from redditrepostsleuth.core.db.uow.sqlalchemyunitofworkmanager import SqlAlchemyUnitOfWorkManager
from redditrepostsleuth.core.logfilters import ContextFilter
from redditrepostsleuth.core.logging import configure_logger
from redditrepostsleuth.core.model.repostresponse import SummonsResponse
from redditrepostsleuth.core.notification.notification_service import NotificationService
from redditrepostsleuth.core.services.eventlogging import EventLogging
from redditrepostsleuth.core.services.reddit_manager import RedditManager
from redditrepostsleuth.core.services.response_handler import ResponseHandler
from redditrepostsleuth.core.util.helpers import update_log_context_data
from redditrepostsleuth.core.util.reddithelpers import get_reddit_instance
from redditrepostsleuth.core.util.replytemplates import BANNED_SUB_MSG

log = configure_logger(
    name='redditrepostsleuth',
    format='%(asctime)s - %(module)s:%(funcName)s:%(lineno)d - Trace_ID=%(trace_id)s Post_ID=%(post_id)s Subreddit=%(subreddit)s Service=%(service)s Level=%(levelname)s Message=%(message)s',
    filters=[ContextFilter()]
)


class RedditMessagingTask(Task):
    def __init__(self):
        self.config = Config()
        self.reddit = get_reddit_instance(self.config)
        self.reddit_manager = RedditManager(self.reddit)
        self.uowm = SqlAlchemyUnitOfWorkManager(get_db_engine(self.config))
        self.event_logger = EventLogging(config=self.config)
        notification_svc = NotificationService(self.config)
        self.response_handler = ResponseHandler(self.reddit_manager, self.uowm, self.event_logger, source='summons',
                                                live_response=self.config.live_responses,
                                                notification_svc=notification_svc)


@celery.task(bind=True, base=RedditMessagingTask, ignore_results=True)
def send_private_message(
        self,
        user: Redditor,
        message_body,
        subject: str = 'Repost Check',
        source: str = None,
        post_id: str = None,
        comment_id: str = None
):
    self.response_handler.send_private_message(
        user,
        message_body,
        subject=subject,
        source=source,
        post_id=post_id,
        comment_id=comment_id
    )


@celery.task(bind=True, base=RedditMessagingTask, ignore_results=True)
def reply_to_submission(self, submission_id: str, comment_body: str):
    self.response_handler.reply_to_submission(submission_id, comment_body)

@celery.task(bind=True, base=RedditMessagingTask, ignore_results=True)
def reply_to_summons(self, summons_response: SummonsResponse):
    update_log_context_data(log, {'trace_id': summons_response.summons.id, 'post_id': summons_response.summons.post_id,
                                  'subreddit': summons_response.summons.subreddit, 'service': 'Summons'})
    log.debug('Sending response to summons comment %s. MESSAGE: %s', summons_response.summons.comment_id,
              summons_response.message)
    try:
        reply_comment = self.response_handler.reply_to_comment(
            summons_response.summons.comment_id,
            summons_response.message,
            subreddit=summons_response.summons.subreddit
        )
        summons_response.comment_reply_id = reply_comment.id
    except APIException as e:
        summons_response.message = e.error_type
        if e.error_type == 'RATELIMIT':
            log.exception('PRAW Ratelimit exception', exc_info=False)
            raise

    except Forbidden:
        log.info('Banned on %s, sending PM', summons_response.summons.subreddit)
        redditor = self.reddit.redditor(summons_response.summons.requestor)
        msg = BANNED_SUB_MSG.format(post_id=summons_response.summons.post_id, subreddit=summons_response.summons.subreddit)
        msg = msg + summons_response.message
        try:
            self.response_handler.send_private_message(
                redditor,
                msg,
                post_id=summons_response.summons.post_id,
                comment_id=summons_response.summons.comment_id,
                source='summons'
            )
            summons_response.message = msg
        except APIException as e:
            if e.error_type == 'NOT_WHITELISTED_BY_USER_MESSAGE':
                summons_response.message = 'NOT_WHITELISTED_BY_USER_MESSAGE'

    with self.uowm.start() as uow:
        summons = uow.summons.get_by_id(summons_response.summons.id)
        if summons:
            summons.comment_reply = summons_response.message
            summons.summons_replied_at = datetime.utcnow()
            summons.comment_reply_id = summons_response.comment_reply_id
            try:
                uow.commit()
                log.debug('Committed summons response to database')
            except InternalError:
                log.exception('Failed to save response to summons', exc_info=True)

@celery.task(bind=True, base=RedditMessagingTask, ignore_results=True)
def reply_to_comment(self, comment_id: str, comment_body: str, subreddit: str = None):
    self.response_handler.reply_to_comment(comment_id, comment_body, subreddit=subreddit)