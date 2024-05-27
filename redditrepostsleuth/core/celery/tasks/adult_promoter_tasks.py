import logging

from celery import Task
from prawcore import TooManyRequests
from redis import Redis
from sqlalchemy.exc import IntegrityError

from redditrepostsleuth.core.celery import celery
from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.db.db_utils import get_db_engine
from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.core.exception import UtilApiException, UserNotFound
from redditrepostsleuth.core.notification.notification_service import NotificationService
from redditrepostsleuth.core.services.eventlogging import EventLogging
from redditrepostsleuth.core.services.response_handler import ResponseHandler
from redditrepostsleuth.core.util.onlyfans_handling import check_user_comments_for_promoter_links
from redditrepostsleuth.core.util.reddithelpers import get_reddit_instance

# TODO - THis should be safe to remove

class AdultPromoterTask(Task):
    def __init__(self):
        self.config = Config()
        self.reddit = get_reddit_instance(self.config)
        self.uowm = UnitOfWorkManager(get_db_engine(self.config))
        self.event_logger = EventLogging(config=self.config)
        self.response_handler = ResponseHandler(self.reddit, self.uowm, self.event_logger,
                                                live_response=self.config.live_responses)
        self.notification_svc = NotificationService(self.config)
        self.redis_client = Redis(
            host=self.config.redis_host,
            port=self.config.redis_port,
            db=self.config.redis_database,
            password=self.config.redis_password
        )


log = logging.getLogger(__name__)

@celery.task(bind=True, base=AdultPromoterTask, autoretry_for=(UtilApiException,ConnectionError,TooManyRequests), retry_kwards={'max_retries': 3})
def check_user_comments_for_only_fans(self, username: str) -> None:
    """
    This should be run after the profile check so we don't do any timeframe checking
    :param self:
    :param username:
    :return:
    """
    skip_names = ['[deleted]', 'AutoModerator']

    if username in skip_names:
        log.info('Skipping name %s', username)
        return

    try:
        with self.uowm.start() as uow:
            user = uow.user_review.get_by_username(username)

            if not user:
                log.error('User not found: %s', username)

            try:
                result = check_user_comments_for_promoter_links(username)
            except UserNotFound as e:
                log.warning(e)
                return

            if result:
                log.info('Promoter found: %s - %s', username, str(result))
                user.content_links_found = True
                user.notes = str(result)
            uow.user_review.add(user)
            uow.commit()
    except (UtilApiException, ConnectionError, TooManyRequests) as e:
        raise e
    except IntegrityError:
        pass
    except Exception as e:
        log.exception('')