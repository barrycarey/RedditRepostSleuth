from datetime import datetime

from celery import Task

from redditrepostsleuth.core.celery import celery
from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.db.db_utils import get_db_engine
from redditrepostsleuth.core.db.uow.sqlalchemyunitofworkmanager import SqlAlchemyUnitOfWorkManager
from redditrepostsleuth.core.duplicateimageservice import DuplicateImageService
from redditrepostsleuth.core.logging import log
from redditrepostsleuth.core.model.events.summonsevent import SummonsEvent
from redditrepostsleuth.core.model.repostresponse import RepostResponseBase
from redditrepostsleuth.core.services.eventlogging import EventLogging
from redditrepostsleuth.core.services.reddit_manager import RedditManager
from redditrepostsleuth.core.services.response_handler import ResponseHandler
from redditrepostsleuth.core.services.responsebuilder import ResponseBuilder
from redditrepostsleuth.core.util.reddithelpers import get_reddit_instance
from redditrepostsleuth.submonitorsvc.submonitor import SubMonitor
from redditrepostsleuth.summonssvc.summonshandler import SummonsHandler


class SummonsHandlerTask(Task):
    def __init__(self):
        self.config = Config()
        self.reddit = RedditManager(get_reddit_instance(self.config))
        self.uowm = SqlAlchemyUnitOfWorkManager(get_db_engine(self.config))
        self.event_logger = EventLogging(config=self.config)
        self.response_handler = ResponseHandler(self.reddit, self.uowm, self.event_logger, source='summons')
        dup_image_svc = DuplicateImageService(self.uowm, self.event_logger, config=self.config)
        response_builder = ResponseBuilder(self.uowm)
        self.summons_handler = SummonsHandler(self.uowm, dup_image_svc, self.reddit, response_builder,
                                 self.response_handler, event_logger=self.event_logger, summons_disabled=False)

class SubMonitorTask(Task):
    def __init__(self):
        self.config = Config()
        self.reddit = RedditManager(get_reddit_instance(self.config))
        uowm = SqlAlchemyUnitOfWorkManager(get_db_engine(self.config))
        event_logger = EventLogging(config=self.config)
        response_handler = ResponseHandler(self.reddit, uowm, event_logger, source='submonitor')
        dup_image_svc = DuplicateImageService(uowm, event_logger, config=self.config)
        response_builder = ResponseBuilder(uowm)
        self.sub_monitor = SubMonitor(dup_image_svc, uowm, self.reddit, response_builder, response_handler, event_logger=event_logger, config=self.config)

@celery.task(bind=True, base=SummonsHandlerTask, serializer='pickle')
def handle_summons(self, summons):
    with self.uowm.start() as uow:
        post = uow.posts.get_by_post_id(summons.post_id)
        if not post:
            post = self.summons_handler.save_unknown_post(summons.post_id)

        if not post:
            response = RepostResponseBase(summons_id=summons.id)
            response.message = 'Sorry, I\'m having trouble with this post. Please try again later'
            log.info('Failed to ingest post %s.  Sending error response', summons.post_id)
            self.summons_handler._send_response(summons.comment_id, response)
            return

        self.summons_handler.process_summons(summons, post)
        # TODO - This sends completed summons events to influx even if they fail
        summons_event = SummonsEvent((datetime.utcnow() - summons.summons_received_at).seconds,
                                     summons.summons_received_at, summons.requestor, event_type='summons')
        self.summons_handler._send_event(summons_event)
        log.info('Finished summons %s', summons.id)

@celery.task(bind=True, base=SubMonitorTask, serializer='pickle')
def sub_monitor_check_post(self, submission, monitored_sub):
    if not self.sub_monitor._should_check_post(submission):
        return
    self.sub_monitor.check_submission(submission, monitored_sub)

@celery.task(bind=True, base=SubMonitorTask, serializer='pickle', ignore_results=True)
def process_monitored_sub(self, monitored_sub):
    subreddit = self.reddit.subreddit(monitored_sub.name)
    if not subreddit:
        log.error('Failed to get Subreddit %s', monitored_sub.name)
        return
    log.info('Loading all submissions from %s', monitored_sub.name)
    submissions = subreddit.new(limit=monitored_sub.search_depth)
    for submission in submissions:
        sub_monitor_check_post.apply_async((submission, monitored_sub), queue='submonitor')
    log.info('All submissions from %s sent to queue', monitored_sub.name)