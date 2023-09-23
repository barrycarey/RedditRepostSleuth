# TODO - Mega hackery, figure this out.
import sys
import time

from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager

sys.path.append('./')
from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.celery.tasks.monitored_sub_tasks import process_monitored_sub
from redditrepostsleuth.core.logging import log
from redditrepostsleuth.core.services.eventlogging import EventLogging
from redditrepostsleuth.core.services.reddit_manager import RedditManager
from redditrepostsleuth.core.services.response_handler import ResponseHandler
from redditrepostsleuth.core.db.db_utils import get_db_engine
from redditrepostsleuth.core.services.responsebuilder import ResponseBuilder

from redditrepostsleuth.core.util.helpers import get_reddit_instance, get_redis_client
from redditrepostsleuth.core.services.duplicateimageservice import DuplicateImageService
from redditrepostsleuth.submonitorsvc.monitored_sub_service import MonitoredSubService

if __name__ == '__main__':
    config = Config()
    event_logger = EventLogging(config=config)
    uowm = UnitOfWorkManager(get_db_engine(config))
    response_builder = ResponseBuilder(uowm)
    reddit = get_reddit_instance(config)
    reddit_manager = RedditManager(reddit)
    dup = DuplicateImageService(uowm, event_logger, reddit, config=config)
    monitor = MonitoredSubService(
        dup,
        uowm,
        reddit,
        response_builder,
        ResponseHandler(reddit_manager, uowm, event_logger, source='submonitor', live_response=config.live_responses),
        event_logger=event_logger,
        config=config
    )
    redis = get_redis_client(config)
    while True:
        while True:
            queued_items = redis.lrange('submonitor_private', 0, 20000)
            if len(queued_items) == 0:
                log.info('Sub monitor queue empty.  Starting over')
                break
            log.info('Sub monitor queue still has %s tasks', len(queued_items))
            time.sleep(60)
        with uowm.start() as uow:
            monitored_subs = uow.monitored_sub.get_all()
            for monitored_sub in monitored_subs:
                if not monitored_sub.active:
                    log.debug('Sub %s is disabled', monitored_sub.name)
                    continue
                if not monitored_sub.is_private:
                    log.info('Skipping public subreddit %s', monitored_sub.name)
                    continue
                if not monitored_sub.check_all_submissions:
                    log.info('Sub %s does not have post checking enabled', monitored_sub.name)
                    continue
                try:
                    process_monitored_sub.apply_async((monitored_sub,), queue='submonitor_private')
                except Exception:
                    log.error('Failed to submit job to Celery')
                continue
            time.sleep(300)


