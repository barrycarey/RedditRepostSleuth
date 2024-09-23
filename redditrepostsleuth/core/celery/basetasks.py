import datetime

from celery import Task

from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.db.db_utils import get_db_engine
from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.core.notification.notification_service import NotificationService
from redditrepostsleuth.core.services.eventlogging import EventLogging
from redditrepostsleuth.core.services.response_handler import ResponseHandler
from redditrepostsleuth.core.services.subreddit_config_updater import SubredditConfigUpdater
from redditrepostsleuth.core.util.helpers import get_reddit_instance


class EventLoggerTask(Task):
    def __init__(self):
        self.config = Config()
        self.event_logger = EventLogging(config=self.config)

class SqlAlchemyTask(Task):
    def __init__(self):
        self.config = Config()
        self.uowm = UnitOfWorkManager(get_db_engine(self.config))
        self.event_logger = EventLogging()


class RepostTask(SqlAlchemyTask):
    def __init__(self):
        super().__init__()
        self.notification_svc = NotificationService(self.config)
        self.link_blacklist = [] # Temp fix.  People were spamming onlyfans links 10s of thousands of times
        self.reddit = get_reddit_instance(self.config)


class AnnoyTask(Task):
    def __init__(self):
        self.config = Config()
        from redditrepostsleuth.core.services.duplicateimageservice import DuplicateImageService
        self.uowm = UnitOfWorkManager(get_db_engine(self.config))
        self.notification_svc = NotificationService(self.config)
        self.event_logger = EventLogging()
        self.reddit = get_reddit_instance(self.config)
        self.dup_service = DuplicateImageService(self.uowm, self.event_logger, self.reddit)

class RedditTask(Task):
    def __init__(self):
        self.config = Config()
        self.reddit = get_reddit_instance(self.config)
        self.uowm = UnitOfWorkManager(get_db_engine(self.config))
        self.event_logger = EventLogging(config=self.config)
        self.notification_svc = NotificationService(self.config)
        self.response_handler = ResponseHandler(self.reddit, self.uowm, self.event_logger, live_response=self.config.live_responses)

class AdminTask(Task):
    def __init__(self):
        self.config = Config()
        self.reddit = get_reddit_instance(self.config)
        self.uowm = UnitOfWorkManager(get_db_engine(self.config))
        self.event_logger = EventLogging(config=self.config)
        self.response_handler = ResponseHandler(self.reddit, self.uowm, self.event_logger,
                                                live_response=self.config.live_responses)
        self.notification_svc = NotificationService(self.config)
        self.config_updater = SubredditConfigUpdater(
            self.uowm,
            self.reddit,
            self.response_handler,
            self.config,
            notification_svc=self.notification_svc
        )
