# TODO - Mega hackery, figure this out.
import sys

from redditrepostsleuth.core.services.eventlogging import EventLogging
from redditrepostsleuth.core.services.reddit_manager import RedditManager
from redditrepostsleuth.core.services.response_handler import ResponseHandler

sys.path.append('./')
from redditrepostsleuth.core.db.db_utils import get_db_engine
from redditrepostsleuth.core.db.uow.sqlalchemyunitofworkmanager import SqlAlchemyUnitOfWorkManager
from redditrepostsleuth.core.services.responsebuilder import ResponseBuilder

from redditrepostsleuth.core.util.helpers import get_reddit_instance
from redditrepostsleuth.core.duplicateimageservice import DuplicateImageService
from redditrepostsleuth.submonitorsvc.submonitor import SubMonitor

if __name__ == '__main__':

    uowm = SqlAlchemyUnitOfWorkManager(get_db_engine())
    response_builder = ResponseBuilder(uowm)
    dup = DuplicateImageService(uowm)
    reddit_manager = RedditManager(get_reddit_instance())
    event_logger = EventLogging()
    monitor = SubMonitor(dup, uowm, reddit_manager, response_builder, ResponseHandler(reddit_manager, uowm, event_logger))
    monitor.run()