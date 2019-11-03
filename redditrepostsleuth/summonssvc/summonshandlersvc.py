# TODO - Mega hackery, figure this out.
import sys

from redditrepostsleuth.common.util.reddithelpers import get_reddit_instance
from redditrepostsleuth.core.db.uow.sqlalchemyunitofworkmanager import SqlAlchemyUnitOfWorkManager
from redditrepostsleuth.core.responsebuilder import ResponseBuilder

sys.path.append('./')
from redditrepostsleuth.core.db import db_engine

from redditrepostsleuth.common.logging import log

from redditrepostsleuth.core.duplicateimageservice import DuplicateImageService
from redditrepostsleuth.summonssvc.summonshandler import SummonsHandler

if __name__ == '__main__':
    uowm = SqlAlchemyUnitOfWorkManager(db_engine)
    dup = DuplicateImageService(uowm)
    response_builder = ResponseBuilder(uowm)
    summons = SummonsHandler(uowm, dup, get_reddit_instance(), response_builder, summons_disabled=False)

    while True:
        try:
            summons.handle_summons()
        except Exception as e:
            log.exception('Summons handler crashed', exc_info=True)





