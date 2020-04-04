# TODO - Mega hackery, figure this out.
import sys
import time

import redis
from redis.exceptions import ConnectionError


sys.path.append('./')
from redditrepostsleuth.core.celery.response_tasks import process_summons
from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.services.reddit_manager import RedditManager
from redditrepostsleuth.core.services.response_handler import ResponseHandler
from redditrepostsleuth.core.db.db_utils import get_db_engine
from redditrepostsleuth.core.services.eventlogging import EventLogging
from redditrepostsleuth.core.db.uow.sqlalchemyunitofworkmanager import SqlAlchemyUnitOfWorkManager
from redditrepostsleuth.core.services.responsebuilder import ResponseBuilder
from redditrepostsleuth.core.util.reddithelpers import get_reddit_instance
from redditrepostsleuth.core.logging import log
from redditrepostsleuth.core.duplicateimageservice import DuplicateImageService
from redditrepostsleuth.summonssvc.summonshandler import SummonsHandler



if __name__ == '__main__':
    config = Config()
    event_logger = EventLogging(config=config)
    uowm = SqlAlchemyUnitOfWorkManager(get_db_engine(config))
    dup = DuplicateImageService(uowm, event_logger, config=config)
    response_builder = ResponseBuilder(uowm)
    reddit_manager = RedditManager(get_reddit_instance(config))
    summons = SummonsHandler(uowm, dup, reddit_manager, response_builder, ResponseHandler(reddit_manager, uowm, event_logger, source='summons'), event_logger=event_logger, summons_disabled=False)
    redis_client = redis.Redis(host=config.redis_host, port=config.redis_port, db=0, password=config.redis_password)
    while True:
        try:
            with uowm.start() as uow:
                summons = uow.summons.get_unreplied(limit=20)

                for s in summons:
                    log.info('Starting summons %s', s.id)
                    process_summons.apply_async((s,), queue='summons')
                while True:
                    queued_items = redis_client.lrange('summons', 0, 20000)
                    if len(queued_items) == 0:
                        log.info('Summons queue empty.  Starting over')
                        break
                    log.info('Summons queue still has %s tasks', len(queued_items))
                    time.sleep(15)
        except ConnectionError as e:
            log.exception('Error connecting to Redis')

    """
    while True:
        try:
            summons.handle_summons()
        except Exception as e:
            log.exception('Summons handler crashed', exc_info=True)
    """




