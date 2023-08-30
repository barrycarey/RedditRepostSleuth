import time

from prawcore import ResponseException

from redditrepostsleuth.core.config import Config
from redditrepostsleuth.core.db.db_utils import get_db_engine
from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager
from redditrepostsleuth.core.logging import log
from redditrepostsleuth.core.services.duplicateimageservice import DuplicateImageService
from redditrepostsleuth.core.services.eventlogging import EventLogging
from redditrepostsleuth.core.services.reddit_manager import RedditManager
from redditrepostsleuth.core.services.response_handler import ResponseHandler
from redditrepostsleuth.core.services.responsebuilder import ResponseBuilder
from redditrepostsleuth.core.util.helpers import get_reddit_instance
from redditrepostsleuth.hotpostsvc.hot_post_monitor import TopPostMonitor

if __name__ == '__main__':
    while True:
        config = Config()
        uowm = UnitOfWorkManager(get_db_engine(config))
        event_logger = EventLogging(config=config)
        reddit = get_reddit_instance(config)
        reddit_manager = RedditManager(reddit)
        dup = DuplicateImageService(uowm, event_logger, reddit, config=config)
        response_builder = ResponseBuilder(uowm)

        top = TopPostMonitor(
            reddit_manager,
            uowm,
            dup,
            response_builder,
            ResponseHandler(reddit_manager, uowm, event_logger, source='toppost', live_response=config.live_responses),
            config=config
        )
        try:
            top.monitor()
        except ResponseException as e:
            if e.response.status_code == 429:
                log.error('IP Rate limit hit.  Waiting')
                time.sleep(60)
                continue
        except Exception as e:
            log.exception('Service crashed', exc_info=True)