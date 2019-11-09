from celery import Task

from redditrepostsleuth.core import logging
from redditrepostsleuth.core.db.db_utils import get_db_engine
from redditrepostsleuth.core.util.helpers import get_reddit_instance

from redditrepostsleuth.core.db.uow.sqlalchemyunitofworkmanager import SqlAlchemyUnitOfWorkManager

from redditrepostsleuth.core.services.eventlogging import EventLogging


class EventLoggerTask(Task):
    def __init__(self):
        self.event_logger = EventLogging()

class SqlAlchemyTask(Task):

    def __init__(self):
        self.uowm = SqlAlchemyUnitOfWorkManager(get_db_engine())
        self.event_logger = EventLogging()


class AnnoyTask(Task):
    def __init__(self):
        from redditrepostsleuth.core.duplicateimageservice import DuplicateImageService
        self.uowm = SqlAlchemyUnitOfWorkManager(get_db_engine())
        self.dup_service = DuplicateImageService(self.uowm)
        self.event_logger = EventLogging()

class RedditTask(Task):
    def __init__(self):
        self.reddit = get_reddit_instance()
        self.uowm = SqlAlchemyUnitOfWorkManager(get_db_engine())
        self.event_logger = EventLogging()

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
