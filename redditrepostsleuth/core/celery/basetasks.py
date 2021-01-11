from celery import Task

from redditrepostsleuth.core import logging
from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.db.db_utils import get_db_engine
from redditrepostsleuth.core.notification.notification_service import NotificationService
from redditrepostsleuth.core.services.reddit_manager import RedditManager
from redditrepostsleuth.core.services.response_handler import ResponseHandler
from redditrepostsleuth.core.util.helpers import get_reddit_instance

from redditrepostsleuth.core.db.uow.sqlalchemyunitofworkmanager import SqlAlchemyUnitOfWorkManager

from redditrepostsleuth.core.services.eventlogging import EventLogging


class EventLoggerTask(Task):
    def __init__(self):
        self.config = Config()
        self.event_logger = EventLogging(config=self.config)

class SqlAlchemyTask(Task):
    def __init__(self):
        self.config = Config()
        self.uowm = SqlAlchemyUnitOfWorkManager(get_db_engine(self.config))
        self.event_logger = EventLogging()

class RepostTask(SqlAlchemyTask):
    def __init__(self):
        super().__init__()
        self.notification_svc = NotificationService(self.config)
        self.link_blacklist = [] # Temp fix.  People were spamming onlyfans links 10s of thousands of times


class AnnoyTask(Task):
    def __init__(self):
        self.config = Config()
        from redditrepostsleuth.core.services.duplicateimageservice import DuplicateImageService
        self.uowm = SqlAlchemyUnitOfWorkManager(get_db_engine(self.config))
        self.notification_svc = NotificationService(self.config)
        self.event_logger = EventLogging()
        self.reddit = get_reddit_instance(self.config)
        self.dup_service = DuplicateImageService(self.uowm, self.event_logger, self.reddit)

class RedditTask(Task):
    def __init__(self):
        self.config = Config()
        self.reddit = RedditManager(get_reddit_instance(self.config))
        self.uowm = SqlAlchemyUnitOfWorkManager(get_db_engine(self.config))
        self.event_logger = EventLogging(config=self.config)
        self.response_handler = ResponseHandler(self.reddit, self.uowm, self.event_logger, live_response=self.config.live_responses)

class RepostLogger(Task):
    def __init__(self):
        self.repost_log = logging.getLogger('error_log')
        self.repost_log.setLevel(logging.DEBUG)
        formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s: %(message)s')
        handler = logging.FileHandler('repost.log')
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(formatter)
        self.repost_log.addHandler(handler)
