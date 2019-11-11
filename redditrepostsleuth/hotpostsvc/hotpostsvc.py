# TODO - Mega hackery, figure this out.
import sys



sys.path.append('./')
from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.services.response_handler import ResponseHandler
from redditrepostsleuth.core.services.eventlogging import EventLogging
from redditrepostsleuth.core.services.reddit_manager import RedditManager
from redditrepostsleuth.core.db.db_utils import get_db_engine
from redditrepostsleuth.core.db.uow.sqlalchemyunitofworkmanager import SqlAlchemyUnitOfWorkManager
from redditrepostsleuth.core.services.responsebuilder import ResponseBuilder
from redditrepostsleuth.core.logging import log
from redditrepostsleuth.core.util.helpers import get_reddit_instance
from redditrepostsleuth.core.duplicateimageservice import DuplicateImageService
from redditrepostsleuth.hotpostsvc.hot_post_monitor import TopPostMonitor


if __name__ == '__main__':
    while True:
        config = Config()
        uowm = SqlAlchemyUnitOfWorkManager(get_db_engine(config))
        dup = DuplicateImageService(uowm, config=config)
        response_builder = ResponseBuilder(uowm)
        reddit_manager = RedditManager(get_reddit_instance(config))
        event_logger = EventLogging(config=config)
        top = TopPostMonitor(
            reddit_manager,
            uowm,
            dup,
            response_builder,
            ResponseHandler(reddit_manager, uowm, event_logger),
            config=config
        )
        try:
            top.monitor()
        except Exception as e:
            log.exception('Service crashed', exc_info=True)