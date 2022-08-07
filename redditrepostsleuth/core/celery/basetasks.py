import pymysql
from celery import Task

from redditrepostsleuth.core import logging
from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.db.db_utils import get_db_engine
from redditrepostsleuth.core.notification.notification_service import NotificationService
from redditrepostsleuth.core.services.reddit_manager import RedditManager
from redditrepostsleuth.core.services.response_handler import ResponseHandler
from redditrepostsleuth.core.services.subreddit_config_updater import SubredditConfigUpdater
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
        self.reddit = get_reddit_instance(self.config)


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
        self.notification_svc = NotificationService(self.config)
        self.response_handler = ResponseHandler(self.reddit, self.uowm, self.event_logger, live_response=self.config.live_responses)

class AdminTask(Task):
    def __init__(self):
        self.config = Config()
        self.reddit = RedditManager(get_reddit_instance(self.config))
        self.uowm = SqlAlchemyUnitOfWorkManager(get_db_engine(self.config))
        self.event_logger = EventLogging(config=self.config)
        self.response_handler = ResponseHandler(self.reddit, self.uowm, self.event_logger,
                                                live_response=self.config.live_responses)
        self.notification_svc = NotificationService(self.config)
        self.config_updater = SubredditConfigUpdater(
            self.uowm,
            self.reddit.reddit,
            self.response_handler,
            self.config,
            notification_svc=self.notification_svc
        )

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

class PyMySQLTask(Task):
    def __init__(self):
        self.config = Config()
        self.conn = self.get_conn()

    def get_conn(self):
        return pymysql.connect(host=self.config.db_host,
                           user=self.config.db_user,
                           password=self.config.db_password,
                           db=self.config.db_name,
                           cursorclass=pymysql.cursors.SSDictCursor)

    def bulk_insert_post(self, rows):
        conn = self.get_conn()
        try:
            with conn.cursor() as cur:
                q = 'INSERT INTO post (post_id, url, perma_link, post_type, author, selftext, created_at, ingested_at, subreddit, title, crosspost_parent, hash_1, hash_2, url_hash) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)'
                data = list([(row['post_id'], row['url'], row['perma_link'], row['post_type'], row['author'], row['selftext'], row['created_at'], row['ingested_at'], row['subreddit'], row['title'], row['crosspost_parent'], row['dhash_h'], row['dhash_v'], row['url_hash']) for row in rows])
                cur.executemany(q, data)
            try:
                self.conn.commit()
            except Exception as e:
                print('')
                conn.close()
            conn.close()
        except Exception as e:
            print('')

    def bulk_insert_image_post(self, rows):
        try:
            with self.conn.cursor() as cur:
                q = 'INSERT INTO post (created_at, post_id) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)'
                data = list([(row['post_id'], row['url'], row['perma_link'], row['post_type'], row['author'], row['selftext'], row['created_at'], row['ingested_at'], row['subreddit'], row['title'], row['crosspost_parent'], row['dhash_h'], row['dhash_v'], row['url_hash']) for row in rows])
                cur.executemany(q, data)
            try:
                self.conn.commit()
            except Exception as e:
                print('')
        except Exception as e:
            print('')