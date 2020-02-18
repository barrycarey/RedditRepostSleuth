# TODO - Mega hackery, figure this out.
import sys
import time
from redis.exceptions import ConnectionError


sys.path.append('./')
from redditrepostsleuth.core.celery.response_tasks import handle_summons
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
    while True:
        try:
            with uowm.start() as uow:
                summons = uow.summons.get_unreplied(limit=10)
                results = []
                for s in summons:
                    log.info('Starting summons %s', s.id)
                    results.append(handle_summons.apply_async((s,), queue='summons'))
                for r in results:
                    try:
                        b = r.get()
                    except ConnectionError:
                        time.sleep(60)
                        b = r.get()
                    #time.sleep(10)
            time.sleep(2)
        except ConnectionError as e:
            log.exception('Error connecting to Redis')

    """
    while True:
        try:
            summons.handle_summons()
        except Exception as e:
            log.exception('Summons handler crashed', exc_info=True)
    """




