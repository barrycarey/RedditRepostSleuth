# TODO - Mega hackery, figure this out.
import sys
import time

import redis

sys.path.append('./')
from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.celery.response_tasks import  process_monitored_sub
from redditrepostsleuth.core.logging import log
from redditrepostsleuth.core.services.eventlogging import EventLogging
from redditrepostsleuth.core.services.reddit_manager import RedditManager
from redditrepostsleuth.core.services.response_handler import ResponseHandler
from redditrepostsleuth.core.db.db_utils import get_db_engine
from redditrepostsleuth.core.db.uow.sqlalchemyunitofworkmanager import SqlAlchemyUnitOfWorkManager
from redditrepostsleuth.core.services.responsebuilder import ResponseBuilder

from redditrepostsleuth.core.util.helpers import get_reddit_instance
from redditrepostsleuth.core.duplicateimageservice import DuplicateImageService
from redditrepostsleuth.submonitorsvc.submonitor import SubMonitor

if __name__ == '__main__':
    config = Config()
    event_logger = EventLogging(config=config)
    uowm = SqlAlchemyUnitOfWorkManager(get_db_engine(config))
    response_builder = ResponseBuilder(uowm)
    dup = DuplicateImageService(uowm, event_logger, config=config)
    reddit = RedditManager(get_reddit_instance(config))
    monitor = SubMonitor(dup, uowm, reddit, response_builder, ResponseHandler(reddit, uowm, event_logger, source='submonitor'), event_logger=event_logger, config=config)
    redis_client = redis.Redis(host=config.redis_host, port=config.redis_port, db=0, password=config.redis_password)
    while True:
        with uowm.start() as uow:
            monitored_subs = uow.monitored_sub.get_all()
            for monitored_sub in monitored_subs:
                subreddit = reddit.subreddit(monitored_sub.name)
                if subreddit:
                    monitored_sub.subscribers = subreddit.subscribers
                    try:
                        uow.commit()
                    except Exception as e:
                        log.exception('Failed to update Monitored Sub %s', monitored_sub.name, exc_info=True)
                if not monitored_sub.active and monitored_sub.check_all_submissions:
                    log.debug('Sub %s is disabled', monitored_sub.name)
                    continue
                log.info('Checking sub %s', monitored_sub.name)
                process_monitored_sub.apply_async((monitored_sub,), queue='submonitor')
                continue

            while True:
                queued_items = redis_client.lrange('submonitor', 0, 20000)
                if len(queued_items) == 0:
                    log.info('Sub monitor queue empty.  Starting over')
                    break
                log.info('Sub monitor queue still has %s tasks', len(queued_items))
                time.sleep(60)

