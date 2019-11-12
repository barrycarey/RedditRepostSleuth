# TODO - Mega hackery, figure this out.
import sys

sys.path.append('./')
from redditrepostsleuth.core.config import Config
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
    reddit_manager = RedditManager(get_reddit_instance(config))
    monitor = SubMonitor(dup, uowm, reddit_manager, response_builder, ResponseHandler(reddit_manager, uowm, event_logger))
    monitor.run()