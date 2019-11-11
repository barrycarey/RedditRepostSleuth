# TODO - Mega hackery, figure this out.
import sys



sys.path.append('./')
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
    config = Config('/home/barry/PycharmProjects/RedditRepostSleuth/sleuth_config.json')
    uowm = SqlAlchemyUnitOfWorkManager(get_db_engine(config))
    dup = DuplicateImageService(uowm, config=config)
    response_builder = ResponseBuilder(uowm)
    reddit_manager = RedditManager(get_reddit_instance(config))
    event_logger = EventLogging(config=config)
    summons = SummonsHandler(uowm, dup, reddit_manager, response_builder, ResponseHandler(reddit_manager, uowm, event_logger), event_logger=event_logger, summons_disabled=False)

    while True:
        try:
            summons.handle_summons()
        except Exception as e:
            log.exception('Summons handler crashed', exc_info=True)





