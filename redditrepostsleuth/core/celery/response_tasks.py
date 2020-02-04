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