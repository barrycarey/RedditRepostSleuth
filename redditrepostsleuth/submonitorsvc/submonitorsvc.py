# TODO - Mega hackery, figure this out.
import os,sys

from redditrepostsleuth.core.responsebuilder import ResponseBuilder

sys.path.append('./')
from redditrepostsleuth.common.db import db_engine
from redditrepostsleuth.common.db.uow.sqlalchemyunitofworkmanager import SqlAlchemyUnitOfWorkManager
from redditrepostsleuth.common.util.helpers import get_reddit_instance
from redditrepostsleuth.core.duplicateimageservice import DuplicateImageService
from redditrepostsleuth.submonitorsvc.submonitor import SubMonitor

if __name__ == '__main__':

    uowm = SqlAlchemyUnitOfWorkManager(db_engine)
    response_builder = ResponseBuilder(uowm)
    dup = DuplicateImageService(uowm)
    monitor = SubMonitor(dup, uowm, get_reddit_instance(), response_builder)
    monitor.run()