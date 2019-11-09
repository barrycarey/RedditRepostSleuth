# TODO - Mega hackery, figure this out.
import sys

from redditrepostsleuth.core.services.reddit_manager import RedditManager
from redditrepostsleuth.core.services.response_handler import ResponseHandler

sys.path.append('./')
from redditrepostsleuth.core.db.db_utils import get_db_engine
from redditrepostsleuth.core.services.eventlogging import EventLogging
from redditrepostsleuth.core.db.uow.sqlalchemyunitofworkmanager import SqlAlchemyUnitOfWorkManager
from redditrepostsleuth.core.responsebuilder import ResponseBuilder
from redditrepostsleuth.core.util.reddithelpers import get_reddit_instance
from redditrepostsleuth.core.logging import log
from redditrepostsleuth.core.duplicateimageservice import DuplicateImageService
from redditrepostsleuth.summonssvc.summonshandler import SummonsHandler



if __name__ == '__main__':
    uowm = SqlAlchemyUnitOfWorkManager(get_db_engine())
    dup = DuplicateImageService(uowm)
    response_builder = ResponseBuilder(uowm)
    reddit_manager = RedditManager(get_reddit_instance())
    event_logger = EventLogging()
    summons = SummonsHandler(uowm, dup, reddit_manager, response_builder, ResponseHandler(reddit_manager, uowm, event_logger), event_logger=event_logger, summons_disabled=False)

    while True:
        try:
            summons.handle_summons()
        except Exception as e:
            log.exception('Summons handler crashed', exc_info=True)





