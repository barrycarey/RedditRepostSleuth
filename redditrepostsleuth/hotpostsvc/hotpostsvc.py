# TODO - Mega hackery, figure this out.
import os,sys
sys.path.append('./')
from redditrepostsleuth.common.db import db_engine
from redditrepostsleuth.common.db.uow.sqlalchemyunitofworkmanager import SqlAlchemyUnitOfWorkManager
from redditrepostsleuth.common.util.helpers import get_reddit_instance
from redditrepostsleuth.core.duplicateimageservice import DuplicateImageService
from redditrepostsleuth.hotpostsvc.toppostmonitor import TopPostMonitor


if __name__ == '__main__':
    uowm = SqlAlchemyUnitOfWorkManager(db_engine)
    dup = DuplicateImageService(uowm)
    top = TopPostMonitor(get_reddit_instance(), uowm, dup)
    top.monitor()
    #summons.monitor_for_summons()