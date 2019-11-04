# TODO - Mega hackery, figure this out.
import sys
sys.path.append('./')
from redditrepostsleuth.core.db.uow.sqlalchemyunitofworkmanager import SqlAlchemyUnitOfWorkManager
from redditrepostsleuth.core.responsebuilder import ResponseBuilder
from redditrepostsleuth.core.db import db_engine
from redditrepostsleuth.core.util.helpers import get_reddit_instance
from redditrepostsleuth.core.duplicateimageservice import DuplicateImageService
from redditrepostsleuth.submonitorsvc.submonitor import SubMonitor

if __name__ == '__main__':

    uowm = SqlAlchemyUnitOfWorkManager(db_engine)
    response_builder = ResponseBuilder(uowm)
    dup = DuplicateImageService(uowm)
    monitor = SubMonitor(dup, uowm, get_reddit_instance(), response_builder)
    monitor.run()