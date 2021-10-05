from celery import Task

from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.db.db_utils import get_db_engine
from redditrepostsleuth.core.db.uow.sqlalchemyunitofworkmanager import SqlAlchemyUnitOfWorkManager
from redditrepostsleuth.core.notification.notification_service import NotificationService
from redditrepostsleuth.core.services.response_handler import ResponseHandler


class RedditMessagingTask(Task):
    def __init__(self):
        self.config = Config()
        self.uowm = SqlAlchemyUnitOfWorkManager(get_db_engine(self.config))
        notification_svc = NotificationService(self.config)
        self.response_handler = ResponseHandler(self.reddit_manager, self.uowm, self.event_logger, source='summons',
                                                live_response=self.config.live_responses,
                                                notification_svc=notification_svc)