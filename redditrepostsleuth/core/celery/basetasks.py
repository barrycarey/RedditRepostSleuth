import datetime
import logging

from celery import Task

from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.db.db_utils import get_db_engine
from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.core.notification.notification_service import NotificationService
from redditrepostsleuth.core.services.eventlogging import EventLogging
from redditrepostsleuth.core.services.response_handler import ResponseHandler
from redditrepostsleuth.core.services.subreddit_config_updater import SubredditConfigUpdater
from redditrepostsleuth.core.util.helpers import get_reddit_instance

log = logging.getLogger(__name__)


class LoggingTaskMixin:
    """
    Mixin that adds on_failure and on_retry hooks for consistent exception logging.

    Include this mixin in task base classes to ensure task failures and retries
    are properly logged with context for debugging.
    """

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Log task failures with full context for debugging."""
        log.error(
            'Task %s[%s] failed: %s\nArgs: %s\nKwargs: %s\nTraceback:\n%s',
            self.name,
            task_id,
            exc,
            repr(args)[:500],
            repr(kwargs)[:500],
            einfo.traceback if einfo else 'No traceback available'
        )
        super().on_failure(exc, task_id, args, kwargs, einfo)

    def on_retry(self, exc, task_id, args, kwargs, einfo):
        """Log retries to help identify flaky failures."""
        retry_count = self.request.retries + 1 if hasattr(self, 'request') and self.request else 'unknown'
        log.warning(
            'Task %s[%s] retrying (attempt %s) due to: %s',
            self.name,
            task_id,
            retry_count,
            exc
        )
        super().on_retry(exc, task_id, args, kwargs, einfo)


class EventLoggerTask(LoggingTaskMixin, Task):
    def __init__(self):
        self.config = Config()
        self.event_logger = EventLogging(config=self.config)

class SqlAlchemyTask(LoggingTaskMixin, Task):
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


class ImageSearchTask(LoggingTaskMixin, Task):
    def __init__(self):
        self.config = Config()
        from redditrepostsleuth.core.services.duplicateimageservice import DuplicateImageService
        self.uowm = UnitOfWorkManager(get_db_engine(self.config))
        self.notification_svc = NotificationService(self.config)
        self.event_logger = EventLogging()
        self.reddit = get_reddit_instance(self.config)
        self.dup_service = DuplicateImageService(self.uowm, self.event_logger, self.reddit)

class RedditTask(LoggingTaskMixin, Task):
    def __init__(self):
        self.config = Config()
        self.reddit = get_reddit_instance(self.config)
        self.uowm = UnitOfWorkManager(get_db_engine(self.config))
        self.event_logger = EventLogging(config=self.config)
        self.notification_svc = NotificationService(self.config)
        self.response_handler = ResponseHandler(self.reddit, self.uowm, self.event_logger, live_response=self.config.live_responses)


class AdminTask(LoggingTaskMixin, Task):
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
