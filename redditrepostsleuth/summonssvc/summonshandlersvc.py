# TODO - Mega hackery, figure this out.
import os,sys
sys.path.append('./')
from redditrepostsleuth.common.db import db_engine
from redditrepostsleuth.common.db.uow.sqlalchemyunitofworkmanager import SqlAlchemyUnitOfWorkManager
from redditrepostsleuth.common.logging import log
from redditrepostsleuth.common.util.helpers import get_reddit_instance
from redditrepostsleuth.core.duplicateimageservice import DuplicateImageService
from redditrepostsleuth.summonssvc.summonshandler import SummonsHandler

if __name__ == '__main__':
    uowm = SqlAlchemyUnitOfWorkManager(db_engine)
    dup = DuplicateImageService(uowm)
    summons = SummonsHandler(uowm, dup, get_reddit_instance(), summons_disabled=False)
    while True:
        try:
            summons.handle_summons()
        except Exception as e:
            log.exception('Summons handler crashed', exc_info=True)





