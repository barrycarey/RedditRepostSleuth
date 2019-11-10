# TODO - Mega hackery, figure this out.
import sys



sys.path.append('./')
from redditrepostsleuth.core.db.db_utils import get_db_engine
from redditrepostsleuth.core.db.uow.sqlalchemyunitofworkmanager import SqlAlchemyUnitOfWorkManager
from redditrepostsleuth.core.services.responsebuilder import ResponseBuilder
from redditrepostsleuth.core.logging import log
from redditrepostsleuth.core.util.helpers import get_reddit_instance
from redditrepostsleuth.core.duplicateimageservice import DuplicateImageService
from redditrepostsleuth.hotpostsvc.toppostmonitor import TopPostMonitor


if __name__ == '__main__':
    while True:
        uowm = SqlAlchemyUnitOfWorkManager(get_db_engine())
        dup = DuplicateImageService(uowm)
        response_builder = ResponseBuilder(uowm)
        top = TopPostMonitor(get_reddit_instance(), uowm, dup, response_builder)
        try:
            top.monitor()
        except Exception as e:
            log.exception('Service crashed', exc_info=True)